#!/usr/bin/env python3
"""main用語選択で実行したtest-novel評価の選択語別成績を集計する。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from audit_test_novel import (
    classify_missing_term,
    load_pool,
    make_prompt_line,
    read_jsonl,
    terms_for_row,
)


# 合成test-novelのmanifest、ASR結果、候補用語集をまとめた監査入力。
ROOT = Path(__file__).parent / "inputs" / "audit-source"
# 評価時のプロンプト定義を監査結果と入力書き出しに固定する。
PROMPT_MODULE = Path(__file__).resolve().parents[2] / "src" / "voiceime" / "formatter" / "prompt.py"
# 評価launcherと同じ順序で、各条件の出力を読む。
MODEL_NAMES = (
    "A",
    "B",
    "C",
    "B-2B",
    "B-clean",
    "B-drop0",
    "B-no-distractors",
)


def sha256(path: Path) -> str:
    """入力と結果の版を実験集計に固定する。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """test-novelの選択語別成績と、モデル入力の再現用JSONLを保存する。"""
    parser = argparse.ArgumentParser(description="main glossary selectorでのtest-novel選択語別集計")
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input-export", required=True, type=Path)
    parser.add_argument("--sft2-run", type=Path, help="SFT2の保存済みtest-novel出力。用語一覧順の照合に使う")
    args = parser.parse_args()

    manifest_path = ROOT / "test-novel.jsonl"
    glossary_paths = [ROOT / "glossary-v1.jsonl", ROOT / "glossary-v2.jsonl"]
    plain_path = ROOT / "a-plain.jsonl"
    accepted_path = ROOT / "a-segment-merge.jsonl"
    excluded = {
        line.strip()
        for line in (ROOT / "exclude-v2-83.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    pool, by_surface = load_pool(glossary_paths, excluded)
    manifest = read_jsonl(manifest_path)
    reference_ids = [row["id"] for row in manifest]
    if len(reference_ids) != 500 or len(set(reference_ids)) != 500:
        raise ValueError(f"test-novel manifestは重複のない500 IDが必要です: {len(reference_ids)}")
    first_pass = {row["id"]: row.get("hyp", "") for row in read_jsonl(plain_path)}
    accepted_second_pass = {row["id"]: row.get("hyp", "") for row in read_jsonl(accepted_path)}
    if list(first_pass) != reference_ids or list(accepted_second_pass) != reference_ids:
        raise ValueError("test-novelの1回目・採否後2回目とmanifestのID順が一致しません")
    sft2_by_id = None
    if args.sft2_run is not None:
        sft2_rows = read_jsonl(args.sft2_run)
        if [row.get("id") for row in sft2_rows] != reference_ids:
            raise ValueError("SFT2のtest-novel出力とmanifestのID順が一致しません")
        sft2_by_id = {row["id"]: row for row in sft2_rows}

    term_entries = {
        row["id"]: {entry["surface"]: entry for entry in row.get("glossary", [])}
        for row in manifest
    }
    stats_by_model: dict[str, dict] = {}
    rows_by_model: dict[str, list[dict]] = {}
    source_paths = [manifest_path, plain_path, accepted_path, *glossary_paths, ROOT / "exclude-v2-83.txt", PROMPT_MODULE]
    input_export_rows: list[dict] = []

    for model_name in MODEL_NAMES:
        result_path = args.results_root / model_name / "test-novel" / "test-novel-include-novel.jsonl"
        rows = read_jsonl(result_path)
        result_ids = [row.get("id") for row in rows]
        if result_ids != reference_ids:
            raise ValueError(f"{model_name}: manifestとtest-novel IDの順序が一致しません")
        rows_by_model[model_name] = rows

        stats = {
            "examples": len(rows),
            "terms": 0,
            "included": 0,
            "included_correct": 0,
            "excluded": 0,
            "excluded_correct": 0,
            "included_misses": Counter(),
            "selected_term_count": Counter(),
            "selected_entries_missing_from_pool": 0,
            "included_accuracy": None,
            "excluded_accuracy": None,
        }
        for manifest_row, result in zip(manifest, rows, strict=True):
            selected = result.get("glossary", [])
            input_export_rows.append({
                "model": model_name,
                "id": manifest_row["id"],
                "first_pass": first_pass[manifest_row["id"]],
                "accepted_second_pass": accepted_second_pass[manifest_row["id"]],
                "formatter_input": result.get("input_text", ""),
                "selected_glossary": selected,
                "selected_glossary_lines": [make_prompt_line(by_surface[surface]) for surface in selected],
            })
            selected_set = set(selected)
            stats["selected_term_count"][str(len(selected))] += 1
            stats["selected_entries_missing_from_pool"] += sum(surface not in by_surface for surface in selected)
            hypothesis = result.get("hyp", "")
            target_entries = term_entries[manifest_row["id"]]
            for term in terms_for_row(manifest_row):
                included = term in selected_set
                correct = hypothesis.count(term) > 0
                bucket = "included" if included else "excluded"
                stats["terms"] += 1
                stats[bucket] += 1
                stats[f"{bucket}_correct"] += int(correct)
                if included and not correct:
                    target = target_entries.get(term, {})
                    readings = target.get("readings", [])
                    if isinstance(readings, str):
                        readings = [readings]
                    stats["included_misses"][classify_missing_term(
                        manifest_row.get("target_text", ""), hypothesis, term, readings
                    )] += 1

        stats["included_accuracy"] = stats["included_correct"] / stats["included"] if stats["included"] else None
        stats["excluded_accuracy"] = stats["excluded_correct"] / stats["excluded"] if stats["excluded"] else None
        stats["included_misses"] = dict(stats["included_misses"])
        stats["selected_term_count"] = dict(stats["selected_term_count"])
        stats["glossary_pool_size"] = len(pool)
        stats_by_model[model_name] = stats
        source_paths.append(result_path)

    selector_match_vs_b = {
        model_name: {
            "glossary_exact_match": sum(
                row.get("glossary", []) == base.get("glossary", [])
                for row, base in zip(rows_by_model[model_name], rows_by_model["B"], strict=True)
            ),
            "formatter_input_exact_match": sum(
                row.get("input_text", "") == base.get("input_text", "")
                for row, base in zip(rows_by_model[model_name], rows_by_model["B"], strict=True)
            ),
        }
        for model_name in MODEL_NAMES
    }
    selector_match_vs_sft2 = None
    if sft2_by_id is not None:
        selector_match_vs_sft2 = {
            model_name: sum(
                result.get("glossary", []) == sft2_by_id[result["id"]].get("glossary", [])
                for result in rows_by_model[model_name]
            )
            for model_name in MODEL_NAMES
        }
        source_paths.append(args.sft2_run)
    summary = {
        "manifest": str(manifest_path),
        "manifest_count": len(manifest),
        "models": stats_by_model,
        "selector_match_vs_B": selector_match_vs_b,
        "selector_match_vs_SFT2": selector_match_vs_sft2,
        "input_export": str(args.input_export),
        "input_export_rows": len(input_export_rows),
        "prompt_source": str(PROMPT_MODULE),
        "source_sha256": {str(path): sha256(path) for path in source_paths},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.input_export.parent.mkdir(parents=True, exist_ok=True)
    args.input_export.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in input_export_rows),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
