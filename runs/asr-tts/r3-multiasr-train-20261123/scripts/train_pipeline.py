#!/usr/bin/env python3
"""第3弾の利用可能な音声にQwen認識とHaas two-passを行う。"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import numpy as np

from voiceime.asr.base import SAMPLE_RATE, Term, Transcription, load_audio


ROOT = Path.home() / "voiceime-work-asr/r3-multiasr-train-20261123"
OUTPUTS = ROOT / "outputs"
INPUTS = ROOT / "inputs"
ASR_ROOT = Path.home() / "voiceime-work-asr"
TTS_TRAIN_ROOT = Path.home() / "voiceime-work-tts/outputs/r3-train-20261122"
QWEN_VAL_ROOT = (
    Path.home()
    / "voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/data/tts/val"
)
HAAS_TRAIN_PLAIN = ASR_ROOT / "r3-train-20261122/train-plain.jsonl"
HAAS_VAL_PLAIN = ASR_ROOT / "r3-twopass-20261122/outputs/b-val-plain.jsonl"
QWEN_MODEL_METADATA = ASR_ROOT / "r3-multiasr-20261122/models/models.json"
GLOSSARY_V1 = ASR_ROOT / "data/glossary/glossary.jsonl"
GLOSSARY_V2 = ASR_ROOT / "data/glossary/glossary-v2.jsonl"
TRAIN_EXCLUSIONS = (
    ASR_ROOT / "r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
)
SPEECH = ASR_ROOT / "speech.cpp/build-cuda-toolkit/speech"
SPEECH_MODEL = ASR_ROOT / "models/asr/haas-ja-v1.0-gguf/Haas-616M-ja-v1.0-Q8_0.gguf"
MAIN_SOURCE_COMMIT = "cab8b886084c42935227c904027dd790d0df17af"
MAIN_SOURCE_ARCHIVE_SHA256 = "40ce43534a41d8d116dfd3dfbce12f393f462b8cbb18ecaca239ac276c7cc585"
SPEECH_CPP_COMMIT = "8d18924cd238b87c0297df112f7ff40783a6414f"
GGML_COMMIT = "79b50d239d0b88852814c873db0d85d43ed66d9b"
QWEN_SYSTEM = "qwen3-asr-0.6b"
HAAS_SYSTEM = "haas-ja-v1.0-speechcpp-q8_0"
FULL_TRAIN_ROWS_DOCUMENTED = 56_971
SHARD_COUNT = 3
BATCH_SIZE = 32
HAAS_WORKERS_PER_GPU = 18
HAAS_THREADS_PER_WORKER = 2
OUTPUT_FIELDS = {
    "id",
    "dataset",
    "speaker",
    "target_text",
    "spoken_text",
    "haas_first_pass_hyp",
    "haas_first_pass_latency_s",
    "haas_second_pass_plain_hyp",
    "haas_second_pass_latency_s",
    "segment_merge_hyp",
    "qwen06_first_pass_hyp",
    "qwen06_first_pass_latency_s",
    "haas_asr_hints",
    "formatter_glossary",
    "merge_edits",
}
DATASETS = {
    "train": {
        "manifest": TTS_TRAIN_ROOT / "manifest.jsonl",
        "audio_root": TTS_TRAIN_ROOT,
        "haas_plain": HAAS_TRAIN_PLAIN,
        "expected_rows": 12_000,
    },
    "val": {
        "manifest": QWEN_VAL_ROOT / "manifest.jsonl",
        "audio_root": QWEN_VAL_ROOT,
        "haas_plain": HAAS_VAL_PLAIN,
        "expected_rows": 1_000,
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、途中の不正行を入力エラーとして止める。"""
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """一時ファイルを使い、完成したJSONLだけを出力先へ置く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def file_sha256(path: Path) -> str:
    """実験条件の入力ファイルを識別するSHA-256を返す。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_records() -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    """trainとvalのmanifestを読み、音声・既存Haas結果との対応を確かめる。"""
    import soundfile

    records_by_dataset: dict[str, list[dict[str, Any]]] = {}
    ids_by_dataset: dict[str, list[str]] = {}
    for dataset, config in DATASETS.items():
        manifest = config["manifest"]
        records = read_jsonl(manifest)
        ids = [str(row.get("id", "")) for row in records]
        if len(records) != config["expected_rows"] or not all(ids):
            raise ValueError(
                f"{dataset} manifest件数またはIDが不正: {len(records)}"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(f"{dataset} manifest内に重複IDがある")
        for row in records:
            row["dataset"] = dataset
            audio_path = config["audio_root"] / row["audio_path"]
            if not audio_path.is_file():
                raise FileNotFoundError(f"manifestに記載された音声がない: {audio_path}")
            info = soundfile.info(str(audio_path))
            row["audio_abs"] = str(audio_path)
            row["duration_s"] = info.duration
            if not isinstance(row.get("terms"), list) or not all(
                isinstance(term, str) for term in row["terms"]
            ):
                raise ValueError(f"対象語リストがない: {dataset}/{row['id']}")
            if not isinstance(row.get("target_text"), str) or not isinstance(
                row.get("spoken_text"), str
            ):
                raise ValueError(f"教師文または読み上げ文がない: {dataset}/{row['id']}")
        haas_rows = read_jsonl(config["haas_plain"])
        haas_ids = [str(row.get("id", "")) for row in haas_rows]
        if haas_ids != ids:
            raise ValueError(f"{dataset} Haas 1回目のIDがmanifestと一致しない")
        if any(row.get("system") != HAAS_SYSTEM for row in haas_rows):
            raise ValueError(f"{dataset} Haas出力のsystemが異なる")
        for record, haas_row in zip(records, haas_rows, strict=True):
            record["haas_first_pass_hyp"] = haas_row["hyp"]
            record["haas_first_pass_latency_s"] = float(haas_row["latency_s"])
        records_by_dataset[dataset] = records
        ids_by_dataset[dataset] = ids
    return records_by_dataset, ids_by_dataset


def prepare() -> None:
    """音声長順に全行を3分割し、ジョブが読むmanifestと条件記録を作る。"""
    if OUTPUTS.exists() and any(OUTPUTS.iterdir()):
        raise FileExistsError(f"既存の出力を上書きしない: {OUTPUTS}")
    records_by_dataset, ids_by_dataset = load_records()
    INPUTS.mkdir(parents=True, exist_ok=True)
    ordered = [
        record
        for dataset in DATASETS
        for record in records_by_dataset[dataset]
    ]
    ordered.sort(key=lambda row: (-float(row["duration_s"]), row["id"]))
    shards: list[list[dict[str, Any]]] = [[] for _ in range(SHARD_COUNT)]
    for index, row in enumerate(ordered):
        shards[index % SHARD_COUNT].append(row)
    for shard_index, shard in enumerate(shards):
        write_jsonl(INPUTS / f"shard-{shard_index:02d}.jsonl", shard)

    metadata = {
        "coverage": "partial_available_audio_only",
        "main_source_commit": MAIN_SOURCE_COMMIT,
        "main_source_archive_sha256": MAIN_SOURCE_ARCHIVE_SHA256,
        "speech_cpp_commit": SPEECH_CPP_COMMIT,
        "ggml_commit": GGML_COMMIT,
        "documented_full_train_rows": FULL_TRAIN_ROWS_DOCUMENTED,
        "available_train_rows": len(records_by_dataset["train"]),
        "unavailable_train_audio_rows": (
            FULL_TRAIN_ROWS_DOCUMENTED - len(records_by_dataset["train"])
        ),
        "available_val_rows": len(records_by_dataset["val"]),
        "shard_count": SHARD_COUNT,
        "batch_size": BATCH_SIZE,
        "sort": "global descending WAV duration; round-robin across three shards",
        "train_manifest": {
            "path": str(DATASETS["train"]["manifest"]),
            "sha256": file_sha256(DATASETS["train"]["manifest"]),
            "rows": len(records_by_dataset["train"]),
        },
        "val_manifest": {
            "path": str(DATASETS["val"]["manifest"]),
            "sha256": file_sha256(DATASETS["val"]["manifest"]),
            "rows": len(records_by_dataset["val"]),
        },
        "haas_plain": {
            "train": {"path": str(HAAS_TRAIN_PLAIN), "sha256": file_sha256(HAAS_TRAIN_PLAIN)},
            "val": {"path": str(HAAS_VAL_PLAIN), "sha256": file_sha256(HAAS_VAL_PLAIN)},
        },
        "id_counts": {
            name: {"rows": len(ids), "unique_ids": len(set(ids))}
            for name, ids in ids_by_dataset.items()
        },
    }
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "input-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "prepared "
        + json.dumps(
            {
                "train": len(records_by_dataset["train"]),
                "val": len(records_by_dataset["val"]),
                "missing_train_audio": metadata["unavailable_train_audio_rows"],
                "shards": [len(shard) for shard in shards],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def assigned_gpu() -> str:
    """キューからGPUを1枚だけ割り当てられた場合に番号を返す。"""
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible or "," in visible or visible == "0":
        raise RuntimeError(f"GPU1〜3の1枚割り当てを確認できない: {visible!r}")
    return visible


def load_qwen_model() -> tuple[Any, Any, dict[str, Any]]:
    """既存の0.6B checkpointを日本語greedy・空contextで使う。"""
    import torch
    from qwen_asr import Qwen3ASRModel

    if not torch.cuda.is_available():
        raise RuntimeError("CUDAが利用できない")
    model_metadata = json.loads(QWEN_MODEL_METADATA.read_text(encoding="utf-8"))
    model_info = model_metadata["models"][QWEN_SYSTEM]
    recognizer = Qwen3ASRModel.from_pretrained(
        model_info["path"],
        dtype=torch.bfloat16,
        device_map="cuda:0",
        max_inference_batch_size=BATCH_SIZE,
        max_new_tokens=512,
    )
    generation = recognizer.model.generation_config
    generation.do_sample = False
    generation.num_beams = 1
    generation.num_return_sequences = 1
    generation.return_dict_in_generate = True
    recognizer.model.eval()
    return recognizer, torch, model_info


def qwen_firstpass(shard_index: int, records: list[dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    """音声長順の32件batchを0.6B Qwenへ渡し、ASR JSONLを保存する。"""
    gpu = assigned_gpu()
    output_path = OUTPUTS / f"qwen06-firstpass-shard-{shard_index:02d}.jsonl"
    expected_ids = [row["id"] for row in records]
    if output_path.is_file():
        rows = read_jsonl(output_path)
        if [row.get("id") for row in rows] != expected_ids:
            raise ValueError(f"既存Qwen shardのIDが異なる: {output_path}")
        return output_path, {"rows": len(rows), "elapsed_s": 0.0, "reused": True}

    recognizer, torch, model_info = load_qwen_model()
    output_rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    print(
        f"start qwen shard={shard_index} rows={len(records)} batch={BATCH_SIZE} gpu={gpu}",
        flush=True,
    )
    for offset in range(0, len(records), BATCH_SIZE):
        batch = records[offset : offset + BATCH_SIZE]
        audio_batch = [load_audio(Path(record["audio_abs"])) for record in batch]
        batch_started = time.perf_counter()
        hypotheses = recognizer.transcribe(
            [(audio, SAMPLE_RATE) for audio in audio_batch],
            context=[""] * len(audio_batch),
            language=["Japanese"] * len(audio_batch),
        )
        batch_wall = time.perf_counter() - batch_started
        if len(hypotheses) != len(batch):
            raise RuntimeError(
                f"Qwen batchの出力数が異なる: {len(hypotheses)}/{len(batch)}"
            )
        per_item_latency = batch_wall / len(batch)
        for record, hypothesis in zip(batch, hypotheses, strict=True):
            output_rows.append(
                {
                    "id": record["id"],
                    "system": QWEN_SYSTEM,
                    "stage": "asr",
                    "hyp": hypothesis.text,
                    "latency_s": per_item_latency,
                }
            )
        if len(output_rows) % 512 < BATCH_SIZE:
            print(
                f"progress qwen shard={shard_index} rows={len(output_rows)}/{len(records)} "
                f"elapsed={time.perf_counter() - started:.0f}s",
                flush=True,
            )
    write_jsonl(output_path, output_rows)
    if [row["id"] for row in output_rows] != expected_ids:
        raise RuntimeError(f"Qwen shardのID順が入力と異なる: {output_path}")
    elapsed = time.perf_counter() - started
    run_data = {
        "rows": len(output_rows),
        "elapsed_s": elapsed,
        "latency_s_definition": "Qwen batch inference wall time divided by the batch item count; audio loading excluded",
        "batch_size": BATCH_SIZE,
        "model": model_info,
        "torch": str(torch.__version__),
        "gpu": torch.cuda.get_device_name(0),
        "cuda_visible_devices": gpu,
        "reused": False,
    }
    del recognizer
    gc.collect()
    torch.cuda.empty_cache()
    return output_path, run_data


class SpeechWorker:
    """CPU decodeのspeech.cpp childを一つ管理し、ヒント付き再認識を行う。"""

    def __init__(self, threads: int) -> None:
        self.process = subprocess.Popen(
            [
                "voiceime-r3multi-haas-twopass-worker",
                "worker",
                str(SPEECH_MODEL),
                "--device",
                "gpu",
                "--threads",
                str(threads),
                "--no-warmup",
                "--decode-on-cpu",
            ],
            executable=str(SPEECH),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.next_id = 0
        ready = self._read_message()
        if ready.get("type") != "ready":
            raise RuntimeError(f"speech.cpp workerの起動応答が不正: {ready}")

    def _read_message(self) -> dict[str, Any]:
        """speech.cpp childからJSON応答を1件読む。"""
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"speech.cpp worker終了: rc={self.process.poll()}")
        return json.loads(line)

    def transcribe(self, audio: np.ndarray, hints: list[Term] | None) -> Transcription:
        """音声PCMとengine形式の用語をspeech.cppへ送り、2回目の仮説を返す。"""
        import base64

        from voiceime.asr.speechcpp_backend import format_keywords

        request_id = f"u{self.next_id}"
        self.next_id += 1
        pcm = np.clip(np.round(audio * 32768.0), -32768, 32767).astype("<i2").tobytes()
        self.process.stdin.write(
            json.dumps(
                {
                    "type": "chunk",
                    "id": request_id,
                    "seq": 0,
                    "pcm": base64.b64encode(pcm).decode("ascii"),
                }
            )
            + "\n"
        )
        request: dict[str, Any] = {
            "type": "transcribe",
            "id": request_id,
            "sample_rate": SAMPLE_RATE,
        }
        if hints:
            keywords = format_keywords(hints)
            if keywords:
                request["keywords"] = keywords
        self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        while True:
            response = self._read_message()
            if response.get("id") != request_id or response.get("type") == "progress":
                continue
            if response.get("type") != "end":
                raise RuntimeError(f"speech.cppの応答が不正: {response}")
            return Transcription(text=response["text"])

    def close(self) -> None:
        """workerを正常終了させ、異常終了を上位へ伝える。"""
        if self.process.poll() is not None:
            return
        try:
            self.process.stdin.close()
            status = self.process.wait(timeout=30)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            self.process.terminate()
            status = self.process.wait(timeout=10)
        if status != 0:
            raise RuntimeError(f"speech.cpp worker終了コード={status}")


def run_twopass(
    shard_index: int,
    records: list[dict[str, Any]],
    qwen_rows: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    """mainの用語選択とsegment-mergeを使い、formatter向け一覧を含む行を作る。"""
    from voiceime.asr.systems import MODELS, asr_hint_format
    from voiceime.engine import (
        SEGMENT_MERGE_MIN_READING_SIMILARITY,
        asr_hints,
        merge_two_pass_text,
    )
    from voiceime.formatter.glossary import (
        GlossaryIndex,
        load_glossary,
        load_term_list,
        select_glossary,
    )

    gpu = assigned_gpu()
    output_path = OUTPUTS / f"combined-shard-{shard_index:02d}.jsonl"
    if output_path.is_file():
        rows = read_jsonl(output_path)
        if [row.get("id") for row in rows] != [row["id"] for row in records]:
            raise ValueError(f"既存two-pass shardのIDが異なる: {output_path}")
        return output_path, {"rows": len(rows), "elapsed_s": 0.0, "reused": True}
    glossary = load_glossary(
        GLOSSARY_V1,
        GLOSSARY_V2,
        exclude_terms=load_term_list(TRAIN_EXCLUSIONS),
    )
    index = GlossaryIndex(glossary)
    by_surface = {entry.surface: entry for entry in glossary}
    hint_format = asr_hint_format(MODELS[HAAS_SYSTEM])
    qwen_by_id = {row["id"]: row for row in qwen_rows}
    if len(qwen_by_id) != len(qwen_rows):
        raise ValueError("Qwen shardに重複IDがある")
    if [row["id"] for row in qwen_rows] != [row["id"] for row in records]:
        raise ValueError("Qwen shardのID順がmanifestと異なる")

    work_queue: Queue[dict[str, Any]] = Queue()
    for row in records:
        work_queue.put(row)
    results: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()
    errors: list[str] = []
    started = time.perf_counter()
    completed = 0

    def work() -> None:
        """一つのworker processでshard内の発話を順に認識する。"""
        nonlocal completed
        worker = SpeechWorker(HAAS_THREADS_PER_WORKER)
        try:
            while True:
                try:
                    record = work_queue.get_nowait()
                except Empty:
                    return
                record_id = record["id"]
                qwen_row = qwen_by_id[record_id]
                selection_text = record["haas_first_pass_hyp"] + "\n" + qwen_row["hyp"]
                candidates16 = select_glossary(selection_text, index, max_entries=16)
                hints = asr_hints(candidates16, hint_format) or []
                hinted_entries = [
                    by_surface[hint.surface] for hint in hints if hint.surface in by_surface
                ]
                audio = load_audio(Path(record["audio_abs"]))
                second_started = time.perf_counter()
                second = worker.transcribe(audio, hints or None)
                second_latency = time.perf_counter() - second_started
                merged = merge_two_pass_text(
                    record["haas_first_pass_hyp"], second.text, hinted_entries
                )
                formatter_terms = select_glossary(
                    selection_text, index, max_entries=20
                )
                result = {
                    "id": record_id,
                    "dataset": record["dataset"],
                    "speaker": record.get("speaker"),
                    "target_text": record.get("target_text", ""),
                    "spoken_text": record.get("spoken_text", ""),
                    "haas_first_pass_hyp": record["haas_first_pass_hyp"],
                    "haas_first_pass_latency_s": record[
                        "haas_first_pass_latency_s"
                    ],
                    "haas_second_pass_plain_hyp": second.text,
                    "haas_second_pass_latency_s": second_latency,
                    "segment_merge_hyp": merged.text,
                    "qwen06_first_pass_hyp": qwen_row["hyp"],
                    "qwen06_first_pass_latency_s": qwen_row["latency_s"],
                    "haas_asr_hints": [asdict(hint) for hint in hints],
                    "formatter_glossary": [
                        {
                            "surface": entry.surface,
                            "readings": list(entry.readings),
                        }
                        for entry in formatter_terms
                    ],
                    "merge_edits": [asdict(edit) for edit in merged.edits],
                }
                with lock:
                    results[record_id] = result
                    completed += 1
                    if completed % 250 == 0:
                        print(
                            f"progress twopass shard={shard_index} "
                            f"rows={completed}/{len(records)} "
                            f"elapsed={time.perf_counter() - started:.0f}s",
                            flush=True,
                        )
        except Exception as error:
            with lock:
                errors.append(repr(error))
            raise
        finally:
            worker.close()

    worker_count = min(HAAS_WORKERS_PER_GPU, max(1, len(records)))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(work) for _ in range(worker_count)]
        for future in as_completed(futures):
            future.result()
    if errors:
        raise RuntimeError(f"two-pass worker失敗: {errors}")
    ordered_rows = [results[record["id"]] for record in records]
    if len(ordered_rows) != len(records):
        raise RuntimeError(f"two-pass shardが未完了: {len(ordered_rows)}/{len(records)}")
    if any(set(row) != OUTPUT_FIELDS for row in ordered_rows):
        raise RuntimeError("two-pass出力schemaが不正")
    write_jsonl(output_path, ordered_rows)
    return output_path, {
        "rows": len(ordered_rows),
        "elapsed_s": time.perf_counter() - started,
        "workers": worker_count,
        "threads_per_worker": HAAS_THREADS_PER_WORKER,
        "gpu": gpu,
        "policy": "segment-merge",
        "merge_min_reading_similarity": SEGMENT_MERGE_MIN_READING_SIMILARITY,
        "reused": False,
    }


def run_shard(shard_index: int) -> None:
    """割当GPU上でQwen初回認識とHaas two-passを続けて実行する。"""
    if not 0 <= shard_index < SHARD_COUNT:
        raise ValueError(f"shard番号が不正: {shard_index}")
    shard_path = INPUTS / f"shard-{shard_index:02d}.jsonl"
    records = read_jsonl(shard_path)
    gpu = assigned_gpu()
    overall_started = time.perf_counter()
    qwen_path, qwen_run = qwen_firstpass(shard_index, records)
    qwen_rows = read_jsonl(qwen_path)
    two_pass_path, twopass_run = run_twopass(shard_index, records, qwen_rows)
    run_metadata = {
        "shard": shard_index,
        "rows": len(records),
        "cuda_visible_devices": gpu,
        "qwen": qwen_run,
        "twopass": twopass_run,
        "elapsed_s": time.perf_counter() - overall_started,
        "outputs": {"qwen": str(qwen_path), "combined": str(two_pass_path)},
    }
    run_path = OUTPUTS / f"shard-run-{shard_index:02d}.json"
    run_path.write_text(
        json.dumps(run_metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("complete shard " + json.dumps(run_metadata, ensure_ascii=False), flush=True)


def validate_output_rows(rows: list[dict[str, Any]], expected_ids: list[str], path: Path) -> None:
    """出力件数、重複、欠落、ID順、必須schemaを確認する。"""
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"出力に重複IDがある: {path}")
    if ids != expected_ids:
        raise ValueError(
            f"出力のIDがmanifestと異なる: {path}; "
            f"rows={len(ids)} expected={len(expected_ids)} "
            f"missing={len(set(expected_ids) - set(ids))} "
            f"extra={len(set(ids) - set(expected_ids))}"
        )
    for row in rows:
        if set(row) != OUTPUT_FIELDS:
            raise ValueError(f"出力schemaが不正: {path}, id={row.get('id')}")
        if len(row["formatter_glossary"]) > 20:
            raise ValueError(f"formatter用語数が上限を超えた: {row['id']}")
        if len(row["haas_asr_hints"]) > 16:
            raise ValueError(f"Haas用語数が上限を超えた: {row['id']}")


def finalize() -> None:
    """3 shardをmanifest順へ戻し、完全性と対象語の一覧採用率を記録する。"""
    records_by_dataset, ids_by_dataset = load_records()
    combined_by_id: dict[str, dict[str, Any]] = {}
    qwen_by_id: dict[str, dict[str, Any]] = {}
    for shard_index in range(SHARD_COUNT):
        shard_records = read_jsonl(INPUTS / f"shard-{shard_index:02d}.jsonl")
        combined_path = OUTPUTS / f"combined-shard-{shard_index:02d}.jsonl"
        qwen_path = OUTPUTS / f"qwen06-firstpass-shard-{shard_index:02d}.jsonl"
        combined_rows = read_jsonl(combined_path)
        qwen_rows = read_jsonl(qwen_path)
        if [row["id"] for row in combined_rows] != [row["id"] for row in shard_records]:
            raise ValueError(f"combined shardのIDが入力と違う: {combined_path}")
        if [row["id"] for row in qwen_rows] != [row["id"] for row in shard_records]:
            raise ValueError(f"Qwen shardのIDが入力と違う: {qwen_path}")
        for row in combined_rows:
            if row["id"] in combined_by_id:
                raise ValueError(f"shard間でIDが重複: {row['id']}")
            combined_by_id[row["id"]] = row
        for row in qwen_rows:
            if row["id"] in qwen_by_id:
                raise ValueError(f"Qwen shard間でIDが重複: {row['id']}")
            qwen_by_id[row["id"]] = row

    metrics: dict[str, Any] = {}
    final_counts: dict[str, Any] = {}
    for dataset, records in records_by_dataset.items():
        rows = [combined_by_id[record["id"]] for record in records]
        path = OUTPUTS / (
            "train-available-12000.jsonl" if dataset == "train" else "val-1000.jsonl"
        )
        validate_output_rows(rows, ids_by_dataset[dataset], path)
        write_jsonl(path, rows)
        exact_total = 0
        exact_hits = 0
        folded_hits = 0
        rows_with_target = 0
        rows_with_exact_hit = 0
        for record, row in zip(records, rows, strict=True):
            terms = list(dict.fromkeys(record["terms"]))
            glossary_surfaces = [entry["surface"] for entry in row["formatter_glossary"]]
            exact_set = set(glossary_surfaces)
            folded_set = {surface.casefold() for surface in glossary_surfaces}
            exact_for_row = sum(term in exact_set for term in terms)
            folded_for_row = sum(term.casefold() in folded_set for term in terms)
            exact_total += len(terms)
            exact_hits += exact_for_row
            folded_hits += folded_for_row
            rows_with_target += bool(terms)
            rows_with_exact_hit += bool(exact_for_row)
        latency_rows = [qwen_by_id[record["id"]]["latency_s"] for record in records]
        metrics[dataset] = {
            "rows": len(rows),
            "unique_ids": len({row["id"] for row in rows}),
            "missing_ids": len(set(ids_by_dataset[dataset]) - {row["id"] for row in rows}),
            "target_term_instances": exact_total,
            "formatter_glossary_exact_surface_hits": exact_hits,
            "formatter_glossary_exact_surface_rate": exact_hits / exact_total if exact_total else None,
            "formatter_glossary_casefold_surface_hits": folded_hits,
            "formatter_glossary_casefold_surface_rate": folded_hits / exact_total if exact_total else None,
            "rows_with_target_terms": rows_with_target,
            "rows_with_any_exact_target_term_in_glossary": rows_with_exact_hit,
            "row_hit_rate": rows_with_exact_hit / len(rows) if rows else None,
            "qwen06_item_latency_mean_s": statistics.fmean(latency_rows),
            "qwen06_item_latency_median_s": statistics.median(latency_rows),
            "output": str(path),
            "output_bytes": path.stat().st_size,
            "output_sha256": file_sha256(path),
        }
        final_counts[dataset] = {
            "rows": len(rows),
            "unique_ids": len({row["id"] for row in rows}),
            "missing_ids": metrics[dataset]["missing_ids"],
            "output": str(path),
        }

    input_metadata = json.loads((OUTPUTS / "input-metadata.json").read_text(encoding="utf-8"))
    input_metadata.update(
        {
            "main_source_commit": MAIN_SOURCE_COMMIT,
            "main_source_archive_sha256": MAIN_SOURCE_ARCHIVE_SHA256,
            "speech_cpp_commit": SPEECH_CPP_COMMIT,
            "ggml_commit": GGML_COMMIT,
        }
    )
    glossary_excluded = load_term_list(TRAIN_EXCLUSIONS)
    from voiceime.formatter.glossary import load_glossary

    candidate_glossary = load_glossary(
        GLOSSARY_V1,
        GLOSSARY_V2,
        exclude_terms=glossary_excluded,
    )
    glossary_summary = {
        "v1": {"path": str(GLOSSARY_V1), "sha256": file_sha256(GLOSSARY_V1)},
        "v2": {"path": str(GLOSSARY_V2), "sha256": file_sha256(GLOSSARY_V2)},
        "excluded": {
            "path": str(TRAIN_EXCLUSIONS),
            "sha256": file_sha256(TRAIN_EXCLUSIONS),
            "unique_surface_count": len(glossary_excluded),
        },
        "candidate_surface_count_after_exclusions": len(candidate_glossary),
    }
    run_files = [
        json.loads((OUTPUTS / f"shard-run-{index:02d}.json").read_text(encoding="utf-8"))
        for index in range(SHARD_COUNT)
    ]
    queue_util = {}
    for index in range(SHARD_COUNT):
        job_name = f"35-r3multi-train-qwen06-haas-shard-{index:02d}"
        util_path = Path.home() / "voiceime-queue/done" / f"{job_name}.util"
        queue_util[job_name] = (
            util_path.read_text(encoding="utf-8").strip()
            if util_path.is_file()
            else "UNAVAILABLE: queue .util not found in done/"
        )
    metadata = {
        **input_metadata,
        "model": json.loads(QWEN_MODEL_METADATA.read_text(encoding="utf-8"))["models"][QWEN_SYSTEM],
        "speech_model": {
            "path": str(SPEECH_MODEL),
            "sha256": file_sha256(SPEECH_MODEL),
            "speech_cpp_commit": SPEECH_CPP_COMMIT,
            "ggml_commit": GGML_COMMIT,
        },
        "glossary": glossary_summary,
        "selection": {
            "source": "src/voiceime/formatter/glossary.py select_glossary on main",
            "selection_text": "Haas first-pass hypothesis + newline + Qwen0.6B first-pass hypothesis",
            "haas_hint_cap": "engine.asr_hints: 16 terms / 240 characters",
            "formatter_glossary_cap": 20,
            "two_pass_policy": "segment-merge",
            "merge_min_reading_similarity": 0.80,
        },
        "execution": {
            "jobs": run_files,
            "queue_util": queue_util,
            "batch_size": BATCH_SIZE,
            "sort_and_sharding": "descending duration then stable ID; round-robin over 3 queue jobs",
            "environment_versions": {
                package: importlib.metadata.version(package)
                for package in ("qwen-asr", "torch", "transformers", "huggingface-hub", "accelerate", "soundfile", "safetensors")
            },
        },
        "results": metrics,
        "integrity": final_counts,
    }
    metadata_path = OUTPUTS / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "finalized "
        + json.dumps({"integrity": final_counts, "metrics": metrics, "metadata": str(metadata_path)}, ensure_ascii=False),
        flush=True,
    )


def load_term_list(path: Path) -> set[str]:
    """除外用語ファイルから重複を除いた表記を読み込む。"""
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> None:
    """manifest準備、shard推論、最終検証のサブコマンドを実行する。"""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    shard_parser = subparsers.add_parser("run-shard")
    shard_parser.add_argument("--shard", type=int, required=True)
    subparsers.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run-shard":
        run_shard(args.shard)
    elif args.command == "finalize":
        finalize()


if __name__ == "__main__":
    main()
