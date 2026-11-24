"""manifestと複数の推論結果から評価表とJSONを出力する。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import soundfile as sf

from .metrics import (
    calculate_cer,
    calculate_filler_metrics,
    calculate_tag_metrics,
    calculate_term_accuracy,
    calculate_term_accuracy_split,
    count_inserted_terms,
    replace_glossary_surfaces_with_readings,
    summarize_latency,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、行番号を含むエラーで不正な入力を知らせる。"""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: JSONを読めません: {error.msg}"
                ) from error
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: 各行はJSON objectが必要です")
            rows.append(value)
    return rows


def _load_manifest(path: Path) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """manifestの必須項目を確認し、相対音声パスから長さを読む。"""
    rows = _read_jsonl(path)
    seen_ids: set[str] = set()
    durations: dict[str, float] = {}
    for row in rows:
        sample_id = row.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(f"{path}: manifestのidは空でない文字列が必要です")
        if sample_id in seen_ids:
            raise ValueError(f"{path}: manifestに重複idがあります: {sample_id}")
        seen_ids.add(sample_id)
        if not isinstance(row.get("target_text"), str):
            raise ValueError(f"{path}: {sample_id} のtarget_textがありません")
        if "audio_path" in row:
            if not isinstance(row["audio_path"], str):
                raise ValueError(f"{path}: {sample_id} のaudio_pathがありません")
            audio_path = path.parent / row["audio_path"]
            audio_info = sf.info(audio_path)
            durations[sample_id] = audio_info.frames / audio_info.samplerate
        fillers = row.get("fillers")
        if not isinstance(fillers, int) or isinstance(fillers, bool) or fillers < 0:
            raise ValueError(f"{path}: {sample_id} のfillersは0以上の整数が必要です")
        terms = row.get("terms", [])
        glossary = row.get("glossary", [])
        if not isinstance(terms, list) or not all(
            isinstance(term, str) for term in terms
        ):
            raise ValueError(f"{path}: {sample_id} のtermsは文字列の配列が必要です")
        if not isinstance(glossary, list) or not all(
            isinstance(entry, dict) for entry in glossary
        ):
            raise ValueError(f"{path}: {sample_id} のglossaryはobjectの配列が必要です")
        for entry in glossary:
            if not isinstance(entry.get("surface"), str):
                raise ValueError(f"{path}: {sample_id} のglossary.surfaceがありません")
            readings = entry.get("readings")
            if not isinstance(readings, list) or not all(
                isinstance(reading, str) for reading in readings
            ):
                raise ValueError(
                    f"{path}: {sample_id} のglossary.readingsは文字列の配列が必要です"
                )
        tags = row.get("tags", [])
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) for tag in tags
        ):
            raise ValueError(f"{path}: {sample_id} のtagsは文字列の配列が必要です")
    return rows, durations


def _duration_group(duration_s: float) -> str:
    """重複しない区間として音声長を5秒・15秒の境界で分類する。"""
    if duration_s <= 5:
        return "<=5s"
    if duration_s <= 15:
        return "5-15s"
    return ">15s"


def _rate(correct: int, total: int) -> float | None:
    """分母が0のとき未定義を維持してJSONのnullにする。"""
    return correct / total if total else None


def _load_unseen_terms(path: Path) -> set[str]:
    """1行1語のテキストファイルから見えない用語の集合を読み込む。"""
    text = path.read_text(encoding="utf-8")
    return {stripped for line in text.splitlines() if (stripped := line.strip())}


def _term_summary(
    correct: int, loose_correct: int, total: int, stage: str
) -> dict[str, int | float | None]:
    """用語正答率の件数・割合と、ASR時のみの緩い正答率をまとめる。"""
    return {
        "correct": correct,
        "total": total,
        "accuracy": _rate(correct, total),
        "loose_correct": loose_correct if stage == "asr" else None,
        "loose_accuracy": _rate(loose_correct, total) if stage == "asr" else None,
    }


