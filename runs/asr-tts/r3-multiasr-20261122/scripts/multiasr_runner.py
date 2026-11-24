#!/usr/bin/env python3
"""多言語ASRの初回認識と、Haasとの合併ヒント評価を行う。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import statistics
import subprocess
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import numpy as np

from voiceime.asr.base import SAMPLE_RATE, Term, Transcription, load_audio


ROOT = Path.home() / "voiceime-work-asr/r3-multiasr-20261122"
ASR_ROOT = Path.home() / "voiceime-work-asr"
TWOPASS_ROOT = ASR_ROOT / "r3-twopass-20261122"
SPEECH = ASR_ROOT / "speech.cpp/build-cuda-toolkit/speech"
SPEECH_MODEL = ASR_ROOT / "models/asr/haas-ja-v1.0-gguf/Haas-616M-ja-v1.0-Q8_0.gguf"
SYSTEM_HAAS = "haas-ja-v1.0-speechcpp-q8_0"
OUTPUT_SCHEMA = {"id", "system", "stage", "hyp", "latency_s"}
DATASETS = {
    "test-novel": {
        "manifest": Path.home() / "voiceime-work-tts/outputs/r3-test-novel-20261122/manifest.jsonl",
        "audio_root": Path.home() / "voiceime-work-tts/outputs/r3-test-novel-20261122",
        "haas_prefix": "a-test-novel-include-novel",
        "expected_rows": 500,
        "exclude_file": TWOPASS_ROOT / "terms/exclude-v2-83.txt",
    },
    "val": {
        "manifest": Path.home() / "voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/data/tts/val/manifest.jsonl",
        "audio_root": Path.home() / "voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/data/tts/val",
        "haas_prefix": "b-val",
        "expected_rows": 1000,
        "exclude_file": TWOPASS_ROOT / "terms/exclude-v2-plus-heldout.txt",
    },
}
MODEL_CONFIG = {
    "qwen06": {
        "system": "qwen3-asr-0.6b",
        "model_key": "qwen3-asr-0.6b",
        "kind": "qwen",
    },
    "qwen17": {
        "system": "qwen3-asr-1.7b",
        "model_key": "qwen3-asr-1.7b",
        "kind": "qwen",
    },
    "whisper": {
        "system": "whisper-large-v3-turbo",
        "model_key": "whisper-large-v3-turbo",
        "kind": "whisper",
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、空行や壊れたJSONを入力エラーとして止める。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"JSONLの形式が不正: {path}:{line_number}") from error
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """全行を一時ファイルへ書き、完了した結果だけを公開する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def validate_ids(rows: list[dict[str, Any]], expected: list[str], path: Path) -> None:
    """結果の行数、重複、manifest順、評価用schemaを検証する。"""
    ids = [row.get("id") for row in rows]
    if ids != expected:
        raise ValueError(f"idまたは行順がmanifestと異なる: {path}")
    for row in rows:
        if set(row) != OUTPUT_SCHEMA or row.get("stage") != "asr":
            raise ValueError(f"評価JSONLのschemaが不正: {path}, id={row.get('id')}")
        if not isinstance(row.get("hyp"), str) or not isinstance(row.get("latency_s"), (int, float)):
            raise ValueError(f"hypまたはlatency_sが不正: {path}, id={row.get('id')}")


def read_manifest(dataset: str) -> list[dict[str, Any]]:
    """データセットmanifestを読み、行数・id・音声ファイルを確かめる。"""
    config = DATASETS[dataset]
    rows = read_jsonl(config["manifest"])
    ids = [row.get("id") for row in rows]
    if len(rows) != config["expected_rows"] or len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError(f"manifestの件数またはidが不正: {dataset} rows={len(rows)}")
    for row in rows:
        audio_path = config["audio_root"] / row["audio_path"]
        if not audio_path.is_file():
            raise FileNotFoundError(f"manifestの音声がない: {audio_path}")
    return rows


def assigned_gpu() -> str:
    """ジョブキューが1枚のGPUを割り当てた場合だけ推論を許す。"""
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible or "," in visible or visible == "0":
        raise RuntimeError(f"ジョブキュー経由のGPU1〜3割り当てを確認できない: {visible!r}")
    return visible


