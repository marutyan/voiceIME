"""保存済みの1回目のASR結果で用語選択を比較し、集計値だけをJSONへ保存する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from rapidfuzz import fuzz

from voiceime.formatter.glossary import (
    DEFAULT_MIN_SCORE,
    GlossaryEntry,
    GlossaryIndex,
    SELECTION_MAX_BIGRAM_POSTINGS,
    SELECTION_MAX_TRIGRAM_POSTINGS,
    _find_matches_in_runs,
    _kana_to_romaji,
    _romanized_runs,
    _selection_surface_key,
    _text_runs,
    load_glossary,
    load_term_list,
    normalize_kana,
    normalize_latin,
)

# 評価スクリプトと辞書・実験出力の既定位置。
ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "runs"
DATA_ROOT = ROOT / "data"
# ASRへ渡す既定の候補数と、上位率を集計する件数。
MAX_ENTRIES = 16
HIT_CUTOFFS = (4, 8, 16)


@dataclass(frozen=True)
class SelectionItem:
    """選択結果と正解語を結び付ける評価用の1発話。"""

    item_id: str
    text: str
    gold_terms: tuple[str, ...]


def read_jsonl(path: Path) -> list[dict]:
    """JSON Linesを読み込み、空行を除いたレコードを返す。"""
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def sha256(path: Path) -> str:
    """評価に使った入力ファイルを識別するSHA-256を返す。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_items(source_path: Path, asr_path: Path, asr_field: str) -> list[SelectionItem]:
    """sourceとASR出力をIDで結び、発話文と用語正解をまとめる。"""
    source_rows = {row["id"]: row for row in read_jsonl(source_path)}
    asr_rows = {row["id"]: row for row in read_jsonl(asr_path)}
    if source_rows.keys() != asr_rows.keys():
        raise ValueError(
            f"sourceとASRのIDが一致しない: source={len(source_rows)}, asr={len(asr_rows)}"
        )
    items = []
    for item_id, row in source_rows.items():
        text = asr_rows[item_id][asr_field]
        if not isinstance(text, str):
            raise TypeError(f"{item_id}の{asr_field}が文字列ではない")
        terms = row.get("terms")
        if terms is None:
            terms = [term["surface"] for term in row.get("glossary", [])]
        items.append(SelectionItem(item_id, text, tuple(terms)))
    return items


def legacy_score_entry(
    entry: GlossaryEntry,
    text: str,
    kana_runs,
    latin_runs,
) -> float:
    """変更前のselect_glossaryと同じ部分一致スコアを1語について計算する。"""
    scores = [
        match.score
        for reading in entry.readings
        for match in _find_matches_in_runs(reading, kana_runs, "kana", 0.0, True, True, True)
    ]
    if entry.surface in text:
        scores.append(100.0)
    else:
        scores.extend(
            match.score
            for match in _find_matches_in_runs(entry.surface, latin_runs, "latin", 0.0, False)
        )
    return max(scores, default=0.0)