def _evaluate_group(
    run_path: Path,
    system: str,
    stage: str,
    run_rows: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    durations: dict[str, float],
    unseen_terms: set[str] | None = None,
) -> dict[str, Any]:
    """1系統・1 stageの有効な出力を指標別に集計する。"""
    manifest_by_id = {row["id"]: row for row in manifest_rows}
    hypotheses: dict[str, dict[str, Any]] = {}
    unknown_ids = 0
    missing_hyp = 0
    duplicate_ids = 0
    invalid_latency = 0
    unknown_duration_rows = 0
    for row in run_rows:
        sample_id = row.get("id")
        if not isinstance(sample_id, str) or sample_id not in manifest_by_id:
            unknown_ids += 1
            continue
        hypothesis = row.get("hyp")
        if not isinstance(hypothesis, str):
            missing_hyp += 1
            continue
        if sample_id in hypotheses:
            duplicate_ids += 1
        hypotheses[sample_id] = row
        latency = row.get("latency_s")
        if (
            not isinstance(latency, (int, float))
            or isinstance(latency, bool)
            or not math.isfinite(float(latency))
            or latency < 0
        ):
            invalid_latency += 1

    evaluated_ids = [
        sample_id for sample_id in manifest_by_id if sample_id in hypotheses
    ]
    target_references = [
        manifest_by_id[sample_id]["target_text"] for sample_id in evaluated_ids
    ]
    predicted_texts = [hypotheses[sample_id]["hyp"] for sample_id in evaluated_ids]
    raw_cer = None
    if stage == "asr":
        spoken_references = []
        aligned_references = []
        aligned_hypotheses = []
        for sample_id, hypothesis in zip(
            evaluated_ids, predicted_texts, strict=True
        ):
            manifest_row = manifest_by_id[sample_id]
            spoken_text = manifest_row.get("spoken_text")
            if not isinstance(spoken_text, str):
                raise ValueError(f"{run_path}: {sample_id} のspoken_textがありません")
            glossary = manifest_row.get("glossary", [])
            spoken_references.append(spoken_text)
            aligned_references.append(
                replace_glossary_surfaces_with_readings(spoken_text, glossary)
            )
            aligned_hypotheses.append(
                replace_glossary_surfaces_with_readings(hypothesis, glossary)
            )
        raw_cer = calculate_cer(spoken_references, predicted_texts)
        cer = calculate_cer(aligned_references, aligned_hypotheses)
    else:
        cer = calculate_cer(target_references, predicted_texts)

    exact_terms = 0
    loose_terms = 0
    term_total = 0
    unseen_exact = 0
    unseen_loose = 0
    unseen_total = 0
    seen_exact = 0
    seen_loose = 0
    seen_total = 0
    inserted_terms = 0
    tag_samples = []
    for sample_id in evaluated_ids:
        manifest_row = manifest_by_id[sample_id]
        hypothesis = hypotheses[sample_id]["hyp"]
        row_terms = manifest_row.get("terms", [])
        row_glossary = manifest_row.get("glossary", [])
        term_metrics = calculate_term_accuracy(row_terms, row_glossary, hypothesis)
        exact_terms += int(term_metrics["correct"])
        loose_terms += int(term_metrics["loose_correct"])
        term_total += int(term_metrics["total"])
        if unseen_terms is not None:
            split_metrics = calculate_term_accuracy_split(
                row_terms, row_glossary, hypothesis, unseen_terms
            )
            unseen_exact += int(split_metrics["unseen"]["correct"])
            unseen_loose += int(split_metrics["unseen"]["loose_correct"])
            unseen_total += int(split_metrics["unseen"]["total"])
            seen_exact += int(split_metrics["seen"]["correct"])
            seen_loose += int(split_metrics["seen"]["loose_correct"])
            seen_total += int(split_metrics["seen"]["total"])
        inserted_terms += count_inserted_terms(
            row_terms,
            row_glossary,
            hypothesis,
            spoken_text=(
                manifest_row["spoken_text"] if stage == "asr" else None
            ),
        )
        tag_samples.append(
            {
                "target_text": manifest_row["target_text"],
                "hyp": hypothesis,
                "tags": manifest_row.get("tags", []),
            }
        )

    filler_metrics = calculate_filler_metrics(
        target_references,
        predicted_texts,
        [int(row["fillers"]) for row in manifest_rows],
    )
    tag_metrics = calculate_tag_metrics(tag_samples)
    manifest_tag_counts: dict[str, int] = defaultdict(int)
    for row in manifest_rows:
        for tag in dict.fromkeys(row.get("tags", [])):
            manifest_tag_counts[tag] += 1
    for tag, manifest_count in manifest_tag_counts.items():
        if tag not in tag_metrics:
            tag_metrics[tag] = {
                "count": 0,
                "cer": calculate_cer([], []),
                "exact_matches": 0,
                "exact_match_rate": None,
                "suspected_responses": 0 if tag == "instruction_like" else None,
            }
        tag_metrics[tag]["manifest_count"] = manifest_count
    tag_metrics = {tag: tag_metrics[tag] for tag in manifest_tag_counts}

    latency_by_group: dict[str, list[float]] = {
        "<=5s": [],
        "5-15s": [],
        ">15s": [],
    }
    all_latencies: list[float] = []
    for sample_id in evaluated_ids:
        latency = hypotheses[sample_id].get("latency_s")
        if (
            isinstance(latency, (int, float))
            and not isinstance(latency, bool)
            and math.isfinite(float(latency))
            and latency >= 0
        ):
            value = float(latency)
            all_latencies.append(value)
            if sample_id in durations:
                latency_by_group[_duration_group(durations[sample_id])].append(value)
            else:
                unknown_duration_rows += 1

    missing_predictions = len(manifest_by_id) - len(evaluated_ids)
    terms_summary: dict[str, Any] = _term_summary(
        exact_terms, loose_terms, term_total, stage
    )
    if unseen_terms is not None:
        terms_summary["unseen"] = _term_summary(
            unseen_exact, unseen_loose, unseen_total, stage
        )
        terms_summary["seen"] = _term_summary(
            seen_exact, seen_loose, seen_total, stage
        )
    return {
        "run": str(run_path),
        "system": system,
        "stage": stage,
        "utterances": {
            "manifest": len(manifest_rows),
            "evaluated": len(evaluated_ids),
            "missing_predictions": missing_predictions,
        },
        "cer": cer,
        "raw_cer": raw_cer,
        "terms": terms_summary,
        "inserted_terms": {
            "count": inserted_terms,
            "basis": (
                "spoken_textに含まれるglossaryのsurface/readings"
                if stage == "asr"
                else "target_textのterms"
            ),
        },
        "fillers": filler_metrics,
        "tags": tag_metrics,
        "latency": {
            "all": summarize_latency(all_latencies),
            "duration_groups": {
                group: summarize_latency(values)
                for group, values in latency_by_group.items()
            },
            "unknown_duration_rows": unknown_duration_rows,
            "invalid_latency_rows": invalid_latency,
        },
        "warnings": {
            "unknown_ids": unknown_ids,
            "missing_hyp": missing_hyp,
            "duplicate_ids": duplicate_ids,
        },
    }


