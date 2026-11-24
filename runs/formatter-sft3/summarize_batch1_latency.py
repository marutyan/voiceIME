#!/usr/bin/env python3
"""batch 1評価の1件ごとの整形時間を、行IDを残さず集計する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、1件ごとの評価記録を返す。"""
    with path.open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: JSON object以外の行があります")
    return rows


def sha256(path: Path) -> str:
    """集計元JSONLのSHA-256を返す。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    """全行がbatch 1であることを確認し、中央値とp90だけを保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_rows(args.input)
    if not rows or any(row.get("batch_size") != 1 for row in rows):
        raise ValueError("全行がbatch_size=1である必要があります")
    values = [row.get("format_latency_s") for row in rows]
    if not all(isinstance(value, (int, float)) and value >= 0 for value in values):
        raise ValueError("format_latency_sが不正です")
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    result = {
        "n": len(values),
        "batch_size": 1,
        "metric": "median per-item generation wall time; batch size 1",
        "median_format_latency_s": statistics.median(values),
        "p90_format_latency_s": p90,
        "mean_format_latency_s": statistics.mean(values),
        "input_sha256": sha256(args.input),
    }
    if args.output.exists():
        raise FileExistsError(f"既存の集計を上書きしません: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