def load_multilingual_model(model_key: str, device: str) -> tuple[Any, dict[str, Any]]:
    """model metadataから公式checkpointを読み、greedy設定の認識器を返す。"""
    import torch

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDAが利用できない")
    config = MODEL_CONFIG[model_key]
    if config["kind"] == "qwen" and device != "cuda":
        raise ValueError("Qwen3-ASRの今回の実行はCUDAのみ対応")
    metadata = json.loads((ROOT / "models/models.json").read_text(encoding="utf-8"))
    model_info = metadata["models"][config["model_key"]]
    model_path = model_info["path"]
    if config["kind"] == "qwen":
        from qwen_asr import Qwen3ASRModel

        recognizer = Qwen3ASRModel.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map="cuda:0",
            max_inference_batch_size=8,
            max_new_tokens=512,
        )
        generation = recognizer.model.generation_config
        generation.do_sample = False
        generation.num_beams = 1
        generation.num_return_sequences = 1
        generation.return_dict_in_generate = True
        generation.temperature = 1.0
        recognizer.model.eval()

        def transcribe_batch(audios: list[np.ndarray]) -> list[str]:
            """文脈なしの音声batchを日本語指定のQwenでgreedy認識する。"""
            outputs = recognizer.transcribe(
                [(audio, SAMPLE_RATE) for audio in audios],
                context=[""] * len(audios),
                language=["Japanese"] * len(audios),
            )
            return [output.text for output in outputs]

        model_info = {
            **model_info,
            "greedy": {"do_sample": False, "num_beams": 1, "max_new_tokens": 512},
            "batch_size": 8,
            "dtype": "bfloat16",
        }
    else:
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
        recognizer = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_path,
            dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            low_cpu_mem_usage=True,
            local_files_only=True,
        ).to("cuda:0" if device == "cuda" else "cpu")
        recognizer.eval()
        generation = recognizer.generation_config
        generation.do_sample = False
        generation.num_beams = 1
        generation.temperature = 1.0

        def transcribe_batch(audios: list[np.ndarray]) -> list[str]:
            """Whisperへ日本語prefixを与え、音声batchをgreedy認識する。"""
            inputs = processor(
                audios,
                sampling_rate=SAMPLE_RATE,
                return_tensors="pt",
                padding=True,
                return_attention_mask=True,
            )
            target_device = "cuda:0" if device == "cuda" else "cpu"
            features = inputs.input_features.to(device=target_device, dtype=recognizer.dtype)
            tokens = recognizer.generate(
                input_features=features,
                attention_mask=inputs.attention_mask.to(device=target_device),
                language="japanese",
                task="transcribe",
                num_beams=1,
                do_sample=False,
                max_new_tokens=444,
            )
            return processor.batch_decode(tokens, skip_special_tokens=True)

        model_info = {
            **model_info,
            "greedy": {
                "do_sample": False,
                "num_beams": 1,
                "language": "japanese",
                "task": "transcribe",
                "max_new_tokens": 444,
                "attention_mask_for_padding": True,
            },
            "batch_size": 8,
            "dtype": str(recognizer.dtype).removeprefix("torch."),
        }
    model_info["runtime"] = {
        "device": torch.cuda.get_device_name(0) if device == "cuda" else "CPU",
        "torch": torch.__version__,
    }
    return transcribe_batch, model_info


