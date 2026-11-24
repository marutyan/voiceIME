"""発話ごとのCER差と対応のある不確実性を、文章を含めずに出力する。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from voiceime.eval.metrics import calculate_cer
from voiceime.formatter.style import apply_output_style


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLのobject行を読み、破損や重複を後段へ持ち越さない。"""
    with path.open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: 各行はJSON objectが必要です")
    return rows


def keyed_hypotheses(path: Path) -> dict[str, str]:
    """runをidで引ける形にし、重複・欠落・形式違反を検出する。"""
    hypotheses: dict[str, str] = {}
    for row in read_jsonl(path):
        sample_id, hypothesis = row.get("id"), row.get("hyp")
        if not isinstance(sample_id, str) or not isinstance(hypothesis, str):
            raise ValueError(f"{path}: idとhypは文字列が必要です")
        if sample_id in hypotheses:
            raise ValueError(f"{path}: idが重複しています: {sample_id}")
        hypotheses[sample_id] = apply_output_style(hypothesis)
    return hypotheses


def paired_cer(
    manifest_path: Path,
    baseline_path: Path,
    candidate_path: Path,
    output_path: Path,
    *,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    """同じ発話の文字誤りを比較し、符号検定と対応bootstrapをまとめる。"""
    manifest = read_jsonl(manifest_path)
    ids = [row.get("id") for row in manifest]
    if any(not isinstance(sample_id, str) for sample_id in ids):
        raise ValueError(f"{manifest_path}: idがありません")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{manifest_path}: idが重複しています")

    baseline = keyed_hypotheses(baseline_path)
    candidate = keyed_hypotheses(candidate_path)
    expected_ids = set(ids)
    if set(baseline) != expected_ids or set(candidate) != expected_ids:
        raise ValueError(
            "manifestと2系統のid集合が一致しません: "
            f"manifest={len(expected_ids)}, baseline={len(baseline)}, candidate={len(candidate)}"
        )

    references = [row["target_text"] for row in manifest]
    baseline_errors: list[int] = []
    candidate_errors: list[int] = []
    reference_lengths: list[int] = []
    per_utterance: list[dict[str, Any]] = []
    improved = worsened = tied = 0
    for sample_id, reference in zip(ids, references, strict=True):
        baseline_cer = calculate_cer([reference], [baseline[sample_id]])
        candidate_cer = calculate_cer([reference], [candidate[sample_id]])
        baseline_errors.append(int(baseline_cer["edit_errors"]))
        candidate_errors.append(int(candidate_cer["edit_errors"]))
        reference_lengths.append(int(baseline_cer["reference_characters"]))
        difference = float(candidate_cer["rate"]) - float(baseline_cer["rate"])
        improved += difference < 0
        worsened += difference > 0
        tied += difference == 0
        per_utterance.append(
            {
                "id": sample_id,
                "baseline_cer": baseline_cer["rate"],
                "candidate_cer": candidate_cer["rate"],
                "cer_delta": difference,
                "baseline_edit_errors": baseline_cer["edit_errors"],
                "candidate_edit_errors": candidate_cer["edit_errors"],
                "reference_characters": baseline_cer["reference_characters"],
            }
        )

    if any(length == 0 for length in reference_lengths):
        raise ValueError("CER bootstrapの正解文に空の行があります")
    total_reference_characters = sum(reference_lengths)
    point_difference = 100 * (
        sum(candidate_errors) - sum(baseline_errors)
    ) / total_reference_characters

    rng = np.random.default_rng(seed)
    draw_indices = rng.integers(0, len(ids), size=(bootstrap_samples, len(ids)))
    error_baseline = np.asarray(baseline_errors, dtype=np.int64)
    error_candidate = np.asarray(candidate_errors, dtype=np.int64)
    chars = np.asarray(reference_lengths, dtype=np.int64)
    sampled_chars = chars[draw_indices].sum(axis=1)
    sampled_delta = 100 * (
        error_candidate[draw_indices].sum(axis=1)
        - error_baseline[draw_indices].sum(axis=1)
    ) / sampled_chars
    lower, upper = np.percentile(sampled_delta, [2.5, 97.5], method="linear")

    non_ties = improved + worsened
    if non_ties:
        tail = sum(math.comb(non_ties, k) for k in range(min(improved, worsened) + 1))
        sign_test_p = min(1.0, 2 * tail / (2**non_ties))
    else:
        sign_test_p = 1.0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as target:
        for row in per_utterance:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "n": len(ids),
        "baseline_path": str(baseline_path),
        "candidate_path": str(candidate_path),
        "metric": "CER difference in percentage points; candidate minus baseline",
        "bootstrap": {
            "samples": bootstrap_samples,
            "seed": seed,
            "interval_95_percent_points": [float(lower), float(upper)],
            "point_difference_percent_points": point_difference,
        },
        "sign_test": {
            "improved": improved,
            "worsened": worsened,
            "ties": tied,
            "two_sided_exact_p": sign_test_p,
        },
        "per_utterance_path": str(output_path),
    }


def main() -> None:
    """引数を読み、JSON形式の対応比較を標準出力へ出す。"""
    parser = argparse.ArgumentParser(description="発話単位の対応CER比較")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--per-utterance", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samplesは1以上にしてください")
    summary = paired_cer(
        args.manifest,
        args.baseline,
        args.candidate,
        args.per_utterance,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