def legacy_select_glossary(
    text: str,
    entries: Sequence[GlossaryEntry],
    max_entries: int = MAX_ENTRIES,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[GlossaryEntry]:
    """保存済み結果を比較するため、変更前の全件採点と順位付けを再現する。"""
    kana_runs = _text_runs(text, "kana", ignore_long_vowel=True)
    latin_runs = _text_runs(text, "latin")
    scored = [
        (legacy_score_entry(entry, text, kana_runs, latin_runs), index, entry)
        for index, entry in enumerate(entries)
    ]
    ranked = sorted(
        (item for item in scored if item[0] >= min_score),
        key=lambda item: (-item[0], item[1]),
    )
    return [entry for _, _, entry in ranked[:max_entries]]


def indexed_select_before_boundary(
    text: str,
    index: GlossaryIndex,
    max_entries: int = MAX_ENTRIES,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[GlossaryEntry]:
    """境界条件を加える前の索引採点を再現し、変更前後を比べる。"""
    kana_runs = _text_runs(text, "kana", ignore_long_vowel=True)
    latin_runs = _text_runs(text, "latin")
    romanized_runs = _romanized_runs(text)
    candidates = index._candidate_key_indexes(kana_runs, latin_runs, romanized_runs)
    scores: dict[int, float] = {}
    for key_index in candidates:
        key = index.keys[key_index]
        if len(key.text) <= 2:
            score = 100.0
        else:
            runs = [run.text for run in kana_runs] if key.script == "kana" else romanized_runs
            score = 0.0
            for run in runs:
                alignment = fuzz.partial_ratio_alignment(
                    key.text,
                    run,
                    score_cutoff=min_score,
                )
                if alignment is None:
                    continue
                matched_length = alignment.src_end - alignment.src_start
                coverage_score = 100.0 * min(1.0, matched_length / len(key.text))
                score = max(score, min(alignment.score, coverage_score))
        if score >= min_score:
            scores[key.entry_index] = max(scores.get(key.entry_index, 0.0), score)

    ranked = sorted(
        scores.items(),
        key=lambda item: (
            not index.entries[item[0]].priority,
            -item[1],
            item[0],
        ),
    )
    return [index.entries[entry_index] for entry_index, _ in ranked[:max_entries]]


def has_short_reading_boundary_miss(
    entry: GlossaryEntry, romanized_runs: Sequence[str]
) -> tuple[bool, bool]:
    """短い読みがローマ字化した区間の全体に合わず、内側へ当たるか調べる。"""
    boundary_miss = False
    strictly_inside = False
    full_run_match = False
    for reading in entry.readings:
        if not 0 < len(normalize_kana(reading)) <= 2:
            continue
        key = _selection_surface_key(_kana_to_romaji(reading))
        if not key:
            continue
        for run in romanized_runs:
            alignment = fuzz.partial_ratio_alignment(
                key,
                run,
                score_cutoff=DEFAULT_MIN_SCORE,
            )
            if alignment is None:
                continue
            starts_at_boundary = alignment.dest_start == 0
            ends_at_boundary = alignment.dest_end == len(run)
            full_run_match |= starts_at_boundary and ends_at_boundary
            boundary_miss |= not (starts_at_boundary and ends_at_boundary)
            strictly_inside |= not starts_at_boundary and not ends_at_boundary
    return boundary_miss and not full_run_match, strictly_inside and not full_run_match


def percentile(values: list[float], fraction: float) -> float:
    """線形補間で分位点を計算する。"""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def compare_selector(
    items: Sequence[SelectionItem],
    entries: Sequence[GlossaryEntry],
    selector_name: str,
    selector: Callable[[str], list[GlossaryEntry]],
    index_build_ms: float | None,
) -> dict:
    """上位K語の正解含有率と、16語中の正解外候補数・選択時間を集計する。"""
    vocabulary = {entry.surface for entry in entries}
    hit_counts = dict.fromkeys(HIT_CUTOFFS, 0)
    total_gold = 0
    missing_gold = 0
    unrelated = 0
    unrelated_short_boundary_miss = 0
    unrelated_short_strictly_inside = 0
    selected_counts = []
    selection_ms = []

    for item in items:
        eligible_gold = [term for term in item.gold_terms if term in vocabulary]
        total_gold += len(eligible_gold)
        missing_gold += len(item.gold_terms) - len(eligible_gold)
        started = time.perf_counter()
        selected = selector(item.text)
        selection_ms.append((time.perf_counter() - started) * 1000)
        selected_counts.append(len(selected))
        gold_set = set(item.gold_terms)
        unrelated += sum(entry.surface not in gold_set for entry in selected)
        romanized_runs = _romanized_runs(item.text)
        for entry in selected:
            if entry.surface in gold_set:
                continue
            boundary_miss, strictly_inside = has_short_reading_boundary_miss(
                entry, romanized_runs
            )
            unrelated_short_boundary_miss += boundary_miss
            unrelated_short_strictly_inside += strictly_inside
        for cutoff in HIT_CUTOFFS:
            selected_surfaces = {entry.surface for entry in selected[:cutoff]}
            hit_counts[cutoff] += sum(term in selected_surfaces for term in eligible_gold)

    return {
        "selector": selector_name,
        "glossary_size": len(entries),
        "utterances": len(items),
        "gold_terms_available": total_gold,
        "gold_terms_not_in_glossary": missing_gold,
        "hit_counts": {str(k): hit_counts[k] for k in HIT_CUTOFFS},
        "hit_rates": {
            str(k): hit_counts[k] / total_gold if total_gold else None for k in HIT_CUTOFFS
        },
        "unrelated_candidates_at_16": unrelated,
        "unrelated_per_utterance_at_16": unrelated / len(items) if items else 0,
        "unrelated_with_short_read_match_not_covering_run_at_16": unrelated_short_boundary_miss,
        "unrelated_with_short_read_strictly_inside_run_at_16": unrelated_short_strictly_inside,
        "mean_selected_at_16": statistics.mean(selected_counts) if selected_counts else 0,
        "selection_ms_median": statistics.median(selection_ms) if selection_ms else 0,
        "selection_ms_p90": percentile(selection_ms, 0.9) if selection_ms else 0,
        "index_build_ms": index_build_ms,
    }


def timed_index(entries: Sequence[GlossaryEntry]) -> tuple[GlossaryIndex, float]:
    """索引構築を選択時間と分けて測る。"""
    started = time.perf_counter()
    index = GlossaryIndex(entries)
    return index, (time.perf_counter() - started) * 1000


def summarize_hiragana_short_reading_collisions(
    items: Sequence[SelectionItem], entries: Sequence[GlossaryEntry]
) -> dict:
    """二仮名読みが発話中のひらがな列に現れる頻度を、正解語との重なりも含め数える。"""
    surfaces_by_reading: dict[str, set[str]] = {}
    for entry in entries:
        for reading in entry.readings:
            normalized = normalize_kana(reading)
            if len(normalized) != 2:
                continue
            hiragana = "".join(
                chr(ord(character) - 0x60)
                if "\u30a1" <= character <= "\u30f6"
                else character
                for character in normalized
            )
            surfaces_by_reading.setdefault(hiragana, set()).add(entry.surface)

    utterances_with_match = 0
    utterances_with_gold_match = 0
    occurrences = 0
    gold_occurrences = 0
    edge_occurrences = 0
    inner_occurrences = 0
    for item in items:
        item_has_match = False
        item_has_gold_match = False
        gold_terms = set(item.gold_terms)
        for run_match in re.finditer(r"[\u3041-\u3096]+", item.text):
            run = run_match.group()
            for reading, surfaces in surfaces_by_reading.items():
                offset = 0
                while (start := run.find(reading, offset)) >= 0:
                    end = start + len(reading)
                    occurrences += 1
                    item_has_match = True
                    if start == 0 or end == len(run):
                        edge_occurrences += 1
                    else:
                        inner_occurrences += 1
                    if surfaces & gold_terms:
                        gold_occurrences += 1
                        item_has_gold_match = True
                    offset = end
        utterances_with_match += item_has_match
        utterances_with_gold_match += item_has_gold_match

    return {
        "distinct_two_kana_readings": len(surfaces_by_reading),
        "utterances_with_hiragana_substring": utterances_with_match,
        "hiragana_substring_occurrences": occurrences,
        "occurrences_at_hiragana_run_edge": edge_occurrences,
        "occurrences_inside_hiragana_run": inner_occurrences,
        "gold_term_reading_occurrences": gold_occurrences,
        "utterances_with_gold_term_reading_occurrence": utterances_with_gold_match,
        "interpretation": "部分文字列の頻度であり、ASRが意図した用語をひらがなで出したと人手判定した件数ではない",
    }


def evaluate_dataset(
    items: list[SelectionItem],
    v1: list[GlossaryEntry],
    v2_old: list[GlossaryEntry],
    v2_new: list[GlossaryEntry],
    *,
    boundary_only: bool = False,
) -> dict:
    """同じ1回目のASR文でv1、旧v2、新v2を全て比較する。"""
    v1_index, v1_build_ms = timed_index(v1)
    v2_new_index, v2_new_build_ms = timed_index(v2_new)
    selectors = []
    if not boundary_only:
        selectors.append(("v1_old", v1, lambda text: legacy_select_glossary(text, v1), None))
    selectors.append(
        (
            "v1_new_before_boundary",
            v1,
            lambda text: indexed_select_before_boundary(text, v1_index),
            v1_build_ms,
        )
    )
    selectors.append(
        (
            "v1_new",
            v1,
            lambda text: v1_index.select(text, MAX_ENTRIES, DEFAULT_MIN_SCORE),
            v1_build_ms,
        )
    )
    if not boundary_only:
        selectors.append(
            ("v2_old", v2_old, lambda text: legacy_select_glossary(text, v2_old), None)
        )
    selectors.extend(
        [
            (
                "v2_new_before_boundary",
                v2_new,
                lambda text: indexed_select_before_boundary(text, v2_new_index),
                v2_new_build_ms,
            ),
            (
                "v2_new_priority_v1_plus_v2",
                v2_new,
                lambda text: v2_new_index.select(text, MAX_ENTRIES, DEFAULT_MIN_SCORE),
                v2_new_build_ms,
            ),
        ]
    )
    return {
        "utterances": len(items),
        "short_reading_hiragana_collisions": summarize_hiragana_short_reading_collisions(
            items, v2_new
        ),
        "results": [
            compare_selector(items, entries, name, selector, build_ms)
            for name, entries, selector, build_ms in selectors
        ],
    }


def parse_args() -> argparse.Namespace:
    """評価に使う辞書、保存済み結果、出力先を受け取る。"""
    parser = argparse.ArgumentParser(description="用語選択を保存済みASR結果で比較する")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--runs-root", type=Path, default=RUNS_ROOT)
    parser.add_argument("--user-glossary", type=Path, action="append", default=[])
    parser.add_argument(
        "--boundary-only",
        action="store_true",
        help="全件採点の旧方式を再実行せず、保存済み旧評価を基準に境界前後を比較する",
    )
    parser.add_argument(
        "--output", type=Path, default=RUNS_ROOT / "term-select" / "selection-comparison.json"
    )
    return parser.parse_args()


def main() -> None:
    """保存済みASR出力を再利用して比較し、個別の発話内容を出さずに集計を保存する。"""
    args = parse_args()
    v1_path = args.data_root / "text" / "glossary.jsonl"
    v2_path = args.data_root / "text" / "glossary-v2.jsonl"
    excluded_path = args.data_root / "text" / "glossary-v2-excluded.txt"
    v1 = load_glossary(v1_path)
    excluded = load_term_list(excluded_path)
    v2_raw = load_glossary(v2_path)
    v2_old = load_glossary(v2_path, exclude_terms=excluded)
    v2_new = load_glossary(v1_path, *args.user_glossary, v2_path, exclude_terms=excluded)
    previous_comparison_path = args.runs_root / "term-select" / "selection-comparison.json"
    previous_comparison = json.loads(previous_comparison_path.read_text(encoding="utf-8"))

    datasets = {
        "dev-user": load_items(
            args.data_root / "dev-user" / "manifest.jsonl",
            args.runs_root / "v2gloss" / "asr-v2-t16-s75.hints.jsonl",
            "first_pass",
        ),
        "test-novel": load_items(
            args.runs_root / "asr-tts" / "r3-audio-20261122" / "test-novel-source.jsonl",
            args.runs_root
            / "asr-tts"
            / "r3-audio-20261122"
            / "test-novel-include-novel-plain.jsonl",
            "hyp",
        ),
        "val": load_items(
            args.data_root / "tts" / "val" / "manifest.jsonl",
            args.runs_root / "asr-tts" / "haas-val.jsonl",
            "hyp",
        ),
    }

    result = {
        "conditions": {
            "min_score": DEFAULT_MIN_SCORE,
            "max_entries": MAX_ENTRIES,
            "v1": {"path": "data/text/glossary.jsonl", "entries": len(v1), "sha256": sha256(v1_path)},
            "v2_old": {
                "path": "data/text/glossary-v2.jsonl",
                "raw_entries": len(v2_raw),
                "entries": len(v2_old),
                "excluded_terms_listed": len(excluded),
                "excluded_entries_removed": len(v2_raw) - len(v2_old),
                "sha256": sha256(v2_path),
                "exclude_sha256": sha256(excluded_path),
            },
            "v2_new": {
                "priority_order": ["v1", "user glossary", "v2"],
                "entries": len(v2_new),
                "user_glossary_files": len(args.user_glossary),
            },
            "k_values": list(HIT_CUTOFFS),
            "selection_max_bigram_postings": SELECTION_MAX_BIGRAM_POSTINGS,
            "selection_max_trigram_postings": SELECTION_MAX_TRIGRAM_POSTINGS,
            "unit": "gold-term occurrence; unrelated means not listed in that utterance's terms",
            "index_build_time_excluded_from_selection_ms": True,
            "old_full_scan_baseline": {
                "path": str(previous_comparison_path.relative_to(ROOT)),
                "sha256": sha256(previous_comparison_path),
                "reused_when_boundary_only": args.boundary_only,
            },
        },
        "datasets": {
            name: evaluate_dataset(
                items, v1, v2_old, v2_new, boundary_only=args.boundary_only
            )
            for name, items in datasets.items()
        },
    }
    for name, dataset in result["datasets"].items():
        previous_dataset = previous_comparison["datasets"][name]
        dataset["previous_full_scan_baseline"] = {
            row["selector"]: row
            for row in previous_dataset["results"]
            if row["selector"] in {"v1_old", "v2_old"}
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "datasets": {
        name: {
            row["selector"]: {
                "rates": row["hit_rates"],
                "unrelated_at_16": row["unrelated_candidates_at_16"],
                "unrelated_short_read_inner_at_16": row[
                    "unrelated_with_short_read_match_not_covering_run_at_16"
                ],
                "median_ms": row["selection_ms_median"],
                "p90_ms": row["selection_ms_p90"],
            }
            for row in dataset["results"]
        }
        | {"short_reading_hiragana_collisions": dataset["short_reading_hiragana_collisions"]}
        for name, dataset in result["datasets"].items()
    }}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
