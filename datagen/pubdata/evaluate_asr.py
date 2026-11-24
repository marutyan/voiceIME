#!/usr/bin/env python3
"""pub-evalのASR出力を、用語正答率・読み揃えCER・遅延で集計する。"""

from __future__ import annotations

import argparse
import json
import math
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from voiceime.eval.metrics import (
    calculate_cer,
    calculate_term_accuracy,
    replace_glossary_surfaces_with_readings,
    summarize_latency,
)


# 用語表記の違いだけで字幕一致率が変わらないよう、既存のASR CER規則で比較する。
def aligned_texts(row: dict[str, Any], hypothesis: str) -> tuple[str, str]:
    """manifestの用語集を使い、正解文と認識文の用語を読みへそろえる。"""
    glossary = row.get("glossary", [])
    reference = replace_glossary_surfaces_with_readings(row["spoken_text"], glossary)
    aligned_hypothesis = replace_glossary_surfaces_with_readings(hypothesis, glossary)
    return reference, aligned_hypothesis


# JSONLを1行ずつ読み、破損行があればpathと行番号を示して止める。
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを辞書の配列として読む。"""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(value)
    return rows


# 出力とmanifestの対応を検証し、行ごとの用語と遅延を評価できる形にする。
def index_results(path: Path, expected_ids: list[str]) -> dict[str, dict[str, Any]]:
    """IDの重複・欠落と、hypおよびlatency_sの型を検証して出力を索引化する。"""
    rows = read_jsonl(path)
    by_id = {row.get("id"): row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != set(expected_ids):
        raise ValueError(f"{path}: 結果IDがmanifestと一致しません")
    for row in rows:
        if not isinstance(row.get("hyp"), str):
            raise ValueError(f"{path}: {row['id']}のhypは文字列が必要です")
        latency = row.get("latency_s")
        if not isinstance(latency, (int, float)) or not math.isfinite(latency) or latency < 0:
            raise ValueError(f"{path}: {row['id']}のlatency_sは0以上の有限値が必要です")
    return by_id


# 字幕の英字表記とカタカナ表記を分け、同じ用語正答率関数で集計する。
def score_terms(
    manifest: list[dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, int | float | None]]:
    """英字字幕、カタカナ字幕、両方の用語について厳密・読み許容の正答数を返す。"""
    groups = {
        "all": lambda row: row.get("terms", []) + row.get("terms_katakana_in_caption", []),
        "english_caption": lambda row: row.get("terms", []),
        "katakana_caption": lambda row: row.get("terms_katakana_in_caption", []),
    }
    report: dict[str, dict[str, int | float | None]] = {}
    for group_name, select_terms in groups.items():
        exact_correct = 0
        loose_correct = 0
        total = 0
        for row in manifest:
            terms = select_terms(row)
            if not terms:
                continue
            score = calculate_term_accuracy(
                terms, row.get("glossary", []), results_by_id[row["id"]]["hyp"]
            )
            exact_correct += int(score["correct"])
            loose_correct += int(score["loose_correct"])
            total += int(score["total"])
        report[group_name] = {
            "exact_correct": exact_correct,
            "loose_correct": loose_correct,
            "total": total,
            "exact_accuracy": exact_correct / total if total else None,
            "loose_accuracy": loose_correct / total if total else None,
        }
    return report


# YODAS字幕は弱い正解なので、各発話のCERをそのまま除外判定にも使う。
def score_cer(
    manifest: list[dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
) -> dict[str, int | float | None]:
    """字幕と認識文を用語読みへそろえてコーパスCERを計算する。"""
    references: list[str] = []
    hypotheses: list[str] = []
    for row in manifest:
        reference, hypothesis = aligned_texts(row, results_by_id[row["id"]]["hyp"])
        references.append(reference)
        hypotheses.append(hypothesis)
    return calculate_cer(references, hypotheses)


# 用語集の語表記を正規化して、期待用語がASRのヒント候補に含まれる割合を出す。
def glossary_coverage(
    manifest: list[dict[str, Any]],
    glossary_paths: list[Path],
    excluded_terms_path: Path | None = None,
) -> dict[str, Any]:
    """用語集を統合・除外した後の語数と、manifest用語の収録率を返す。"""
    records: list[dict[str, Any]] = []
    for path in glossary_paths:
        records.extend(read_jsonl(path))
    excluded = set()
    if excluded_terms_path:
        excluded = {
            line.strip()
            for line in excluded_terms_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    raw_surfaces = {
        row["surface"]
        for row in records
        if isinstance(row.get("surface"), str) and row["surface"] not in excluded
    }
    surfaces = {unicodedata.normalize("NFKC", surface).casefold() for surface in raw_surfaces}
    counts = Counter(
        unicodedata.normalize("NFKC", term).casefold()
        for row in manifest
        for term in row.get("terms", []) + row.get("terms_katakana_in_caption", [])
    )
    total = sum(counts.values())
    covered = sum(count for surface, count in counts.items() if surface in surfaces)
    covered_unique = sum(surface in surfaces for surface in counts)
    return {
        "raw_entries": len(records),
        "unique_surfaces_after_exclusion": len(raw_surfaces),
        "excluded_terms": len(excluded),
        "expected_occurrences": total,
        "covered_occurrences": covered,
        "occurrence_coverage": covered / total if total else None,
        "unique_expected_surfaces": len(counts),
        "unique_covered_surfaces": covered_unique,
    }


# 除外IDは、用語の正誤を参照せず、v1の初回認識CERだけから作る。
def high_cer_exclusions(
    manifest: list[dict[str, Any]],
    first_pass_by_id: dict[str, dict[str, Any]],
    threshold: float,
) -> tuple[set[str], list[dict[str, Any]]]:
    """読み揃えCERが閾値を超えた区間と、その監査用情報を返す。"""
    excluded_ids: set[str] = set()
    exclusions: list[dict[str, Any]] = []
    for row in manifest:
        hypothesis = first_pass_by_id[row["id"]]["hyp"]
        reference, aligned_hypothesis = aligned_texts(row, hypothesis)
        score = calculate_cer([reference], [aligned_hypothesis])
        rate = score["rate"]
        if rate is None or rate <= threshold:
            continue
        excluded_ids.add(row["id"])
        exclusions.append(
            {
                "id": row["id"],
                "video_id": row.get("video_id"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "read_aligned_cer": rate,
                "edit_errors": score["edit_errors"],
                "reference_characters": score["reference_characters"],
                "spoken_text": row["spoken_text"],
                "first_pass_hypothesis": hypothesis,
                "exclusion_reason": f"初回認識の読み揃えCERが{threshold:.0%}を超えた",
            }
        )
    return excluded_ids, exclusions


# 除外前と除外後を同じ条件で並べ、pub-evalの補助指標を比較する。
def condition_metrics(
    manifest: list[dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
    excluded_ids: set[str],
) -> dict[str, Any]:
    """用語正答率、読み揃えCER、中央値・p90遅延を全区間と保持区間で返す。"""
    retained = [row for row in manifest if row["id"] not in excluded_ids]

    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        selected = [results_by_id[row["id"]] for row in rows]
        selected_by_id = {row["id"]: results_by_id[row["id"]] for row in rows}
        return {
            "segments": len(rows),
            "terms": score_terms(rows, selected_by_id),
            "read_aligned_cer": score_cer(rows, selected_by_id),
            "latency_s": summarize_latency([row["latency_s"] for row in selected]),
        }

    return {"all": summarize(manifest), "retained_after_cer_filter": summarize(retained)}


# 4種類の出力を同じmanifestに照合し、除外一覧と結果統計を保存する。
def evaluate(
    manifest_path: Path,
    output_paths: dict[str, Path],
    v1_glossary_path: Path,
    v2_glossary_path: Path,
    excluded_terms_path: Path,
    metrics_path: Path,
    exclusions_path: Path,
    high_cer_threshold: float = 0.50,
) -> dict[str, Any]:
    """ASR条件ごとの指標を出し、初回CERだけで定めた除外一覧を作成する。"""
    manifest = read_jsonl(manifest_path)
    expected_ids = [row["id"] for row in manifest]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("manifestに重複したidがあります")
    results = {
        name: index_results(path, expected_ids)
        for name, path in output_paths.items()
    }
    excluded_ids, exclusions = high_cer_exclusions(
        manifest, results["v1_plain"], high_cer_threshold
    )
    v1_coverage = glossary_coverage(manifest, [v1_glossary_path])
    legacy_coverage = glossary_coverage(
        manifest, [v1_glossary_path, v2_glossary_path], excluded_terms_path
    )

    report = {
        "split": manifest[0].get("split") if manifest else None,
        "segments": len(manifest),
        "expected_term_occurrences": sum(
            len(row.get("terms", [])) + len(row.get("terms_katakana_in_caption", []))
            for row in manifest
        ),
        "read_aligned_cer_for_caption_check": {
            "reference_output": "v1_plain",
            "threshold_exclusive": high_cer_threshold,
            "excluded_segments": len(excluded_ids),
            "retained_segments": len(manifest) - len(excluded_ids),
            "selection_uses_term_accuracy": False,
        },
        "glossary_coverage": {"v1": v1_coverage, "v1_plus_v2_excluding_terms": legacy_coverage},
        "conditions": {
            name: {
                "results_file": path.name,
                "metrics": condition_metrics(manifest, results[name], excluded_ids),
            }
            for name, path in output_paths.items()
        },
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    exclusions_path.parent.mkdir(parents=True, exist_ok=True)
    with exclusions_path.open("w", encoding="utf-8") as file:
        for row in exclusions:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return report


# CLI引数からfaculty出力を読み、集計JSONとCERによる除外JSONLを書き出す。
def main() -> None:
    """必要なmanifest、ASR出力、用語集を受け取り結果を保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plain-v1", type=Path, required=True)
    parser.add_argument("--two-pass-v1", type=Path, required=True)
    parser.add_argument("--plain-v1v2", type=Path, required=True)
    parser.add_argument("--two-pass-v1v2", type=Path, required=True)
    parser.add_argument("--v1-glossary", type=Path, required=True)
    parser.add_argument("--v2-glossary", type=Path, required=True)
    parser.add_argument("--excluded-terms", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--high-cer-threshold", type=float, default=0.50)
    args = parser.parse_args()
    paths = {
        "v1_plain": args.plain_v1,
        "v1_segment_merge": args.two_pass_v1,
        "v1v2_plain": args.plain_v1v2,
        "v1v2_segment_merge": args.two_pass_v1v2,
    }
    report = evaluate(
        args.manifest,
        paths,
        args.v1_glossary,
        args.v2_glossary,
        args.excluded_terms,
        args.metrics,
        args.exclusions,
        args.high_cer_threshold,
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
