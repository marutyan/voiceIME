"""faculty上でcheckpointを推論し、voiceime.eval互換のrun JSONLを保存する。"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import torch
from qwen_asr import Qwen3ASRModel


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """推論用JSONLを読み、1行1件のobjectを返す。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(value)
    return rows


def parse_model_spec(value: str) -> tuple[str, str]:
    """`name=path`指定を解析し、run名に使えない文字を拒否する。"""
    name, separator, path = value.partition("=")
    if not separator or not name or not path:
        raise ValueError(f"modelはname=path形式が必要です: {value}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError(f"run名に使えない文字があります: {name}")
    return name, path


def evaluate_model(
    model_name: str,
    model_path: str,
    rows: list[dict[str, Any]],
    output_dir: Path,
    batch_size: int,
) -> tuple[int, float]:
    """checkpointをbf16のbatch推論で評価し、完了したrunだけを確定する。"""
    model = Qwen3ASRModel.from_pretrained(
        model_path,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        max_inference_batch_size=batch_size,
    )
    model.model.eval()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{model_name}.jsonl"
    temporary_path = output_path.with_suffix(".jsonl.tmp")
    total_time = 0.0
    try:
        with torch.inference_mode(), temporary_path.open("w", encoding="utf-8") as output:
            for start in range(0, len(rows), batch_size):
                batch_rows = rows[start : start + batch_size]
                started = time.perf_counter()
                transcriptions = model.transcribe(
                    audio=[row["audio"] for row in batch_rows],
                    context=[row.get("prompt", "") for row in batch_rows],
                    language=["Japanese"] * len(batch_rows),
                )
                elapsed = time.perf_counter() - started
                total_time += elapsed
                for row, transcription in zip(
                    batch_rows, transcriptions, strict=True
                ):
                    result = {
                        "id": row["id"],
                        "system": model_name,
                        "stage": "e2e",
                        "hyp": transcription.text.strip(),
                    }
                    if batch_size == 1:
                        result["latency_s"] = elapsed
                    output.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    os.replace(temporary_path, output_path)
    del model
    gc.collect()
    torch.cuda.empty_cache()
    print(
        json.dumps(
            {
                "system": model_name,
                "rows": len(rows),
                "batch_size": batch_size,
                "elapsed_s": round(total_time, 3),
                "utterances_per_s": round(len(rows) / total_time, 3)
                if total_time > 0
                else None,
                "output": str(output_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return len(rows), total_time


def main() -> None:
    """指定checkpoint群を順番に評価する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--model", required=True, action="append")
    args = parser.parse_args()

    rows = read_jsonl(args.eval_file)
    if not rows:
        raise ValueError("evaluation JSONLが空です")
    if args.batch_size < 1:
        raise ValueError("batch-sizeは1以上である必要があります")
    for specification in args.model:
        model_name, model_path = parse_model_spec(specification)
        evaluate_model(model_name, model_path, rows, args.output_dir, args.batch_size)


if __name__ == "__main__":
    main()
