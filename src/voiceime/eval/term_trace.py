"""用語の失敗をASR候補選択、two-pass、整形の段階へ分けて集計する。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from voiceime.engine import (
    SEGMENT_MERGE_MIN_READING_SIMILARITY,
    asr_hints,
    merge_two_pass_text,
)
from voiceime.formatter.glossary import (
    DEFAULT_MIN_SCORE,
    GlossaryEntry,
    entry_from_record,
    load_glossary,
    normalize_kana,
    score_entry_in_text,
    score_entry_readings,
    select_glossary,
    to_katakana,
)

from .metrics import (
    calculate_cer,
    calculate_term_accuracy,
    replace_glossary_surfaces_with_readings,
)

_KANA_RUN_PATTERN = re.compile(r"[\u30a1-\u30ff\u31f0-\u31ff]+")
_TRACE_FIELDS = (
    "id",
    "occurrence",
    "term",
    "readings",
    "first_pass",
    "closest_reading",
    "closest_reading_distance",
    "first_pass_reading_score",
    "first_pass_reading_near",
    "selected_candidates",
    "hint_terms",
    "gold_candidate_selected",
    "first_pass_exact",
    "two_pass",
    "two_pass_exact",
    "two_pass_broke_first_pass_correct",
    "two_pass_reading_distance",
    "two_pass_moved_farther_from_reading",
    "formatted",
    "formatted_exact",
    "formatter_fixed",
    "formatter_broke",
    "format_input_matches_two_pass",
    "final_failure_cause",
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


def _index_by_id(rows: list[dict[str, Any]], path: Path) -> dict[str, dict[str, Any]]:
    """idの重複を拒否し、JSONL行を発話idから引けるようにする。"""
    indexed: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(rows, start=1):
        sample_id = row.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(f"{path}:{line_number}: idは空でない文字列が必要です")
        if sample_id in indexed:
            raise ValueError(f"{path}:{line_number}: idが重複しています: {sample_id}")
        indexed[sample_id] = row
    return indexed


def _readings_for_term(
    row: dict[str, Any], term: str, glossary_by_surface: dict[str, GlossaryEntry]
) -> tuple[str, ...]:
    """manifestの対象発話に記録された読みを優先し、無ければ全体用語集を使う。"""
    matching = [
        entry_from_record(record)
        for record in row.get("glossary", [])
        if record.get("surface") == term
    ]
    readings = tuple(
        dict.fromkeys(reading for entry in matching for reading in entry.readings)
    )
    if readings:
        return readings
    entry = glossary_by_surface.get(term)
    return entry.readings if entry is not None else ()


def _katakana_runs(text: str) -> list[str]:
    """ひらがな・全角英数を揃え、読みの距離を測れる仮名区間を返す。"""
    normalized = to_katakana(unicodedata.normalize("NFKC", text))
    return [
        value
        for match in _KANA_RUN_PATTERN.finditer(normalized)
        if (value := normalize_kana(match.group()))
    ]


def _minimum_substring_distance(reading: str, text_run: str) -> int:
    """読み全体と、仮名区間内の最も近い連続部分とのLevenshtein距離を返す。"""
    if not reading:
        return 0
    previous = [0] * (len(text_run) + 1)
    for reading_index, reading_char in enumerate(reading, start=1):
        current = [reading_index] + [0] * len(text_run)
        for text_index, text_char in enumerate(text_run, start=1):
            current[text_index] = min(
                previous[text_index] + 1,
                current[text_index - 1] + 1,
                previous[text_index - 1] + (reading_char != text_char),
            )
        previous = current
    return min(previous[1:], default=len(reading))


def _closest_reading(
    readings: tuple[str, ...], text: str
) -> tuple[str | None, int | None]:
    """読み候補の順序を保ち、書き起こし内での最小距離を返す。"""
    runs = _katakana_runs(text)
    if not readings or not runs:
        return None, None
    best_reading: str | None = None
    best_distance: int | None = None
    for reading in readings:
        normalized_reading = normalize_kana(reading)
        if not normalized_reading:
            continue
        for run in runs:
            distance = _minimum_substring_distance(normalized_reading, run)
            if best_distance is None or distance < best_distance:
                best_reading = reading
                best_distance = distance
    return best_reading, best_distance


def _occurrence_flags(terms: list[str], text: str) -> list[bool]:
    """同じ正解語が複数回ある場合も、出力中の出現数だけを正答にする。"""
    observed = Counter({term: text.count(term) for term in set(terms)})
    seen: Counter[str] = Counter()
    flags = []
    for term in terms:
        seen[term] += 1
        flags.append(seen[term] <= observed[term])
    return flags


def _candidate_selection(
    text: str,
    entries: list[GlossaryEntry],
    hint_format: str,
) -> tuple[list[GlossaryEntry], list[str]]:
    """engineと同じ候補選択とASRヒント上限を適用する。"""
    selected = select_glossary(text, entries)
    hints = asr_hints(selected, hint_format) or []
    return selected, [hint.surface for hint in hints]


def _coverage_for_glossary(
    manifest_rows: list[dict[str, Any]],
    first_by_id: dict[str, dict[str, Any]],
    entries: list[GlossaryEntry],
    hint_format: str,
) -> dict[str, Any]:
    """1回目の文から作る実ヒントに正解surfaceが入る件数を数える。"""
    correct = total = 0
    samples_with_correct_hint: set[str] = set()
    for row in manifest_rows:
        first_text = first_by_id[row["id"]]["hyp"]
        _, hinted_surfaces = _candidate_selection(first_text, entries, hint_format)
        for term in row.get("terms", []):
            total += 1
            if term in hinted_surfaces:
                correct += 1
                samples_with_correct_hint.add(row["id"])
    return {
        "correct_candidate_occurrences": correct,
        "total_occurrences": total,
        "accuracy": correct / total if total else None,
        "utterances_with_any_correct_candidate": len(samples_with_correct_hint),
    }


def _failure_cause(
    *,
    first_correct: bool,
    second_correct: bool,
    formatted_correct: bool,
    gold_candidate_selected: bool,
    reading_score: float,
) -> str:
    """最終の用語誤りを、最初に確認できる失敗工程へ分類する。"""
    if formatted_correct:
        return "correct"
    if second_correct:
        return "formatter_broke_two_pass_correct"
    if first_correct:
        return "two_pass_broke_first_pass_correct"
    if not gold_candidate_selected:
        if reading_score < DEFAULT_MIN_SCORE:
            return "first_pass_reading_not_close_or_missing"
        return "gold_candidate_not_hinted"
    return "two_pass_did_not_correct_term"


def analyze_term_trace(
    manifest_rows: list[dict[str, Any]],
    first_by_id: dict[str, dict[str, Any]],
    second_by_id: dict[str, dict[str, Any]],
    formatted_by_id: dict[str, dict[str, Any]],
    glossary: list[GlossaryEntry],
    expanded_glossary: list[GlossaryEntry],
    hint_format: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """同じ用語出現を1回目、候補選択、two-pass、整形の順に記録する。"""
    glossary_by_surface = {entry.surface: entry for entry in glossary}
    trace_rows: list[dict[str, Any]] = []
    failure_causes: Counter[str] = Counter()
    counts = Counter()
    reading_distances: Counter[str] = Counter()
    format_input_mismatches = 0

    for row in manifest_rows:
        sample_id = row["id"]
        terms = row.get("terms", [])
        first_text = first_by_id[sample_id]["hyp"]
        second_text = second_by_id[sample_id]["hyp"]
        formatted_text = formatted_by_id[sample_id]["hyp"]
        if not all(isinstance(text, str) for text in (first_text, second_text, formatted_text)):
            raise ValueError(f"{sample_id}: 各段階のhypは文字列が必要です")
        format_input = formatted_by_id[sample_id].get("input_text")
        format_input_matches = format_input == second_text
        if format_input is not None and not format_input_matches:
            format_input_mismatches += 1

        selected, hint_terms = _candidate_selection(first_text, glossary, hint_format)
        first_flags = _occurrence_flags(terms, first_text)
        second_flags = _occurrence_flags(terms, second_text)
        formatted_flags = _occurrence_flags(terms, formatted_text)
        for index, term in enumerate(terms):
            readings = _readings_for_term(row, term, glossary_by_surface)
            closest_reading, first_distance = _closest_reading(readings, first_text)
            _, second_distance = _closest_reading(readings, second_text)
            reading_score = score_entry_readings(
                GlossaryEntry(term, readings), first_text
            )
            first_correct = first_flags[index]
            second_correct = second_flags[index]
            formatted_correct = formatted_flags[index]
            gold_candidate_selected = term in hint_terms
            cause = _failure_cause(
                first_correct=first_correct,
                second_correct=second_correct,
                formatted_correct=formatted_correct,
                gold_candidate_selected=gold_candidate_selected,
                reading_score=reading_score,
            )
            counts["first_pass_correct"] += first_correct
            counts["two_pass_correct"] += second_correct
            counts["formatted_correct"] += formatted_correct
            counts["gold_candidate_selected"] += gold_candidate_selected
            counts["first_pass_reading_near"] += reading_score >= DEFAULT_MIN_SCORE
            counts["two_pass_broke_first_pass_correct"] += (
                first_correct and not second_correct
            )
            counts["two_pass_moved_farther_from_reading"] += (
                first_distance is not None
                and second_distance is not None
                and second_distance > first_distance
            )
            counts["formatter_fixed"] += not second_correct and formatted_correct
            counts["formatter_broke"] += second_correct and not formatted_correct
            if first_distance is None:
                reading_distances["no_kana_reading_match"] += 1
            else:
                reading_distances[str(first_distance)] += 1
            failure_causes[cause] += 1
            trace_rows.append(
                {
                    "id": sample_id,
                    "occurrence": index + 1,
                    "term": term,
                    "readings": list(readings),
                    "first_pass": first_text,
                    "closest_reading": closest_reading,
                    "closest_reading_distance": first_distance,
                    "first_pass_reading_score": reading_score,
                    "first_pass_reading_near": reading_score >= DEFAULT_MIN_SCORE,
                    "selected_candidates": [entry.surface for entry in selected],
                    "hint_terms": hint_terms,
                    "gold_candidate_selected": gold_candidate_selected,
                    "first_pass_exact": first_correct,
                    "two_pass": second_text,
                    "two_pass_exact": second_correct,
                    "two_pass_broke_first_pass_correct": (
                        first_correct and not second_correct
                    ),
                    "two_pass_reading_distance": second_distance,
                    "two_pass_moved_farther_from_reading": (
                        first_distance is not None
                        and second_distance is not None
                        and second_distance > first_distance
                    ),
                    "formatted": formatted_text,
                    "formatted_exact": formatted_correct,
                    "formatter_fixed": not second_correct and formatted_correct,
                    "formatter_broke": second_correct and not formatted_correct,
                    "format_input_matches_two_pass": format_input_matches,
                    "final_failure_cause": cause,
                }
            )

    total = len(trace_rows)
    coverage = _coverage_for_glossary(
        manifest_rows, first_by_id, glossary, hint_format
    )
    expanded_coverage = _coverage_for_glossary(
        manifest_rows, first_by_id, expanded_glossary, hint_format
    )
    summary = {
        "utterances": len(manifest_rows),
        "term_occurrences": total,
        "stage_counts": {
            "first_pass_exact": counts["first_pass_correct"],
            "first_pass_reading_near": counts["first_pass_reading_near"],
            "gold_candidate_selected": counts["gold_candidate_selected"],
            "two_pass_exact": counts["two_pass_correct"],
            "two_pass_broke_first_pass_correct": counts[
                "two_pass_broke_first_pass_correct"
            ],
            "two_pass_moved_farther_from_reading": counts[
                "two_pass_moved_farther_from_reading"
            ],
            "formatted_exact": counts["formatted_correct"],
            "formatter_fixed": counts["formatter_fixed"],
            "formatter_broke": counts["formatter_broke"],
        },
        "failure_causes": {
            cause: count
            for cause, count in sorted(failure_causes.items())
            if cause != "correct"
        },
        "reading_distance_histogram": dict(sorted(reading_distances.items())),
        "candidate_coverage": {
            "current_readings": coverage,
            "automatic_abbreviation_readings": expanded_coverage,
            "delta_correct_candidate_occurrences": (
                expanded_coverage["correct_candidate_occurrences"]
                - coverage["correct_candidate_occurrences"]
            ),
        },
        "formatter_input_mismatches": format_input_mismatches,
        "policy_estimates": {},
    }
    return trace_rows, summary


def _candidate_entries_from_names(
    names: list[str], entries_by_surface: dict[str, GlossaryEntry]
) -> list[GlossaryEntry]:
    """保存済みヒント表記を、元の読みを持つ用語集項目へ戻す。"""
    return [
        entries_by_surface[name]
        for name in dict.fromkeys(names)
        if name in entries_by_surface
    ]


def _choose_utterance_output(
    policy: str,
    first_text: str,
    second_text: str,
    candidates: list[GlossaryEntry],
) -> tuple[str, bool]:
    """保存済み2出力から発話単位で採る文を選び、再認識を通したか返す。"""
    if policy == "reading-near":
        near = max(
            (score_entry_readings(entry, first_text) for entry in candidates),
            default=0.0,
        ) >= DEFAULT_MIN_SCORE
        return (second_text if near else first_text), near
    first_score = max(
        (score_entry_in_text(entry, first_text) for entry in candidates), default=0.0
    )
    second_score = max(
        (score_entry_in_text(entry, second_text) for entry in candidates), default=0.0
    )
    use_second = second_score >= first_score
    return (second_text if use_second else first_text), use_second


def _metrics_for_hypotheses(
    rows: list[dict[str, Any]], hypotheses: dict[str, str]
) -> dict[str, Any]:
    """用語正表記数とASR既存レポートと同じ読み揃えCERを計算する。"""
    exact_terms = total_terms = 0
    references: list[str] = []
    predictions: list[str] = []
    for row in rows:
        sample_id = row["id"]
        hyp = hypotheses[sample_id]
        metrics = calculate_term_accuracy(row.get("terms", []), row.get("glossary", []), hyp)
        exact_terms += int(metrics["correct"])
        total_terms += int(metrics["total"])
        spoken_text = row.get("spoken_text")
        if not isinstance(spoken_text, str):
            raise ValueError(f"{sample_id}: spoken_textがありません")
        glossary = row.get("glossary", [])
        references.append(replace_glossary_surfaces_with_readings(spoken_text, glossary))
        predictions.append(replace_glossary_surfaces_with_readings(hyp, glossary))
    return {
        "term_exact_correct": exact_terms,
        "term_total": total_terms,
        "term_exact_accuracy": exact_terms / total_terms if total_terms else None,
        "aligned_cer": calculate_cer(references, predictions),
    }


def _rejected_change_counts(merged: Any) -> tuple[int, int, int]:
    """Fable試作に合わせ、拒否した編集の文字幅と4文字以上の発話を数える。"""
    rejected_edits = rejected_chars = 0
    for edit in merged.edits:
        if edit.accepted or _normalize_trace_text(edit.old_text) == _normalize_trace_text(edit.new_text):
            continue
        rejected_edits += 1
        rejected_chars += max(len(edit.old_text), len(edit.new_text))
    return rejected_edits, rejected_chars, int(rejected_chars >= 4)


def _normalize_trace_text(text: str) -> str:
    """空白、句読点、大小文字を除き、mergeの差分長を比較する。"""
    normalized = to_katakana(unicodedata.normalize("NFKC", text)).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and unicodedata.category(character)[0] not in {"P", "S"}
    )


def analyze_saved_hints(
    manifest_rows: list[dict[str, Any]],
    hints_rows: list[dict[str, Any]],
    glossary: list[GlossaryEntry],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """保存済みの1回目・2回目とヒントから各方針を測り、結合出力を作る。"""
    glossary_by_surface = {entry.surface: entry for entry in glossary}
    hints_by_id = {row["id"]: row for row in hints_rows}
    scripted_rows = [row for row in manifest_rows if row.get("prompt_kind") == "scripted"]
    free_rows = [row for row in manifest_rows if row.get("prompt_kind") == "free"]
    strategies: dict[str, dict[str, str]] = {
        "two_pass_as_is": {},
        "reading_near": {},
        "no_farther": {},
        "segment_merge": {},
    }
    merge_by_id = {}
    entries_by_id: dict[str, list[GlossaryEntry]] = {}
    second_pass_used: dict[str, dict[str, bool]] = {
        "reading_near": {},
        "no_farther": {},
    }
    unsafe_by_strategy: dict[str, dict[str, tuple[int, int, int]]] = {
        name: {} for name in strategies
    }
    output_rows: list[dict[str, Any]] = []

    for row in manifest_rows:
        sample_id = row["id"]
        saved = hints_by_id[sample_id]
        first_text = saved.get("first_pass")
        second_text = saved.get("final")
        hint_names = saved.get("hints")
        if not isinstance(first_text, str) or not isinstance(second_text, str):
            raise ValueError(f"{sample_id}: first_passとfinalは文字列が必要です")
        if hint_names is None:
            hint_names = []
        if not isinstance(hint_names, list) or not all(
            isinstance(name, str) for name in hint_names
        ):
            raise ValueError(f"{sample_id}: hintsは文字列の配列が必要です")
        candidates = _candidate_entries_from_names(hint_names, glossary_by_surface)
        entries_by_id[sample_id] = candidates
        strategies["two_pass_as_is"][sample_id] = second_text
        for policy in ("reading_near", "no_farther"):
            selected_text, used_second = _choose_utterance_output(
                policy, first_text, second_text, candidates
            )
            strategies[policy][sample_id] = selected_text
            second_pass_used[policy][sample_id] = used_second

        merged = merge_two_pass_text(first_text, second_text, candidates)
        merge_by_id[sample_id] = merged
        strategies["segment_merge"][sample_id] = merged.text
        output_rows.append(
            {
                "id": sample_id,
                "system": "asr-v1-t16-s75+segment-merge",
                "stage": "asr",
                "hyp": merged.text,
            }
        )

    for row in free_rows:
        sample_id = row["id"]
        saved = hints_by_id[sample_id]
        first_text = saved["first_pass"]
        for name, hypotheses in strategies.items():
            checked = merge_two_pass_text(
                first_text, hypotheses[sample_id], entries_by_id[sample_id]
            )
            unsafe_by_strategy[name][sample_id] = _rejected_change_counts(checked)

    policy_estimates = {}
    for name, hypotheses in strategies.items():
        free_results = unsafe_by_strategy[name]
        raw_unsafe = {
            sample_id
            for sample_id, counts in unsafe_by_strategy["two_pass_as_is"].items()
            if counts[2]
        }
        current_unsafe = {
            sample_id for sample_id, counts in free_results.items() if counts[2]
        }
        protected = raw_unsafe - current_unsafe
        policy_estimates[name] = {
            **_metrics_for_hypotheses(scripted_rows, hypotheses),
            "free_utterances_with_rejected_changes": sum(
                bool(counts[0]) for counts in free_results.values()
            ),
            "free_utterances_with_4plus_rejected_characters": len(current_unsafe),
            "free_rejected_changed_characters": sum(
                counts[1] for counts in free_results.values()
            ),
            "free_utterances_protected_from_raw_4plus_changes": len(protected),
            "second_pass_used_utterances": (
                None
                if name == "two_pass_as_is" or name == "segment_merge"
                else sum(second_pass_used[name].values())
            ),
        }

    merge_decisions = Counter()
    for row in free_rows:
        merged = merge_by_id[row["id"]]
        rejected_edits, rejected_chars, flagged = _rejected_change_counts(merged)
        merge_decisions["rejected_edits"] += rejected_edits
        merge_decisions["rejected_changed_characters"] += rejected_chars
        merge_decisions["utterances_with_rejected_edit"] += bool(rejected_edits)
        merge_decisions["utterances_with_4plus_rejected_characters"] += flagged

    scripted_term_total = sum(len(row.get("terms", [])) for row in scripted_rows)
    report = {
        "manifest_utterances": len(manifest_rows),
        "scripted_utterances": len(scripted_rows),
        "scripted_term_occurrences": scripted_term_total,
        "free_utterances": len(free_rows),
        "hint_rows": len(hints_rows),
        "merge_threshold_normalized_levenshtein": SEGMENT_MERGE_MIN_READING_SIMILARITY,
        "free_raw_two_pass_detection": dict(merge_decisions),
        "strategies": policy_estimates,
        "estimation_note": (
            "全指標は保存済みfirst_pass/finalを選択・結合した反実仮想であり、ASRを再実行していない。"
            "新しいヒントでASRのfinal自体が変わる効果は測っていない。freeの4文字判定はFable試作の基準に合わせた。"
        ),
    }
    return output_rows, report, [
        {
            "id": row["id"],
            "first_pass": hints_by_id[row["id"]]["first_pass"],
            "two_pass": hints_by_id[row["id"]]["final"],
            "hint_terms": hints_by_id[row["id"]].get("hints") or [],
            "edits": [
                {
                    "old": edit.old_text,
                    "new": edit.new_text,
                    "candidate_surface": edit.candidate_surface,
                    "reading_similarity": edit.reading_similarity,
                    "match_basis": edit.match_basis,
                    "accepted": edit.accepted,
                    "rejection_reason": edit.rejection_reason,
                }
                for edit in merge_by_id[row["id"]].edits
            ],
            "merged": merge_by_id[row["id"]].text,
        }
        for row in manifest_rows
    ]


def _jsonable_trace_row(row: dict[str, Any]) -> dict[str, Any]:
    """TSV内の配列をJSON文字列へ変換し、列数を一定に保つ。"""
    return {
        key: json.dumps(row[key], ensure_ascii=False)
        if isinstance(row[key], (list, dict))
        else "" if row[key] is None else row[key]
        for key in _TRACE_FIELDS
    }


def _term_trace_markdown(summary: dict[str, Any]) -> str:
    """工程別の件数、読み候補の変化、未検証範囲を短い報告にする。"""
    stages = summary["stage_counts"]
    coverage = summary["candidate_coverage"]
    current = coverage["current_readings"]
    expanded = coverage["automatic_abbreviation_readings"]
    cause_lines = [
        f"| {cause} | {count} |"
        for cause, count in summary["failure_causes"].items()
    ] or ["| 失敗なし | 0 |"]
    return "\n".join(
        [
            "# 用語の工程別切り分け",
            "",
            f"対象は{summary['utterances']}発話、用語{summary['term_occurrences']}回。",
            "",
            "| 段階 | 正表記の件数 |",
            "| --- | ---: |",
            f"| 1回目 | {stages['first_pass_exact']} |",
            f"| 2回目 | {stages['two_pass_exact']} |",
            f"| 整形後 | {stages['formatted_exact']} |",
            f"| 2回目で1回目の正表記を破壊 | {stages['two_pass_broke_first_pass_correct']} |",
            f"| 2回目で読み距離が増加 | {stages['two_pass_moved_farther_from_reading']} |",
            f"| 整形で修正 / 破壊 | {stages['formatter_fixed']} / {stages['formatter_broke']} |",
            "",
            "## 最終失敗の分類",
            "",
            "| 原因 | 件数 |",
            "| --- | ---: |",
            *cause_lines,
            "",
            "## 略語読みの追加による候補数の見積もり",
            "",
            f"現行 {current['correct_candidate_occurrences']}/{current['total_occurrences']}、"
            f"自動読み追加 {expanded['correct_candidate_occurrences']}/{expanded['total_occurrences']}、"
            f"差 {coverage['delta_correct_candidate_occurrences']:+d}。",
            "候補は1回目の保存済み出力に対してのみ再計算し、ASRは動かしていない。",
            "",
            f"整形JSONLのinput_textと2回目出力の不一致: {summary['formatter_input_mismatches']}件。",
            "",
        ]
    )


def _saved_hints_markdown(report: dict[str, Any]) -> str:
    """読み上げ50件の精度とfree発話の破壊検出を方針別に並べる。"""
    labels = {
        "two_pass_as_is": "2回目そのまま",
        "reading_near": "発話単位:読みが近い場合のみ",
        "no_farther": "発話単位:読み距離が悪化しない場合",
        "segment_merge": "区間単位の結合",
    }
    lines = [
        "# 保存済みtwo-pass出力の比較",
        "",
        f"manifest {report['manifest_utterances']}件、scripted {report['scripted_utterances']}件・用語"
        f"{report['scripted_term_occurrences']}回、free {report['free_utterances']}件。",
        "",
        "| 方針 | scripted用語正表記 | 読み揃えCER | freeで4文字以上の破壊検出 | freeで保護した発話 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, label in labels.items():
        values = report["strategies"][name]
        cer = values["aligned_cer"]
        lines.append(
            f"| {label} | {values['term_exact_correct']}/{values['term_total']} | "
            f"{cer['edit_errors']}/{cer['reference_characters']} "
            f"({cer['rate']:.2%}) | "
            f"{values['free_utterances_with_4plus_rejected_characters']} | "
            f"{values['free_utterances_protected_from_raw_4plus_changes']} |"
        )
    detection = report["free_raw_two_pass_detection"]
    lines.extend(
        [
            "",
            "freeの破壊検出は、ヒント表記に対応せず、元区間も読み類似度0.75未満の差分文字幅を集計し、"
            "1発話で4文字以上なら検出と数えた。Fable試作の4文字基準に合わせている。",
            f"区間結合が拒否したfree差分: {detection.get('rejected_edits', 0)}区間、"
            f"{detection.get('rejected_changed_characters', 0)}文字、"
            f"{detection.get('utterances_with_4plus_rejected_characters', 0)}発話。",
            "",
            report["estimation_note"],
            "",
        ]
    )
    return "\n".join(lines)


def _write_term_trace_outputs(
    output_dir: Path, trace_rows: list[dict[str, Any]], summary: dict[str, Any]
) -> None:
    """工程別の表、機械可読集計、Markdownを出力する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "term_trace.tsv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=_TRACE_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(_jsonable_trace_row(row) for row in trace_rows)
    (output_dir / "term_trace_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "term_trace_report.md").write_text(
        _term_trace_markdown(summary), encoding="utf-8"
    )