def _evaluate_run(
    run_path: Path,
    manifest_rows: list[dict[str, Any]],
    durations: dict[str, float],
    unseen_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    """run JSONLをsystemとstageごとに分け、除外行も警告対象にする。"""
    run_rows = _read_jsonl(run_path)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    manifest_ids = {row["id"] for row in manifest_rows}
    unknown_ids = 0
    missing_hyp = 0
    for row in run_rows:
        sample_id = row.get("id")
        known_id = isinstance(sample_id, str) and sample_id in manifest_ids
        if not known_id:
            unknown_ids += 1
        if not isinstance(row.get("hyp"), str):
            missing_hyp += 1
            continue
        if not known_id:
            continue
        system_value = row.get("system")
        system = system_value if isinstance(system_value, str) else run_path.stem
        stage_value = row.get("stage")
        stage = stage_value if isinstance(stage_value, str) else "unknown"
        groups[(system, stage)].append(row)

    if unknown_ids or missing_hyp:
        print(
            f"warning: {run_path}: manifestにないid={unknown_ids}, hyp欠落={missing_hyp}",
            file=sys.stderr,
        )
    if not groups:
        groups[(run_path.stem, "unknown")] = []

    results = []
    for (system, stage), rows in groups.items():
        result = _evaluate_group(
            run_path,
            system,
            stage,
            rows,
            manifest_rows,
            durations,
            unseen_terms=unseen_terms,
        )
        result["warnings"]["unknown_ids"] = unknown_ids
        result["warnings"]["missing_hyp"] = missing_hyp
        if result["utterances"]["missing_predictions"]:
            print(
                f"warning: {run_path} ({system}/{stage}): "
                f"manifestの未予測id={result['utterances']['missing_predictions']}",
                file=sys.stderr,
            )
        if result["warnings"]["duplicate_ids"]:
            print(
                f"warning: {run_path} ({system}/{stage}): "
                f"重複id={result['warnings']['duplicate_ids']}（最後のhypを採用）",
                file=sys.stderr,
            )
        if result["latency"]["invalid_latency_rows"]:
            print(
                f"warning: {run_path} ({system}/{stage}): "
                f"latency_s不正={result['latency']['invalid_latency_rows']}",
                file=sys.stderr,
            )
        if result["latency"]["unknown_duration_rows"]:
            print(
                f"warning: {run_path} ({system}/{stage}): "
                "音声長不明のため音声長別遅延集計から除外="
                f"{result['latency']['unknown_duration_rows']}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _format_rate(
    value: float | None,
    numerator: int | None = None,
    denominator: int | None = None,
) -> str:
    """Markdown表で割合と分子・分母を読みやすく表示する。"""
    if value is None:
        return "—"
    rate = f"{value:.2%}"
    if numerator is None or denominator is None:
        return rate
    return f"{numerator}/{denominator} ({rate})"


def _format_cer(cer: dict[str, Any] | None) -> str:
    """CERと置換・挿入・削除の内訳を表セル向けに整える。"""
    if cer is None or cer["rate"] is None:
        return "—"
    return (
        f"{cer['edit_errors']}/{cer['reference_characters']} ({cer['rate']:.2%}; "
        f"置換 {cer['substitutions']}、挿入 {cer['insertions']}、削除 {cer['deletions']})"
    )


def _format_seconds(value: float | None) -> str:
    """遅延値を秒単位のMarkdown表示へ整える。"""
    return "—" if value is None else f"{value:.3f}"


def _markdown_table(results: list[dict[str, Any]]) -> str:
    """全体指標と音声長別遅延をMarkdown表にする。"""
    headers = [
        "系統",
        "stage",
        "件数",
        "CER（ASRは読み揃え、E2Eはtarget）",
        "読み揃え前CER（ASR）",
        "用語正答率",
        "緩い正答率（ASR）",
        "話していない用語の挿入数"
        "（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準）",
        "フィラー残存率",
        "遅延中央値 / p90 (秒)",
        "長さ不明で音声長別遅延から除外",
        "≤5秒 中央値 / p90",
        "5–15秒 中央値 / p90",
        ">15秒 中央値 / p90",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for result in results:
        latency = result["latency"]
        groups = latency["duration_groups"]
        cer = result["cer"]
        terms = result["terms"]
        fillers = result["fillers"]
        system = str(result["system"]).replace("|", "\\|")
        lines.append(
            "| "
            + " | ".join(
                [
                    system,
                    str(result["stage"]),
                    f"{result['utterances']['evaluated']}/{result['utterances']['manifest']}",
                    _format_cer(cer),
                    _format_cer(result["raw_cer"]),
                    _format_rate(
                        terms["accuracy"], terms["correct"], terms["total"]
                    ),
                    _format_rate(
                        terms["loose_accuracy"],
                        terms["loose_correct"],
                        terms["total"],
                    )
                    if result["stage"] == "asr"
                    else "—",
                    str(result["inserted_terms"]["count"]),
                    _format_rate(
                        fillers["residual_rate"],
                        fillers["residual_count"],
                        fillers["manifest_count"],
                    ),
                    f"{_format_seconds(latency['all']['median_s'])} / {_format_seconds(latency['all']['p90_s'])}",
                    str(latency["unknown_duration_rows"]),
                    f"{_format_seconds(groups['<=5s']['median_s'])} / {_format_seconds(groups['<=5s']['p90_s'])}",
                    f"{_format_seconds(groups['5-15s']['median_s'])} / {_format_seconds(groups['5-15s']['p90_s'])}",
                    f"{_format_seconds(groups['>15s']['median_s'])} / {_format_seconds(groups['>15s']['p90_s'])}",
                ]
            )
            + " |"
        )

    if any("unseen" in result["terms"] for result in results):
        lines.extend(
            [
                "",
                "用語正答率（見えない用語 / それ以外）",
                "| 系統 | stage | 全体 | 見えない用語 | それ以外 | 緩い正答率：見えない用語（ASR） | 緩い正答率：それ以外（ASR） |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for result in results:
            terms = result["terms"]
            unseen = terms.get("unseen")
            seen = terms.get("seen")
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(result["system"]).replace("|", "\\|"),
                        str(result["stage"]),
                        _format_rate(
                            terms["accuracy"], terms["correct"], terms["total"]
                        ),
                        _format_rate(
                            unseen["accuracy"], unseen["correct"], unseen["total"]
                        )
                        if unseen is not None
                        else "—",
                        _format_rate(seen["accuracy"], seen["correct"], seen["total"])
                        if seen is not None
                        else "—",
                        _format_rate(
                            unseen["loose_accuracy"],
                            unseen["loose_correct"],
                            unseen["total"],
                        )
                        if unseen is not None and result["stage"] == "asr"
                        else "—",
                        _format_rate(
                            seen["loose_accuracy"],
                            seen["loose_correct"],
                            seen["total"],
                        )
                        if seen is not None and result["stage"] == "asr"
                        else "—",
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "タグ別集計",
            "| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for result in results:
        for tag, metrics in result["tags"].items():
            exact_rate = _format_rate(
                metrics["exact_match_rate"],
                metrics["exact_matches"],
                metrics["count"],
            )
            if tag == "no_change":
                exact_rate += "（無変更の保持）"
            elif tag == "self_correction":
                exact_rate += "（言い直しの正答率）"
            suspected = (
                str(metrics["suspected_responses"])
                if tag == "instruction_like"
                else "—"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(result["system"]).replace("|", "\\|"),
                        str(result["stage"]),
                        tag,
                        f"{metrics['count']}/{metrics['manifest_count']}",
                        _format_cer(metrics["cer"]),
                        exact_rate,
                        suspected,
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI引数を読み、Markdown表とJSONを標準出力へ出す。"""
    parser = argparse.ArgumentParser(description="音声入力モデルの評価結果を集計します")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--runs",
        required=True,
        action="append",
        nargs="+",
        type=Path,
        help="比較するrun JSONL。複数指定と複数パスのまとめ指定に対応します",
    )
    parser.add_argument(
        "--unseen-terms",
        type=Path,
        default=None,
        help="見えない用語の一覧ファイル（1行1語）。指定すると用語正答率を見えない用語とそれ以外に分けて出します",
    )
    args = parser.parse_args(argv)
    run_paths = [path for group in args.runs for path in group]
    manifest_rows, durations = _load_manifest(args.manifest)
    unseen_terms = (
        _load_unseen_terms(args.unseen_terms) if args.unseen_terms is not None else None
    )
    results = []
    for run_path in run_paths:
        results.extend(
            _evaluate_run(
                run_path, manifest_rows, durations, unseen_terms=unseen_terms
            )
        )

    report: dict[str, Any] = {
        "manifest": str(args.manifest),
        "results": results,
    }
    if args.unseen_terms is not None:
        report["unseen_terms"] = str(args.unseen_terms)
    print(_markdown_table(results))
    print("\nJSON:")
    print("```json")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
