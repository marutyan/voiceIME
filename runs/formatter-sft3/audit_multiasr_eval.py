#!/usr/bin/env python3
"""多言語ASR再評価の入力一致と用語一覧内正答を確認する。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


MODELS = ("B", "B-2B", "B-drop0-seed1", "B-2B-drop0")
VARIANTS = ("plain", "segment-merge")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、空行を無視する。"""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_by_id(path: Path) -> dict[str, dict[str, Any]]:
    """各入力のID重複を検査し、idをキーにする。"""
    rows = read_jsonl(path)
    mapped = {row["id"]: row for row in rows}
    if len(mapped) != len(rows):
        raise ValueError(f"{path}: idが重複しています")
    return mapped


def summarize_condition(
    result_path: Path,
    manifest: list[dict[str, Any]],
    first_by_id: dict[str, dict[str, Any]],
    second_by_id: dict[str, dict[str, Any]],
    selected_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """出力のID、入力本文、用語順を照合し、用語正答数を分けて数える。"""
    rows = read_jsonl(result_path)
    ids = [row.get("id") for row in rows]
    expected_ids = [row["id"] for row in manifest]
    if ids != expected_ids:
        raise ValueError(f"{result_path}: manifestとIDまたは順序が一致しません")

    totals = Counter()
    for gold, result in zip(manifest, rows, strict=True):
        sample_id = gold["id"]
        first = first_by_id[sample_id]["hyp"]
        second = second_by_id[sample_id]["hyp"]
        listed = [entry["surface"] for entry in selected_by_id[sample_id]["glossary"]]
        input_record = result.get("input_text")
        if not isinstance(input_record, dict):
            raise ValueError(f"{result_path}/{sample_id}: FormatterInputが保存されていません")
        if input_record.get("first_pass") != first or input_record.get("second_pass") != second:
            raise ValueError(f"{result_path}/{sample_id}: ASR入力が指定ファイルと一致しません")
        if input_record.get("combined_text") is not None or input_record.get("qwen_hypothesis") is not None:
            raise ValueError(f"{result_path}/{sample_id}: B形式以外の入力欄が設定されています")
        if result.get("glossary") != listed:
            raise ValueError(f"{result_path}/{sample_id}: 用語一覧が指定ファイルと一致しません")

        selected = set(listed)
        hypothesis = result.get("hyp", "")
        for term, count in Counter(gold.get("terms", [])).items():
            correct = min(count, hypothesis.count(term))
            included = term in selected
            totals["terms"] += count
            totals["correct"] += correct
            bucket = "included" if included else "excluded"
            totals[bucket] += count
            totals[f"{bucket}_correct"] += correct
    return dict(totals)


def main() -> None:
    """全モデル・splitの入力監査と一覧内外の用語成績を保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--val-manifest", type=Path, required=True)
    parser.add_argument("--test-novel-manifest", type=Path, required=True)
    parser.add_argument("--val-first", type=Path, required=True)
    parser.add_argument("--test-novel-first", type=Path, required=True)
    parser.add_argument("--val-glossary", type=Path, required=True)
    parser.add_argument("--test-novel-glossary", type=Path, required=True)
    parser.add_argument("--multiasr-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sources = {
        "val": (
            read_jsonl(args.val_manifest), load_by_id(args.val_first),
            load_by_id(args.val_glossary),
        ),
        "test-novel": (
            read_jsonl(args.test_novel_manifest), load_by_id(args.test_novel_first),
            load_by_id(args.test_novel_glossary),
        ),
    }
    results: dict[str, Any] = {}
    for model in MODELS:
        for split, (manifest, first, selected) in sources.items():
            for variant in VARIANTS:
                condition = f"{model}/{split}-qwen-{variant}"
                second = load_by_id(args.multiasr_dir / f"haas-plus-qwen06-{split}-{variant}.jsonl")
                results[condition] = summarize_condition(
                    args.results_root / model / "combined" / f"{split}-qwen-{variant}.jsonl",
                    manifest,
                    first,
                    second,
                    selected,
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
