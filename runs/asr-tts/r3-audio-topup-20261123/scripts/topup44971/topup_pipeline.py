#!/usr/bin/env python3
"""44,971件にHaas/Qwen初回認識、合併ヒントtwo-pass、整形用語一覧を付ける。"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import numpy as np
import train_pipeline as base


ASR_RUN_ROOT = Path.home() / "voiceime-work-asr/r3-multiasr-train-20261123"
TTS_ROOT = Path.home() / "voiceime-work-tts/outputs/r3-audio-topup-20261123"
TTS_MANIFEST = TTS_ROOT / "manifest.jsonl"
TTS_METADATA = TTS_ROOT / "generation-metadata.json"
OLD_TTS_MANIFEST = Path.home() / "voiceime-work-tts/outputs/r3-train-20261122/manifest.jsonl"
OLD_ASR_OUTPUT = ASR_RUN_ROOT / "outputs/train-available-12000.jsonl"
PREPARATION = TTS_ROOT / "preparation.json"
INPUTS = ASR_RUN_ROOT / "inputs/topup44971"
WORK = ASR_RUN_ROOT / "outputs/topup44971-work"
FINAL_OUTPUTS = ASR_RUN_ROOT / "outputs"
EXPECTED_ROWS = 44_971
EXPECTED_FULL_ROWS = 56_971
SHARD_COUNT = 3
PREVIEW_ROWS = 22_000
PHASE_SHARDS = {"preview": range(0, SHARD_COUNT), "remaining": range(SHARD_COUNT, 2 * SHARD_COUNT)}

# 推論実装は前回の学習音声処理から再利用し、入出力先だけを追加集合へ向ける。
base.ROOT = ASR_RUN_ROOT
base.INPUTS = INPUTS
base.OUTPUTS = WORK
base.SHARD_COUNT = SHARD_COUNT
base.BATCH_SIZE = 32
base.HAAS_WORKERS_PER_GPU = 18
base.HAAS_THREADS_PER_WORKER = 2
base.MAIN_SOURCE_COMMIT = "c2ad2769819bcdb3fe1cf90fb760279692206889"
base.MAIN_SOURCE_ARCHIVE_SHA256 = "baa749ea20aea83079fe03f390f32e674825b15c22d41d83c046db30f6103402"


def id_digest(ids: list[str] | set[str]) -> str:
    """ID集合をソートしてSHA-256にし、前回・今回・全trainを照合する。"""
    payload = "\n".join(sorted(ids)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、破損した行があれば処理を止める。"""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def input_shard(index: int) -> Path:
    """長さ順に振り分けた、ASRジョブごとの入力を返す。"""
    return INPUTS / f"shard-{index:02d}.jsonl"


def prepared_records(indices: range) -> list[dict[str, Any]]:
    """登録済みの入力から対象IDを読み、同じ音声の再投入を防ぐ。"""
    rows = [row for index in indices for row in read_jsonl(input_shard(index))]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)) or not all(ids):
        raise ValueError("ASR入力に空または重複したIDがある")
    return rows


def verified_missing_ids() -> set[str]:
    """全件照合で確認した長さ不合格のIDを読み、ASR入力の完全性検査に使う。"""
    return set(json.loads(TTS_METADATA.read_text(encoding="utf-8"))["missing_topup_ids"])