def read_partial(path: Path, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    """中断時の完全な行を読み、再開できる出力だけを保持する。"""
    if not path.exists():
        return {}
    output: dict[str, dict[str, Any]] = {}
    valid_lines: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise ValueError(f"途中のJSONL行が壊れている: {path}:{index + 1}")
            continue
        if row.get("id") not in expected_ids:
            raise ValueError(f"manifest外のidがある: {path}:{row.get('id')}")
        output[row["id"]] = row
        valid_lines.append(line)
    if len(valid_lines) != len(lines):
        path.write_text("\n".join(valid_lines) + ("\n" if valid_lines else ""), encoding="utf-8")
    return output


def run_firstpass(model_key: str, device: str, cpu_threads: int) -> None:
    """1モデルでtest-novelとvalをbatch処理し、評価JSONLと速度情報を保存する。"""
    import torch

    visible = assigned_gpu() if device == "cuda" else "cpu"
    if device == "cpu":
        torch.set_num_threads(cpu_threads)
        torch.set_num_interop_threads(1)
    config = MODEL_CONFIG[model_key]
    transcribe_batch, model_info = load_multilingual_model(model_key, device)
    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_started = time.perf_counter()
    metadata: dict[str, Any] = {
        "system": config["system"],
        "model": model_info,
        "environment_versions": {
            package: importlib.metadata.version(package)
            for package in (
                "qwen-asr",
                "torch",
                "transformers",
                "huggingface-hub",
                "accelerate",
                "soundfile",
                "safetensors",
            )
        },
        "cuda_visible_devices": visible,
        "cpu_threads": cpu_threads if device == "cpu" else None,
        "device": device,
        "batch_size": 8,
        "latency_s_definition": "バッチの推論壁時間を、同時に出力された各行へ記録",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "datasets": {},
    }

    datasets = {name: read_manifest(name) for name in DATASETS}
    warmup_records = datasets["test-novel"][:8]
    warmup_audio = [
        load_audio(DATASETS["test-novel"]["audio_root"] / row["audio_path"])
        for row in warmup_records
    ]
    transcribe_batch(warmup_audio)  # warm-up is excluded from each row's latency.
    print(
        f"start model={config['system']} device={visible} rows="
        f"{sum(len(rows) for rows in datasets.values())} greedy=true batch=8 warmup=8",
        flush=True,
    )

    for dataset, records in datasets.items():
        path = out_dir / f"multiasr-{dataset}-{model_key}-firstpass.jsonl"
        partial = path.with_suffix(path.suffix + ".partial")
        ids = [row["id"] for row in records]
        if path.is_file():
            existing = read_jsonl(path)
            validate_ids(existing, ids, path)
            if any(row["system"] != config["system"] for row in existing):
                raise ValueError(f"既存結果のsystemが異なる: {path}")
            print(f"skip complete dataset={dataset} rows={len(existing)}", flush=True)
            continue
        saved = read_partial(partial, set(ids))
        started = time.perf_counter()
        with partial.open("a", encoding="utf-8") as output:
            pending_records = [record for record in records if record["id"] not in saved]
            for offset in range(0, len(pending_records), 8):
                batch = pending_records[offset : offset + 8]
                audio_batch = [
                    load_audio(DATASETS[dataset]["audio_root"] / record["audio_path"])
                    for record in batch
                ]
                batch_started = time.perf_counter()
                hypotheses = transcribe_batch(audio_batch)
                batch_latency = time.perf_counter() - batch_started
                if len(hypotheses) != len(batch):
                    raise RuntimeError(
                        f"batch出力数が入力数と異なる: {dataset} {len(hypotheses)}/{len(batch)}"
                    )
                for record, hypothesis in zip(batch, hypotheses, strict=True):
                    row = {
                        "id": record["id"],
                        "system": config["system"],
                        "stage": "asr",
                        "hyp": hypothesis,
                        "latency_s": batch_latency,
                    }
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    saved[row["id"]] = row
                output.flush()
                if len(saved) % 50 < 8:
                    print(
                        f"progress model={config['system']} dataset={dataset} "
                        f"rows={len(saved)}/{len(records)} elapsed={time.perf_counter() - started:.0f}s",
                        flush=True,
                    )
        ordered = [saved[record_id] for record_id in ids]
        validate_ids(ordered, ids, path)
        write_jsonl(path, ordered)
        partial.unlink(missing_ok=True)
        latencies = [float(row["latency_s"]) for row in ordered]
        metadata["datasets"][dataset] = {
            "rows": len(ordered),
            "elapsed_s": time.perf_counter() - started,
            "latency_mean_s": statistics.fmean(latencies),
            "latency_median_s": statistics.median(latencies),
            "latency_p90_s": float(np.percentile(latencies, 90)),
            "output": str(path),
        }
        print(
            f"complete model={config['system']} dataset={dataset} rows={len(ordered)} "
            f"elapsed={metadata['datasets'][dataset]['elapsed_s']:.1f}s "
            f"mean_latency={metadata['datasets'][dataset]['latency_mean_s']:.3f}s",
            flush=True,
        )
    metadata["elapsed_s"] = time.perf_counter() - run_started
    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    meta_path = out_dir / f"multiasr-{model_key}-run.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"model complete {config['system']} total={metadata['elapsed_s']:.1f}s", flush=True)


def normalized_surface(text: str) -> str:
    """表記比較用にUnicode正規化、大文字小文字、空白、記号を無視する。"""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace() and unicodedata.category(character)[0] not in {"P", "S"}
    )


