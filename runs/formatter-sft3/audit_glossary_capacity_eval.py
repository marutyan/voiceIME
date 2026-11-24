#!/usr/bin/env python3
"""用語一覧上限の評価で、モデル入力・一覧・一覧内正答を照合する。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


VARIANTS = tuple(
    f"max{limit}-haas-qwen{suffix}"
    for limit in (20, 32, 48)
    for suffix in ("", "-whisper")
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、各行がobjectであることを確認する。"""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: JSON object以外の行があります")
    return rows


def index_rows(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """JSONLの順序付きIDとID辞書を返し、重複IDを拒否する。"""
    rows = read_jsonl(path)
    ids = [row.get("id") for row in rows]
    if not all(isinstance(sample_id, str) and sample_id for sample_id in ids):
        raise ValueError(f"{path}: 空でない文字列IDが必要です")
    indexed = dict(zip(ids, rows, strict=True))
    if len(indexed) != len(rows):
        raise ValueError(f"{path}: IDが重複しています")
    return ids, indexed


def audit_split(
    name: str,
    manifest_path: Path,
    first_path: Path,
    combined_path: Path,
    qwen_path: Path,
    result_dir: Path,
    glossary_dir: Path,
) -> dict[str, Any]:
    """6条件のFormatterInputと用語一覧を確かめ、一覧内外の正答数を集計する。"""
    ids, manifest = index_rows(manifest_path)
    for label, path in (("1回目", first_path), ("結合文", combined_path), ("Qwen", qwen_path)):
        source_ids, _ = index_rows(path)
        if source_ids != ids:
            raise ValueError(f"{name}: {label}のIDまたは順序がmanifestと一致しません")
    _, first = index_rows(first_path)
    _, combined = index_rows(combined_path)
    _, qwen = index_rows(qwen_path)

    reports = {}
    for variant in VARIANTS:
        result_path = result_dir / f"{name}-{variant}.jsonl"
        glossary_path = glossary_dir / name / f"{variant}.jsonl"
        result_ids, results = index_rows(result_path)
        glossary_ids, glossaries = index_rows(glossary_path)
        if result_ids != ids or glossary_ids != ids:
            raise ValueError(f"{name}/{variant}: manifest、結果、一覧の順序が一致しません")

        counts = Counter()
        for sample_id in ids:
            result = results[sample_id]
            expected_input = {
                "first_pass": first[sample_id]["hyp"],
                "second_pass": None,
                "combined_text": combined[sample_id]["hyp"],
                "qwen_hypothesis": qwen[sample_id]["hyp"] or None,
            }
            if result.get("input_text") != expected_input:
                raise ValueError(f"{name}/{variant}/{sample_id}: D入力がASR runと一致しません")
            expected_surfaces = [entry["surface"] for entry in glossaries[sample_id]["glossary"]]
            if result.get("glossary") != expected_surfaces:
                raise ValueError(f"{name}/{variant}/{sample_id}: 整形モデルへ渡した一覧が異なります")
            if not isinstance(result.get("hyp"), str):
                raise ValueError(f"{name}/{variant}/{sample_id}: hypがありません")

            listed = set(expected_surfaces)
            hypothesis = result["hyp"]
            for term, expected_count in Counter(manifest[sample_id].get("terms", [])).items():
                correct = min(expected_count, hypothesis.count(term))
                included = term in listed
                counts["terms"] += expected_count
                counts["correct"] += correct
                bucket = "included" if included else "excluded"
                counts[bucket] += expected_count
                counts[f"{bucket}_correct"] += correct

        reports[variant] = {
            "rows": len(ids),
            "model_input_match": len(ids),
            "glossary_match": len(ids),
            "terms": counts["terms"],
            "correct": counts["correct"],
            "included": counts["included"],
            "included_correct": counts["included_correct"],
            "excluded": counts["excluded"],
            "excluded_correct": counts["excluded_correct"],
        }
    return reports


def main() -> None:
    """valとtest-novelの評価JSONLを照合し、行本文を含まない監査を保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--val-manifest", type=Path, required=True)
    parser.add_argument("--val-first", type=Path, required=True)
    parser.add_argument("--val-combined", type=Path, required=True)
    parser.add_argument("--val-qwen", type=Path, required=True)
    parser.add_argument("--test-novel-manifest", type=Path, required=True)
    parser.add_argument("--test-novel-first", type=Path, required=True)
    parser.add_argument("--test-novel-combined", type=Path, required=True)
    parser.add_argument("--test-novel-qwen", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--glossary-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = {
        "val": audit_split(
            "val", args.val_manifest, args.val_first, args.val_combined,
            args.val_qwen, args.results_dir, args.glossary_dir,
        ),
        "test_novel": audit_split(
            "test-novel", args.test_novel_manifest, args.test_novel_first,
            args.test_novel_combined, args.test_novel_qwen,
            args.results_dir, args.glossary_dir,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"監査結果を上書きしません: {args.output}")
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