def prepare(phase: str) -> None:
    """先行22,000件または残り22,971件を実時間順に3分割する。"""
    import soundfile

    indices = PHASE_SHARDS[phase]
    prep_path = WORK / f"input-metadata-{phase}.json"
    if prep_path.exists() or any(input_shard(index).exists() for index in indices):
        raise FileExistsError(f"ASR入力が既にある: {phase}")
    preparation = json.loads(PREPARATION.read_text(encoding="utf-8"))
    missing: set[str] = set()
    if phase == "preview":
        rows = []
        for index in range(2):
            shard_name = f"shard-{index:02d}"
            manifest = read_jsonl(TTS_ROOT / shard_name / "manifest.jsonl")
            source = preparation["shards"][index]
            if len(manifest) < source["rows"] - (index == 0):
                raise ValueError(f"先行分に使うTTS manifestが揃っていない: {shard_name}")
            # 完成済みの音声をIDのハッシュ順で選び、本文の種類と音声長による選別を避ける。
            ordered = sorted(manifest, key=lambda row: hashlib.sha256(row["id"].encode()).digest())
            for row in ordered[: PREVIEW_ROWS // 2]:
                row["audio_path"] = f"{shard_name}/{row['audio_path']}"
                rows.append(row)
    else:
        missing = verified_missing_ids()
        rows = read_jsonl(TTS_MANIFEST)
        all_ids = {row["id"] for row in rows}
        if len(rows) != EXPECTED_ROWS - len(missing) or len(all_ids) != len(rows):
            raise ValueError(f"TTS manifest件数またはIDが不正: {len(rows)}")
        if all_ids & missing or id_digest(all_ids | missing) != preparation["remaining_id_sha256"]:
            raise ValueError("TTS manifestのID集合が入力準備時の差集合と異なる")
        preview_ids = {row["id"] for row in prepared_records(PHASE_SHARDS["preview"])}
        if len(preview_ids) != PREVIEW_ROWS or not preview_ids <= all_ids:
            raise ValueError("先行ASR入力のID集合がTTS manifestと一致しない")
        rows = [row for row in rows if row["id"] not in preview_ids]

    ids = [str(row.get("id", "")) for row in rows]
    expected = PREVIEW_ROWS if phase == "preview" else EXPECTED_ROWS - PREVIEW_ROWS - len(missing)
    if len(rows) != expected or not all(ids) or len(ids) != len(set(ids)):
        raise ValueError(f"ASR入力件数またはIDが不正: {phase} {len(rows)}")

    speakers = set(preparation["speaker_counts"])
    for row in rows:
        if row.get("split") != "train" or row.get("speaker") not in speakers:
            raise ValueError(f"splitまたは声の割当が不正: {row.get('id')}")
        audio_path = TTS_ROOT / str(row["audio_path"])
        if not audio_path.is_file():
            raise FileNotFoundError(f"音声がない: {audio_path}")
        info = soundfile.info(str(audio_path))
        if info.samplerate != 16_000 or info.channels != 1 or info.subtype != "PCM_16":
            raise ValueError(f"音声形式が前回条件と異なる: {row['id']} {info}")
        row["audio_abs"] = str(audio_path)
        row["duration_s"] = float(info.duration)
        row["dataset"] = "train"

    rows.sort(key=lambda row: (-float(row["duration_s"]), row["id"]))
    shards = [rows[index::SHARD_COUNT] for index in range(SHARD_COUNT)]
    INPUTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    for index, shard in zip(indices, shards, strict=True):
        base.write_jsonl(input_shard(index), shard)
    metadata = {
        "phase": phase,
        "rows": len(rows),
        "unique_ids": len(set(ids)),
        "missing_ids": sorted(missing),
        "id_sha256": id_digest(ids),
        "full_train_rows": EXPECTED_FULL_ROWS,
        "full_train_id_sha256": preparation["full_train_id_sha256"],
        "existing_id_sha256": preparation["existing_id_sha256"],
        "shards": [
            {"shard": index, "rows": len(shard), "id_sha256": id_digest([row["id"] for row in shard])}
            for index, shard in zip(indices, shards, strict=True)
        ],
        "sort": "descending WAV duration then stable ID; round-robin over 3 queue jobs",
    }
    prep_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("prepared " + json.dumps(metadata, ensure_ascii=False), flush=True)


class R3AudioSpeechWorker(base.SpeechWorker):
    """Haasの子プロセスへ本処理用の識別名を付ける。"""

    def __init__(self, threads: int) -> None:
        self.process = subprocess.Popen(
            [
                "voiceime-r3audio-haas-worker",
                "worker",
                str(base.SPEECH_MODEL),
                "--device",
                "gpu",
                "--threads",
                str(threads),
                "--no-warmup",
                "--decode-on-cpu",
            ],
            executable=str(base.SPEECH),
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


base.SpeechWorker = R3AudioSpeechWorker


def haas_firstpass(
    shard_index: int, records: list[dict[str, Any]]
) -> tuple[Path, dict[str, Any]]:
    """ヒント無しHaas初回認識を、18個の同名CPU decode workerで処理する。"""
    output_path = WORK / f"haas-firstpass-shard-{shard_index:02d}.jsonl"
    expected_ids = [row["id"] for row in records]
    if output_path.is_file():
        output_rows = read_jsonl(output_path)
        if [row.get("id") for row in output_rows] != expected_ids:
            raise ValueError(f"既存Haas初回shardのIDが異なる: {output_path}")
        return output_path, {"rows": len(output_rows), "elapsed_s": 0.0, "reused": True}

    work_queue: Queue[dict[str, Any]] = Queue()
    for record in records:
        work_queue.put(record)
    results: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()
    started = time.perf_counter()
    completed = 0
    errors: list[str] = []

    def work() -> None:
        """一つのspeech.cpp workerで、キューから音声を順に認識する。"""
        nonlocal completed
        worker = R3AudioSpeechWorker(base.HAAS_THREADS_PER_WORKER)
        try:
            while True:
                try:
                    record = work_queue.get_nowait()
                except Empty:
                    return
                audio = base.load_audio(Path(record["audio_abs"]))
                inference_started = time.perf_counter()
                result = worker.transcribe(audio, None)
                row = {
                    "id": record["id"],
                    "system": base.HAAS_SYSTEM,
                    "stage": "asr",
                    "hyp": result.text,
                    "latency_s": time.perf_counter() - inference_started,
                    "speaker": record["speaker"],
                }
                with lock:
                    results[record["id"]] = row
                    completed += 1
                    if completed % 512 == 0 or completed == len(records):
                        print(
                            f"haas firstpass shard={shard_index} rows={completed}/{len(records)} "
                            f"elapsed={time.perf_counter() - started:.0f}s",
                            flush=True,
                        )
        except Exception as error:  # noqa: BLE001 - 1 workerの異常も全体を失敗にする
            errors.append(f"{type(error).__name__}: {error}")
        finally:
            worker.close()

    worker_count = min(base.HAAS_WORKERS_PER_GPU, max(1, len(records)))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(work) for _ in range(worker_count)]
        for future in as_completed(futures):
            future.result()
    if errors:
        raise RuntimeError(f"Haas初回worker失敗: {errors}")
    output_rows = [results[record["id"]] for record in records if record["id"] in results]
    if len(output_rows) != len(records):
        raise RuntimeError(f"Haas初回shardが未完了: {len(output_rows)}/{len(records)}")
    base.write_jsonl(output_path, output_rows)
    return output_path, {
        "rows": len(output_rows),
        "elapsed_s": time.perf_counter() - started,
        "workers": worker_count,
        "threads_per_worker": base.HAAS_THREADS_PER_WORKER,
        "gpu": base.assigned_gpu(),
        "hints": None,
        "decode_on_cpu": True,
        "reused": False,
    }


def run_shard(shard_index: int) -> None:
    """一つのqueue GPUでHaas初回、Qwen初回、Haas two-passを連続処理する。"""
    if not 0 <= shard_index < 2 * SHARD_COUNT:
        raise ValueError(f"shard番号が不正: {shard_index}")
    shard_path = input_shard(shard_index)
    records = read_jsonl(shard_path)
    gpu = base.assigned_gpu()
    overall_started = time.perf_counter()
    haas_path, haas_run = haas_firstpass(shard_index, records)
    haas_rows = read_jsonl(haas_path)
    if [row["id"] for row in haas_rows] != [row["id"] for row in records]:
        raise ValueError("Haas初回出力のIDがASR shardと一致しない")
    for record, haas_row in zip(records, haas_rows, strict=True):
        record["haas_first_pass_hyp"] = haas_row["hyp"]
        record["haas_first_pass_latency_s"] = float(haas_row["latency_s"])
    qwen_path, qwen_run = base.qwen_firstpass(shard_index, records)
    qwen_rows = read_jsonl(qwen_path)
    twopass_path, twopass_run = base.run_twopass(shard_index, records, qwen_rows)
    run_data = {
        "shard": shard_index,
        "rows": len(records),
        "cuda_visible_devices": gpu,
        "haas_firstpass": haas_run,
        "qwen": qwen_run,
        "twopass": twopass_run,
        "elapsed_s": time.perf_counter() - overall_started,
        "outputs": {
            "haas": str(haas_path),
            "qwen": str(qwen_path),
            "combined": str(twopass_path),
        },
    }
    (WORK / f"shard-run-{shard_index:02d}.json").write_text(
        json.dumps(run_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("complete shard " + json.dumps(run_data, ensure_ascii=False), flush=True)


def combined_shard(index: int, expected_ids: list[str]) -> list[dict[str, Any]]:
    """shardの入力と同じ順序で、所定の形式のASR結果が揃ったことを確認する。"""
    path = WORK / f"combined-shard-{index:02d}.jsonl"
    rows = read_jsonl(path)
    base.validate_output_rows(rows, expected_ids, path)
    return rows


def omitted_matches(
    source_rows: list[dict[str, Any]], output_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """各行のomitted_termsと、同じ行の用語一覧を表記の完全一致で照合する。"""
    by_id = {row["id"]: row for row in output_rows}
    matches = []
    for row in source_rows:
        output = by_id[row["id"]]
        omitted = list(dict.fromkeys(term["surface"] for term in row["omitted_terms"]))
        if not omitted:
            continue
        surfaces = {entry["surface"] for entry in output["formatter_glossary"]}
        hits = [surface for surface in omitted if surface in surfaces]
        matches.append({
            "id": row["id"],
            "omitted_terms": omitted,
            "omitted_terms_in_formatter_glossary": hits,
            "omitted_term_count": len(omitted),
            "omitted_term_hit_count": len(hits),
        })
    summary = {
        "rows_with_omitted_terms": len(matches),
        "rows_with_any_hit": sum(row["omitted_term_hit_count"] > 0 for row in matches),
        "rows_with_all_hits": sum(
            row["omitted_term_hit_count"] == row["omitted_term_count"] for row in matches
        ),
        "rows_with_no_hit": sum(row["omitted_term_hit_count"] == 0 for row in matches),
        "omitted_term_instances": sum(row["omitted_term_count"] for row in matches),
        "omitted_term_hits": sum(row["omitted_term_hit_count"] for row in matches),
    }
    return matches, summary


def publish_preview() -> None:
    """先行ASRが全件揃った段階で、同じ形式の学習JSONLを提供する。"""
    path = FINAL_OUTPUTS / "train-topup44971-preview22000.jsonl"
    indices = PHASE_SHARDS["preview"]
    records = prepared_records(indices)
    old_ids = {row["id"] for row in read_jsonl(OLD_ASR_OUTPUT)}
    ids = {row["id"] for row in records}
    if len(ids) != PREVIEW_ROWS or ids & old_ids:
        raise ValueError("先行ASR入力に欠落または既存12,000件と重複がある")
    rows = [
        row
        for index in indices
        for row in combined_shard(index, [record["id"] for record in read_jsonl(input_shard(index))])
    ]
    rows.sort(key=lambda row: row["id"])
    _, omitted = omitted_matches(records, rows)
    with (WORK / "publish-preview.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            if read_jsonl(path) != rows:
                raise ValueError(f"既存の先行ファイルが検証済みの出力と異なる: {path}")
        else:
            base.write_jsonl(path, rows)
    print(json.dumps({
        "path": str(path), "rows": len(rows), "id_sha256": id_digest(ids),
        "bytes": path.stat().st_size, "sha256": base.file_sha256(path), "omitted_terms": omitted,
    }, ensure_ascii=False), flush=True)


def finalize() -> None:
    """6 shardのASRを統合し、56,971件全体のID網羅と候補率を記録する。"""
    preparation = json.loads(PREPARATION.read_text(encoding="utf-8"))
    missing = verified_missing_ids()
    count = EXPECTED_ROWS - len(missing)
    full_count = EXPECTED_FULL_ROWS - len(missing)
    manifest_rows = read_jsonl(TTS_MANIFEST)
    expected_ids = [str(row["id"]) for row in manifest_rows]
    if len(expected_ids) != count or len(set(expected_ids)) != count:
        raise ValueError("top-up manifestのID件数が不正")
    if set(expected_ids) & missing or id_digest(set(expected_ids) | missing) != preparation["remaining_id_sha256"]:
        raise ValueError("top-up manifestのID集合が入力と一致しない")

    haas_by_id: dict[str, dict[str, Any]] = {}
    qwen_by_id: dict[str, dict[str, Any]] = {}
    combined_by_id: dict[str, dict[str, Any]] = {}
    for shard_index in range(2 * SHARD_COUNT):
        shard_records = read_jsonl(input_shard(shard_index))
        shard_ids = [str(row["id"]) for row in shard_records]
        if len(shard_ids) != len(set(shard_ids)):
            raise ValueError(f"ASR入力shard内に重複ID: {shard_index}")
        paths = {
            "haas": WORK / f"haas-firstpass-shard-{shard_index:02d}.jsonl",
            "qwen": WORK / f"qwen06-firstpass-shard-{shard_index:02d}.jsonl",
            "combined": WORK / f"combined-shard-{shard_index:02d}.jsonl",
        }
        outputs = {name: read_jsonl(path) for name, path in paths.items()}
        for name, rows in outputs.items():
            if [str(row.get("id", "")) for row in rows] != shard_ids:
                raise ValueError(f"{name}のshard件数またはID順が入力と不一致: {paths[name]}")
        for row in outputs["haas"]:
            if row["id"] in haas_by_id:
                raise ValueError(f"Haas初回にshard間重複: {row['id']}")
            haas_by_id[row["id"]] = row
        for row in outputs["qwen"]:
            if row["id"] in qwen_by_id:
                raise ValueError(f"Qwen初回にshard間重複: {row['id']}")
            qwen_by_id[row["id"]] = row
        for row in outputs["combined"]:
            if row["id"] in combined_by_id:
                raise ValueError(f"combinedにshard間重複: {row['id']}")
            combined_by_id[row["id"]] = row

    for name, rows in (("haas", haas_by_id), ("qwen", qwen_by_id), ("combined", combined_by_id)):
        if set(rows) != set(expected_ids):
            raise ValueError(
                f"{name}にIDの欠落・余分がある: rows={len(rows)} missing={len(set(expected_ids)-set(rows))} "
                f"extra={len(set(rows)-set(expected_ids))}"
            )

    old_rows = read_jsonl(OLD_TTS_MANIFEST)
    old_ids = {str(row["id"]) for row in old_rows}
    new_ids = set(expected_ids)
    if len(old_rows) != len(old_ids) or len(old_ids) != 12_000 or id_digest(old_ids) != preparation["existing_id_sha256"]:
        raise ValueError("前回音声manifestが入力準備時の12,000 IDと一致しない")
    old_asr_rows = read_jsonl(OLD_ASR_OUTPUT)
    old_asr_ids = [row["id"] for row in old_asr_rows]
    if len(old_asr_ids) != len(old_ids) or set(old_asr_ids) != old_ids:
        raise ValueError("前回ASRの12,000 IDが音声manifestと一致しない")
    base.validate_output_rows(old_asr_rows, old_asr_ids, OLD_ASR_OUTPUT)
    if old_ids & new_ids:
        raise ValueError(f"前回trainとtop-upのIDが重複: {len(old_ids & new_ids)}")
    full_ids = old_ids | new_ids
    if len(full_ids) != full_count or id_digest(full_ids | missing) != preparation["full_train_id_sha256"]:
        raise ValueError("前回12,000件とtop-upの和集合が全56,971件と一致しない")

    haas_rows = [haas_by_id[row_id] for row_id in expected_ids]
    qwen_rows = [qwen_by_id[row_id] for row_id in expected_ids]
    combined_rows = [combined_by_id[row_id] for row_id in expected_ids]
    base.validate_output_rows(combined_rows, expected_ids, FINAL_OUTPUTS / f"train-topup{count}.jsonl")
    for name, rows in (("haas", haas_rows), ("qwen", qwen_rows)):
        ids = [row["id"] for row in rows]
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError(f"{name}最終出力に重複または欠落がある")
    excluded_terms = base.load_term_list(base.TRAIN_EXCLUSIONS)
    for manifest, haas, qwen, combined in zip(manifest_rows, haas_rows, qwen_rows, combined_rows, strict=True):
        if (
            combined["dataset"] != "train"
            or combined["speaker"] != manifest["speaker"] or haas["speaker"] != manifest["speaker"]
            or combined["target_text"] != manifest["target_text"]
            or combined["spoken_text"] != manifest["spoken_text"]
            or combined["haas_first_pass_hyp"] != haas["hyp"]
            or combined["qwen06_first_pass_hyp"] != qwen["hyp"]
            or combined["haas_first_pass_latency_s"] != haas["latency_s"]
            or combined["qwen06_first_pass_latency_s"] != qwen["latency_s"]
        ):
            raise ValueError(f"照合したASR結果または入力が異なる: {combined['id']}")
        if any(
            not isinstance(combined[key], str)
            for key in ("haas_first_pass_hyp", "haas_second_pass_plain_hyp", "segment_merge_hyp", "qwen06_first_pass_hyp")
        ):
            raise ValueError(f"認識結果の型が不正: {combined['id']}")
        if any(not math.isfinite(value) or value < 0 for key, value in combined.items() if key.endswith("_latency_s")):
            raise ValueError(f"認識時間が不正: {combined['id']}")
        for key in ("haas_asr_hints", "formatter_glossary"):
            if any(entry["surface"] in excluded_terms for entry in combined[key]):
                raise ValueError(f"除外語が一覧に混入した: {combined['id']} {key}")

    omitted_topup, omitted_topup_summary = omitted_matches(manifest_rows, combined_rows)
    omitted_old, omitted_old_summary = omitted_matches(old_rows, old_asr_rows)
    omitted_all = sorted(omitted_topup + omitted_old, key=lambda row: row["id"])
    omitted_all_summary = {
        key: omitted_topup_summary[key] + omitted_old_summary[key] for key in omitted_topup_summary
    }
    final_paths = {
        "haas": FINAL_OUTPUTS / f"haas-plain-topup{count}.jsonl",
        "qwen": FINAL_OUTPUTS / f"qwen06-firstpass-topup{count}.jsonl",
        "combined": FINAL_OUTPUTS / f"train-topup{count}.jsonl",
        "omitted_term_matches": FINAL_OUTPUTS / f"omitted-term-matches-train{full_count}.jsonl",
    }
    for path in final_paths.values():
        if path.exists():
            raise FileExistsError(f"完成済み出力を上書きしない: {path}")
    for name, rows in (
        ("haas", haas_rows), ("qwen", qwen_rows), ("combined", combined_rows),
        ("omitted_term_matches", omitted_all),
    ):
        base.write_jsonl(final_paths[name], rows)

    exact_total = exact_hits = folded_hits = rows_with_terms = rows_with_hit = 0
    for manifest, output in zip(manifest_rows, combined_rows, strict=True):
        terms = list(dict.fromkeys(manifest.get("terms", [])))
        surfaces = [entry["surface"] for entry in output["formatter_glossary"]]
        exact = set(surfaces)
        folded = {surface.casefold() for surface in surfaces}
        hits = sum(term in exact for term in terms)
        exact_total += len(terms)
        exact_hits += hits
        folded_hits += sum(term.casefold() in folded for term in terms)
        rows_with_terms += bool(terms)
        rows_with_hit += bool(hits)

    qwen_latencies = [float(row["latency_s"]) for row in qwen_rows]
    tts_metadata = json.loads(TTS_METADATA.read_text(encoding="utf-8"))
    run_files = [
        json.loads((WORK / f"shard-run-{index:02d}.json").read_text(encoding="utf-8"))
        for index in range(2 * SHARD_COUNT)
    ]
    queue_util: dict[str, str] = {}
    queue_root = Path.home() / "voiceime-queue"
    for phase, priority in (("tts", 80), ("asr", 90)):
        for state in ("done", "failed"):
            for util_path in sorted((queue_root / state).glob(f"{priority}-r3audio-{phase}-*topup44971*.util")):
                queue_util[util_path.stem] = f"{state}: {util_path.read_text(encoding='utf-8').strip()}"

    from voiceime.formatter.glossary import load_glossary

    glossary = load_glossary(
        base.GLOSSARY_V1,
        base.GLOSSARY_V2,
        exclude_terms=excluded_terms,
    )
    metadata = {
        "coverage": "partial_topup_confirmed_tts_failures" if missing else "complete_training_split_topup",
        "main_source_commit": base.MAIN_SOURCE_COMMIT,
        "main_source_archive_sha256": base.MAIN_SOURCE_ARCHIVE_SHA256,
        "previous_train_id_sha256": id_digest(old_ids),
        "topup_train_id_sha256": id_digest(new_ids),
        "full_train_id_sha256": id_digest(full_ids),
        "row_counts": {
            "previous": len(old_ids),
            "topup": len(new_ids),
            "full_train": len(full_ids),
            "topup_unique": len(set(expected_ids)),
            "topup_missing": len(missing),
            "overlap": 0,
        },
        "confirmed_tts_failures": tts_metadata["missing_topup_details"],
        "tts": tts_metadata,
        "model": json.loads(base.QWEN_MODEL_METADATA.read_text(encoding="utf-8"))["models"][base.QWEN_SYSTEM],
        "speech_model": {
            "path": str(base.SPEECH_MODEL),
            "sha256": base.file_sha256(base.SPEECH_MODEL),
            "speech_cpp_commit": base.SPEECH_CPP_COMMIT,
            "ggml_commit": base.GGML_COMMIT,
        },
        "glossary": {
            "v1_sha256": base.file_sha256(base.GLOSSARY_V1),
            "v2_sha256": base.file_sha256(base.GLOSSARY_V2),
            "excluded_sha256": base.file_sha256(base.TRAIN_EXCLUSIONS),
            "excluded_unique_surface_count": len(excluded_terms),
            "candidate_surface_count_after_exclusions": len(glossary),
        },
        "selection": {
            "text": "Haas first-pass hypothesis + newline + Qwen0.6B first-pass hypothesis",
            "source": "src/voiceime/formatter/glossary.py select_glossary from current main",
            "haas_hints": "engine.asr_hints cap 16 terms / 240 characters",
            "formatter_glossary_cap": 20,
            "two_pass_policy": "segment-merge",
            "merge_min_reading_similarity": 0.80,
        },
        "execution": {
            "qwen_batch_size": 32,
            "qwen_language": "Japanese",
            "qwen_context": "empty",
            "qwen_generation": {"do_sample": False, "num_beams": 1},
            "haas_firstpass_hints": None,
            "haas_decode": "CPU with CUDA encoder",
            "haas_workers_per_gpu": 18,
            "haas_threads_per_worker": 2,
            "shard_runs": run_files,
            "queue_util": queue_util,
            "qwen_item_latency_mean_s": statistics.fmean(qwen_latencies),
            "qwen_item_latency_median_s": statistics.median(qwen_latencies),
        },
        "results": {
            "rows": len(combined_rows),
            "unique_ids": len({row["id"] for row in combined_rows}),
            "missing_ids": sorted(missing),
            "target_term_instances": exact_total,
            "formatter_glossary_exact_surface_hits": exact_hits,
            "formatter_glossary_exact_surface_rate": exact_hits / exact_total if exact_total else None,
            "formatter_glossary_casefold_surface_hits": folded_hits,
            "formatter_glossary_casefold_surface_rate": folded_hits / exact_total if exact_total else None,
            "rows_with_target_terms": rows_with_terms,
            "rows_with_any_exact_target_term_in_glossary": rows_with_hit,
            "row_hit_rate": rows_with_hit / len(combined_rows),
            "omitted_terms": {
                "match": "exact surface; deduplicated per row; only formatter_glossary",
                "topup": omitted_topup_summary,
                "previous": omitted_old_summary,
                "full_train": omitted_all_summary,
            },
            "outputs": {
                name: {
                    "path": str(path),
                    "rows": len(omitted_all) if name == "omitted_term_matches" else count,
                    "bytes": path.stat().st_size,
                    "sha256": base.file_sha256(path),
                }
                for name, path in final_paths.items()
            },
        },
    }
    metadata_path = FINAL_OUTPUTS / f"metadata-topup{count}.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "finalized "
        + json.dumps(
            {
                "rows": metadata["row_counts"],
                "term_hits": [exact_hits, exact_total],
                "queue_util": queue_util,
                "outputs": metadata["results"]["outputs"],
                "metadata": str(metadata_path),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def main() -> None:
    """準備・shard推論・完成検査を別々に実行する。"""
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("phase", choices=PHASE_SHARDS)
    run_parser = commands.add_parser("run-shard")
    run_parser.add_argument("--shard", type=int, required=True)
    commands.add_parser("publish-preview")
    commands.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.phase)
    elif args.command == "run-shard":
        run_shard(args.shard)
    elif args.command == "publish-preview":
        publish_preview()
    elif args.command == "finalize":
        finalize()


if __name__ == "__main__":
    main()