def _write_saved_hints_outputs(
    output_dir: Path,
    merged_rows: list[dict[str, Any]],
    report: dict[str, Any],
    merge_details: list[dict[str, Any]],
) -> None:
    """結合後のruns JSONLと方針別の数値、区間採否の説明を保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_path = output_dir / "asr-v1-t16-s75.segment-merge.jsonl"
    with merged_path.open("w", encoding="utf-8") as file:
        for row in merged_rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    report["merged_asr_jsonl"] = str(merged_path)
    (output_dir / "saved_hints_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "saved_hints_merge_details.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in merge_details),
        encoding="utf-8",
    )
    (output_dir / "saved_hints_report.md").write_text(
        _saved_hints_markdown(report), encoding="utf-8"
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """用語追跡または保存済みヒントの結合に必要なパスを読む。"""
    parser = argparse.ArgumentParser(
        description="用語の工程別集計と、保存済みtwo-pass出力の区間結合を行う"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, nargs="+", required=True)
    parser.add_argument("--first-pass", type=Path)
    parser.add_argument("--two-pass", type=Path)
    parser.add_argument("--formatted", type=Path)
    parser.add_argument("--hints", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--hint-format",
        choices=("surface", "surface-reading"),
        default="surface-reading",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """指定された保存結果を解析し、頼まれた成果物だけを書き出す。"""
    args = _parse_args(argv)
    term_paths = (args.first_pass, args.two_pass, args.formatted)
    if any(term_paths) and not all(term_paths):
        raise SystemExit("--first-pass、--two-pass、--formattedはすべて指定してください")
    if not args.hints and not all(term_paths):
        raise SystemExit("工程別集計または保存済みヒント結合の入力が必要です")

    manifest_path = args.manifest
    manifest_rows = _read_jsonl(manifest_path)
    manifest_by_id = _index_by_id(manifest_rows, manifest_path)
    glossary = load_glossary(*args.glossary)
    expanded_glossary = load_glossary(
        *args.glossary, expand_abbreviation_readings=True
    )

    if all(term_paths):
        scripted_rows = [row for row in manifest_rows if row.get("prompt_kind") == "scripted"]
        eligible_rows = scripted_rows or [
            row for row in manifest_rows if isinstance(row.get("terms"), list) and row["terms"]
        ]
        run_paths = (args.first_pass, args.two_pass, args.formatted)
        indexed_runs = [
            _index_by_id(_read_jsonl(path), path) for path in run_paths if path is not None
        ]
        first_by_id, second_by_id, formatted_by_id = indexed_runs
        missing = {
            str(path): [
                row["id"]
                for row in eligible_rows
                if row["id"] not in indexed
            ]
            for path, indexed in zip(run_paths, indexed_runs, strict=True)
        }
        if any(missing.values()):
            raise ValueError(f"用語を持つ発話の推論結果が不足しています: {missing}")
        trace_rows, summary = analyze_term_trace(
            eligible_rows,
            first_by_id,
            second_by_id,
            formatted_by_id,
            glossary,
            expanded_glossary,
            args.hint_format,
        )
        _write_term_trace_outputs(args.out_dir, trace_rows, summary)
        print(
            f"term trace: {len(trace_rows)}用語を集計 -> "
            f"{args.out_dir / 'term_trace_report.md'}"
        )

    if args.hints:
        hints_rows = _read_jsonl(args.hints)
        hints_by_id = _index_by_id(hints_rows, args.hints)
        if set(hints_by_id) != set(manifest_by_id):
            missing = sorted(set(manifest_by_id) - set(hints_by_id))
            unknown = sorted(set(hints_by_id) - set(manifest_by_id))
            raise ValueError(
                f"manifestとhintsのidが一致しません: 欠落={missing[:3]}、未知={unknown[:3]}"
            )
        merged_rows, report, merge_details = analyze_saved_hints(
            manifest_rows, hints_rows, glossary
        )
        _write_saved_hints_outputs(args.out_dir, merged_rows, report, merge_details)
        print(
            f"saved hints: {len(merged_rows)}発話を結合 -> "
            f"{args.out_dir / 'asr-v1-t16-s75.segment-merge.jsonl'}"
        )


if __name__ == "__main__":
    main()