def term_counts(records: list[dict[str, Any]], hypotheses: dict[str, str]) -> dict[str, Any]:
    """対象用語の正表記・正規化表記一致件数と発話単位の件数を返す。"""
    total = exact = normalized = rows_exact = rows_normalized = 0
    for record in records:
        hyp = hypotheses[record["id"]]
        normalized_hyp = normalized_surface(hyp)
        terms = record.get("terms", [])
        total += len(terms)
        row_exact = False
        row_normalized = False
        for surface, expected in Counter(terms).items():
            exact_count = min(expected, hyp.count(surface))
            normalized_term = normalized_surface(surface)
            normalized_count = (
                min(expected, normalized_hyp.count(normalized_term)) if normalized_term else 0
            )
            exact += exact_count
            normalized += normalized_count
            row_exact |= exact_count > 0
            row_normalized |= normalized_count > 0
        rows_exact += int(row_exact)
        rows_normalized += int(row_normalized)
    return {
        "target_term_instances": total,
        "exact_surface_instances": exact,
        "exact_surface_accuracy": exact / total if total else None,
        "normalized_surface_instances": normalized,
        "normalized_surface_accuracy": normalized / total if total else None,
        "rows_with_any_exact_term": rows_exact,
        "rows_with_any_normalized_term": rows_normalized,
        "rows": len(records),
    }


def reading_aligned_cer(records: list[dict[str, Any]], hypotheses: dict[str, str]) -> dict[str, Any]:
    """PLAN.mdに従いspoken_textとASR出力を用語の最初の読みへそろえてCERを返す。"""
    from voiceime.eval.metrics import calculate_cer, replace_glossary_surfaces_with_readings

    references = [
        replace_glossary_surfaces_with_readings(row["spoken_text"], row.get("glossary", []))
        for row in records
    ]
    aligned_hypotheses = [
        replace_glossary_surfaces_with_readings(hypotheses[row["id"]], row.get("glossary", []))
        for row in records
    ]
    return calculate_cer(references, aligned_hypotheses)


def selection_metrics(
    records: list[dict[str, Any]],
    haas_hypotheses: dict[str, str],
    multilingual_hypotheses: dict[str, str] | None,
    index: GlossaryIndex,
) -> dict[str, Any]:
    """Haas単独または2つのASR文から候補を選び、正解語の選択率を返す。"""
    from voiceime.asr.systems import MODELS, asr_hint_format
    from voiceime.engine import asr_hints
    from voiceime.formatter.glossary import select_glossary

    result: dict[str, Any] = {}
    hint_format = asr_hint_format(MODELS[SYSTEM_HAAS])
    for cap in (16, 20):
        candidate_rows_hit = candidate_terms_hit = candidate_count = total_terms = 0
        hint_rows_hit = hint_terms_hit = hint_count = 0
        for record in records:
            record_id = record["id"]
            text = haas_hypotheses[record_id]
            if multilingual_hypotheses is not None:
                text += "\n" + multilingual_hypotheses[record_id]
            selected = select_glossary(text, index, max_entries=cap)
            selected_surfaces = {entry.surface for entry in selected}
            targets = record.get("terms", [])
            candidate_hits = sum(surface in selected_surfaces for surface in targets)
            candidates = asr_hints(selected, hint_format) or []
            hint_surfaces = {term.surface for term in candidates}
            hint_hits = sum(surface in hint_surfaces for surface in targets)
            candidate_rows_hit += int(candidate_hits > 0)
            candidate_terms_hit += candidate_hits
            hint_rows_hit += int(hint_hits > 0)
            hint_terms_hit += hint_hits
            total_terms += len(targets)
            candidate_count += len(selected)
            hint_count += len(candidates)
        result[str(cap)] = {
            "max_entries": cap,
            "selected_candidates_before_asr_caps": {
                "rows_with_any_correct_target": candidate_rows_hit,
                "rows": len(records),
                "row_hit_rate": candidate_rows_hit / len(records) if records else None,
                "target_term_instances_selected": candidate_terms_hit,
                "target_term_instances": total_terms,
                "term_instance_hit_rate": candidate_terms_hit / total_terms if total_terms else None,
                "candidate_instances": candidate_count,
            },
            "hints_after_asr_caps": {
                "max_terms": 16,
                "max_characters": 240,
                "rows_with_any_correct_target": hint_rows_hit,
                "rows": len(records),
                "row_hit_rate": hint_rows_hit / len(records) if records else None,
                "target_term_instances_selected": hint_terms_hit,
                "target_term_instances": total_terms,
                "term_instance_hit_rate": hint_terms_hit / total_terms if total_terms else None,
                "hint_instances": hint_count,
            },
        }
    return result


