#!/usr/bin/env python3
"""条件Dのval/test-novel出力が指定入力と一致するか監査する。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、各行がobjectであることを確認する。"""
    with path.open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: object以外の行があります")
    return rows


def index_rows(path: Path) -> dict[str, dict[str, Any]]:
    """ASR runと用語一覧をidで照合できるようにする。"""
    rows = read_rows(path)
    indexed = {row["id"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"{path}: idが重複しています")
    return indexed


def audit_split(
    split: str,
    result_path: Path,
    manifest_path: Path,
    first_path: Path,
    combined_path: Path,
    qwen_path: Path,
    glossary_path: Path,
) -> dict[str, int]:
    """モデルへ渡した3入力と用語一覧を照合し、一覧内外の正答数を集計する。"""
    manifest = read_rows(manifest_path)
    results = read_rows(result_path)
    expected_ids = [row["id"] for row in manifest]
    result_ids = [row.get("id") for row in results]
    if result_ids != expected_ids:
        raise ValueError(f"{split}: manifestと結果のIDまたは順序が一致しません")

    first_by_id = index_rows(first_path)
    combined_by_id = index_rows(combined_path)
    qwen_by_id = index_rows(qwen_path)
    glossary_by_id = index_rows(glossary_path)
    if any(set(source) != set(expected_ids) for source in (
        first_by_id, combined_by_id, qwen_by_id, glossary_by_id
    )):
        raise ValueError(f"{split}: manifestとASR/用語一覧のID集合が一致しません")

    counts = Counter()
    for gold, result in zip(manifest, results, strict=True):
        sample_id = gold["id"]
        expected_input = {
            "first_pass": first_by_id[sample_id]["hyp"],
            "second_pass": None,
            "combined_text": combined_by_id[sample_id]["hyp"],
            "qwen_hypothesis": qwen_by_id[sample_id]["hyp"] or None,
        }
        if result.get("input_text") != expected_input:
            raise ValueError(f"{split}/{sample_id}: FormatterInputが指定ASR runと一致しません")
        listed = [entry["surface"] for entry in glossary_by_id[sample_id]["glossary"]]
        if result.get("glossary") != listed:
            raise ValueError(f"{split}/{sample_id}: 用語一覧が指定runと一致しません")

        selected = set(listed)
        hypothesis = result.get("hyp")
        if not isinstance(hypothesis, str):
            raise ValueError(f"{split}/{sample_id}: hypがありません")
        for term, expected_count in Counter(gold.get("terms", [])).items():
            correct = min(expected_count, hypothesis.count(term))
            included = term in selected
            counts["terms"] += expected_count
            counts["correct"] += correct
            group = "included" if included else "excluded"
            counts[group] += expected_count
            counts[f"{group}_correct"] += correct

    if counts["included"] + counts["excluded"] != counts["terms"]:
        raise ValueError(f"{split}: 一覧内外の分母が一致しません")
    return {"rows": len(results), **dict(counts)}


def main() -> None:
    """val/test-novelを監査し、個々の本文を含めず集計値だけ保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--val-manifest", type=Path, required=True)
    parser.add_argument("--val-first", type=Path, required=True)
    parser.add_argument("--val-combined", type=Path, required=True)
    parser.add_argument("--val-qwen", type=Path, required=True)
    parser.add_argument("--val-glossary", type=Path, required=True)
    parser.add_argument("--test-novel-manifest", type=Path, required=True)
    parser.add_argument("--test-novel-first", type=Path, required=True)
    parser.add_argument("--test-novel-combined", type=Path, required=True)
    parser.add_argument("--test-novel-qwen", type=Path, required=True)
    parser.add_argument("--test-novel-glossary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = {
        "val": audit_split(
            "val", args.results_dir / "val-segment-merge.jsonl", args.val_manifest,
            args.val_first, args.val_combined, args.val_qwen, args.val_glossary,
        ),
        "test_novel": audit_split(
            "test-novel", args.results_dir / "test-novel-segment-merge.jsonl",
            args.test_novel_manifest, args.test_novel_first, args.test_novel_combined,
            args.test_novel_qwen, args.test_novel_glossary,
        ),
    }
    if args.output.exists():
        raise FileExistsError(f"既存の監査を上書きしません: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