def summarize_model(model_key: str, dataset: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """1モデル・1 splitの評価JSONLを読み、schemaとmanifest順を検証する。"""
    path = ROOT / "outputs" / f"multiasr-{dataset}-{model_key}-firstpass.jsonl"
    rows = read_jsonl(path)
    validate_ids(rows, [row["id"] for row in records], path)
    config = MODEL_CONFIG[model_key]
    if any(row["system"] != config["system"] for row in rows):
        raise ValueError(f"system名が異なる: {path}")
    hypotheses = {row["id"]: row["hyp"] for row in rows}
    return {
        "system": config["system"],
        "output": str(path),
        "term_accuracy": term_counts(records, hypotheses),
        "reading_aligned_cer": reading_aligned_cer(records, hypotheses),
        "latency_s": {
            "mean": statistics.fmean(row["latency_s"] for row in rows),
            "median": statistics.median(row["latency_s"] for row in rows),
            "p90": float(np.percentile([row["latency_s"] for row in rows], 90)),
        },
        "hypotheses": hypotheses,
    }


def evaluate() -> None:
    """全モデルを採点し、Haas単独baseline、モデル比較、選定結果を保存する。"""
    from voiceime.formatter.glossary import GlossaryIndex, load_glossary, load_term_list

    glossary_v1 = ASR_ROOT / "data/glossary/glossary.jsonl"
    glossary_v2 = ASR_ROOT / "data/glossary/glossary-v2.jsonl"
    outputs: dict[str, Any] = {"datasets": {}, "conditions": {}}
    ranking: list[tuple[float, float, float, str]] = []
    for dataset in DATASETS:
        records = read_manifest(dataset)
        config = DATASETS[dataset]
        exclude_terms = load_term_list(config["exclude_file"])
        glossary = load_glossary(glossary_v1, glossary_v2, exclude_terms=exclude_terms)
        index = GlossaryIndex(glossary)
        haas_path = TWOPASS_ROOT / "outputs" / f"{config['haas_prefix']}-plain.jsonl"
        haas_rows = read_jsonl(haas_path)
        validate_ids(haas_rows, [row["id"] for row in records], haas_path)
        haas_hypotheses = {row["id"]: row["hyp"] for row in haas_rows}
        condition = {
            "excluded_term_file": str(config["exclude_file"]),
            "excluded_term_count": len(exclude_terms),
            "candidate_surface_count": len(glossary),
            "haas_only_selection": selection_metrics(records, haas_hypotheses, None, index),
            "models": {},
        }
        for model_key in MODEL_CONFIG:
            model_result = summarize_model(model_key, dataset, records)
            selected = selection_metrics(
                records, haas_hypotheses, model_result["hypotheses"], index
            )
            model_result["combined_selection"] = selected
            condition["models"][MODEL_CONFIG[model_key]["system"]] = {
                key: value for key, value in model_result.items() if key != "hypotheses"
            }
            if dataset == "val":
                ranking.append(
                    (
                        selected["16"]["hints_after_asr_caps"]["term_instance_hit_rate"],
                        model_result["term_accuracy"]["normalized_surface_accuracy"],
                        -model_result["reading_aligned_cer"]["rate"],
                        model_key,
                    )
                )
        outputs["conditions"][dataset] = {
            "excluded_term_file_sha256": __import__("hashlib").sha256(
                config["exclude_file"].read_bytes()
            ).hexdigest(),
            "excluded_term_count": len(exclude_terms),
            "candidate_surface_count": len(glossary),
            "haas_only_selection": condition["haas_only_selection"],
        }
        outputs["datasets"][dataset] = condition["models"]
        baseline = condition["haas_only_selection"]["16"]["hints_after_asr_caps"]
        expected = (
            {"target_term_instances_selected": 319, "target_term_instances": 500}
            if dataset == "test-novel"
            else {"target_term_instance_rate": 0.843}
        )
        outputs["conditions"][dataset]["provided_haas_baseline"] = {
            "expected": expected,
            "measured_actual_hint_selection": baseline,
            "matches_test_novel_exact": (
                dataset != "test-novel"
                or baseline["target_term_instances_selected"] == 319
            ),
            "val_rate_difference_from_prompt": (
                baseline["term_instance_hit_rate"] - 0.843 if dataset == "val" else None
            ),
        }
    best = max(ranking, key=lambda item: item[:3])
    best_key = best[3]
    outputs["best_model"] = {
        "model_key": best_key,
        "system": MODEL_CONFIG[best_key]["system"],
        "selection_rule": "val target term instance hit rate among actual Haas hints after the 16-term/240-character cap using selector cap 16; tie break by normalized surface term accuracy then lower reading-aligned CER; remaining exact ties keep model iteration order qwen06, qwen17, whisper",
        "val_rank_tuple": {
            "actual_hint_target_term_instance_hit_rate_at_16": best[0],
            "normalized_surface_term_accuracy": best[1],
            "negative_reading_aligned_cer": best[2],
        },
    }
    output_path = ROOT / "outputs/metrics.json"
    output_path.write_text(json.dumps(outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "outputs/best-model.json").write_text(
        json.dumps(outputs["best_model"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for dataset, data in outputs["conditions"].items():
        baseline = data["haas_only_selection"]["16"]["hints_after_asr_caps"]
        print(
            f"baseline {dataset} actual hints: terms="
            f"{baseline['target_term_instances_selected']}/{baseline['target_term_instances']} "
            f"({baseline['term_instance_hit_rate']:.1%}), rows="
            f"{baseline['rows_with_any_correct_target']}/{baseline['rows']} "
            f"({baseline['row_hit_rate']:.1%})",
            flush=True,
        )
    print(f"best by validation={MODEL_CONFIG[best_key]['system']}", flush=True)


class SpeechWorker:
    """speech.cpp CUDA encoder・CPU decode workerを一つの子プロセスとして管理する。"""

    def __init__(self, threads: int) -> None:
        command = [
            "voiceime-r3multi-haas-twopass-worker",
            "worker",
            str(SPEECH_MODEL),
            "--device",
            "gpu",
            "--threads",
            str(threads),
            "--no-warmup",
            "--decode-on-cpu",
        ]
        self.process = subprocess.Popen(
            command,
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
        """workerからJSON応答を一件読む。"""
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"speech.cpp workerが終了した: rc={self.process.poll()}")
        return json.loads(line)

    def transcribe(self, audio: np.ndarray, hints: list[Term] | None) -> Transcription:
        """16kHz音声をPCMへ変換し、Haasに最大16語・240字のヒントを渡す。"""
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
                    "pcm": __import__("base64").b64encode(pcm).decode("ascii"),
                }
            )
            + "\n"
        )
        request: dict[str, Any] = {"type": "transcribe", "id": request_id, "sample_rate": SAMPLE_RATE}
        if hints:
            keywords = format_keywords(hints)
            if keywords:
                request["keywords"] = keywords
        self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        while True:
            message = self._read_message()
            if message.get("id") != request_id or message.get("type") == "progress":
                continue
            if message.get("type") != "end":
                raise RuntimeError(f"speech.cpp workerの認識応答が不正: {message}")
            return Transcription(text=message["text"])

    def close(self) -> None:
        """workerを正常終了させ、終了しない場合だけ停止する。"""
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


def run_twopass(best_model_key: str, workers: int, threads: int) -> None:
    """valで選んだASRとの合併選択でHaas two-passとformatter用語JSONLを作る。"""
    from voiceime.asr.systems import MODELS, asr_hint_format
    from voiceime.engine import (
        SEGMENT_MERGE_MIN_READING_SIMILARITY,
        asr_hints,
        merge_two_pass_text,
    )
    from voiceime.formatter.glossary import GlossaryIndex, load_glossary, load_term_list, select_glossary

    visible = assigned_gpu()
    if not SPEECH.is_file() or not SPEECH_MODEL.is_file():
        raise FileNotFoundError("speech.cpp CUDA executableまたはHaas Q8_0 GGUFがない")
    model_config = MODEL_CONFIG[best_model_key]
    glossary_v1 = ASR_ROOT / "data/glossary/glossary.jsonl"
    glossary_v2 = ASR_ROOT / "data/glossary/glossary-v2.jsonl"
    outputs_dir = ROOT / "outputs"
    for dataset, dataset_config in DATASETS.items():
        records = read_manifest(dataset)
        exclude_terms = load_term_list(dataset_config["exclude_file"])
        glossary = load_glossary(glossary_v1, glossary_v2, exclude_terms=exclude_terms)
        index = GlossaryIndex(glossary)
        by_surface = {entry.surface: entry for entry in glossary}
        best_rows = read_jsonl(
            outputs_dir / f"multiasr-{dataset}-{best_model_key}-firstpass.jsonl"
        )
        validate_ids(best_rows, [row["id"] for row in records], outputs_dir / f"multiasr-{dataset}-{best_model_key}-firstpass.jsonl")
        multilingual = {row["id"]: row for row in best_rows}
        haas_path = TWOPASS_ROOT / "outputs" / f"{dataset_config['haas_prefix']}-plain.jsonl"
        haas_rows = read_jsonl(haas_path)
        validate_ids(haas_rows, [row["id"] for row in records], haas_path)
        haas = {row["id"]: row for row in haas_rows}
        haas_trace_path = TWOPASS_ROOT / "outputs" / f"{dataset_config['haas_prefix']}-trace.jsonl"
        haas_trace = {row["id"]: row for row in read_jsonl(haas_trace_path)}
        if set(haas_trace) != set(haas):
            raise ValueError(f"既存Haas traceとplainのidが異なる: {dataset}")
        hint_format = asr_hint_format(MODELS[SYSTEM_HAAS])
        prefix = f"haas-plus-{best_model_key}-{dataset}"
        trace_path = outputs_dir / f"{prefix}-trace.jsonl"
        plain_path = outputs_dir / f"{prefix}-plain.jsonl"
        merged_path = outputs_dir / f"{prefix}-segment-merge.jsonl"
        glossary_path = outputs_dir / f"formatter-glossary-{best_model_key}-{dataset}.jsonl"
        expected_ids = [row["id"] for row in records]
        old_rows = read_partial(trace_path, set(expected_ids))
        trace_rows = old_rows.copy()
        todo: Queue[dict[str, Any]] = Queue()
        for record in records:
            if record["id"] not in old_rows:
                todo.put(record)
        lock = threading.Lock()
        errors: list[str] = []
        done = 0
        started = time.perf_counter()
        print(
            f"start twopass dataset={dataset} rows={len(records)} already={len(old_rows)} "
            f"workers={workers} threads={threads} gpu={visible} best={model_config['system']}",
            flush=True,
        )

        def work() -> None:
            """一つのspeech.cpp childを保有し、割り当てられた発話を処理する。"""
            nonlocal done
            worker = SpeechWorker(threads)
            try:
                while True:
                    try:
                        record = todo.get_nowait()
                    except Empty:
                        return
                    record_id = record["id"]
                    first_row = haas[record_id]
                    multi_row = multilingual[record_id]
                    combined_text = first_row["hyp"] + "\n" + multi_row["hyp"]
                    candidates16 = select_glossary(combined_text, index, max_entries=16)
                    hints = asr_hints(candidates16, hint_format) or []
                    hinted_entries = [by_surface[hint.surface] for hint in hints if hint.surface in by_surface]
                    audio = load_audio(dataset_config["audio_root"] / record["audio_path"])
                    second_started = time.perf_counter()
                    second = worker.transcribe(audio, hints or None)
                    second_latency = time.perf_counter() - second_started
                    merged = merge_two_pass_text(first_row["hyp"], second.text, hinted_entries)
                    trace_row = {
                        "id": record_id,
                        "dataset": dataset,
                        "system": f"{SYSTEM_HAAS}+twopass+{model_config['system']}",
                        "stage": "asr",
                        "two_pass_policy": "segment-merge",
                        "merge_min_reading_similarity": SEGMENT_MERGE_MIN_READING_SIMILARITY,
                        "speaker": record.get("speaker"),
                        "haas_first_pass_hyp": first_row["hyp"],
                        "haas_first_pass_latency_s": first_row["latency_s"],
                        "multilingual_first_pass_system": multi_row["system"],
                        "multilingual_first_pass_hyp": multi_row["hyp"],
                        "multilingual_first_pass_latency_s": multi_row["latency_s"],
                        "selection_text": combined_text,
                        "selected_candidates_16": [asdict(entry) for entry in candidates16],
                        "asr_hints_after_engine_caps": [asdict(hint) for hint in hints],
                        "second_pass_raw_hyp": second.text,
                        "second_pass_latency_s": second_latency,
                        "segment_merge_hyp": merged.text,
                        "merge_edits": [asdict(edit) for edit in merged.edits],
                    }
                    with lock:
                        trace_rows[record_id] = trace_row
                        with trace_path.open("a", encoding="utf-8") as trace_output:
                            trace_output.write(json.dumps(trace_row, ensure_ascii=False) + "\n")
                            trace_output.flush()
                        done += 1
                        if done % 100 == 0:
                            print(f"progress dataset={dataset} rows={done}/{len(records)} elapsed={time.perf_counter()-started:.0f}s", flush=True)
            except Exception as error:
                with lock:
                    errors.append(repr(error))
                raise
            finally:
                worker.close()

        with ThreadPoolExecutor(max_workers=min(workers, max(todo.qsize(), 1))) as pool:
            futures = [pool.submit(work) for _ in range(min(workers, todo.qsize()))]
            for future in as_completed(futures):
                future.result()
        if errors:
            raise RuntimeError(f"worker失敗: {errors}")
        if len(trace_rows) != len(records):
            raise RuntimeError(f"traceが未完了: {dataset}, rows={len(trace_rows)}/{len(records)}")
        ordered_trace = [trace_rows[record_id] for record_id in expected_ids]
        plain_rows = [
            {
                "id": row["id"],
                "system": SYSTEM_HAAS,
                "stage": "asr",
                "hyp": row["haas_first_pass_hyp"],
                "latency_s": row["haas_first_pass_latency_s"],
            }
            for row in ordered_trace
        ]
        merged_rows = [
            {
                "id": row["id"],
                "system": f"{SYSTEM_HAAS}+twopass+{model_config['system']}",
                "stage": "asr",
                "hyp": row["segment_merge_hyp"],
                "latency_s": row["haas_first_pass_latency_s"] + row["second_pass_latency_s"],
            }
            for row in ordered_trace
        ]
        glossary_rows = []
        for record in records:
            combined = haas[record["id"]]["hyp"] + "\n" + multilingual[record["id"]]["hyp"]
            selected20 = select_glossary(combined, index, max_entries=20)
            glossary_rows.append(
                {
                    "id": record["id"],
                    "system": f"combined-selection+{model_config['system']}",
                    "glossary": [
                        {"surface": entry.surface, "readings": list(entry.readings)}
                        for entry in selected20
                    ],
                }
            )
        write_jsonl(trace_path, ordered_trace)
        write_jsonl(plain_path, plain_rows)
        write_jsonl(merged_path, merged_rows)
        write_jsonl(glossary_path, glossary_rows)
        print(
            f"complete twopass dataset={dataset} rows={len(records)} "
            f"elapsed={time.perf_counter()-started:.1f}s outputs={plain_path},{merged_path},{trace_path},{glossary_path}",
            flush=True,
        )


def main() -> None:
    """選択したGPUキュージョブのサブコマンドを実行する。"""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--model", choices=tuple(MODEL_CONFIG), required=True)
    run_parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    run_parser.add_argument("--cpu-threads", type=int, default=16)
    subparsers.add_parser("evaluate")
    twopass_parser = subparsers.add_parser("twopass")
    twopass_parser.add_argument("--best-model", choices=tuple(MODEL_CONFIG), required=True)
    twopass_parser.add_argument("--workers", type=int, default=18)
    twopass_parser.add_argument("--threads", type=int, default=3)
    args = parser.parse_args()
    if args.command == "run":
        run_firstpass(args.model, args.device, args.cpu_threads)
    elif args.command == "evaluate":
        evaluate()
    else:
        run_twopass(args.best_model, args.workers, args.threads)


if __name__ == "__main__":
    main()
