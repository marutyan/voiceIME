"""保存済みの1回目のASR結果で選択順、英字読み、候補上限を比較する。"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import time
from pathlib import Path
from typing import Callable, Sequence

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from evaluate_term_selection import (
    SelectionItem,
    has_short_reading_boundary_miss,
    load_items,
    percentile,
    read_jsonl,
    sha256,
)
from voiceime.formatter.glossary import (
    DEFAULT_MIN_SCORE,
    PRIORITY_INTERLEAVE_RATIO,
    GlossaryEntry,
    GlossaryIndex,
    _interleave_rankings,
    _romanized_runs,
    _text_runs,
    load_glossary,
    load_term_list,
    normalize_kana,
    normalize_latin,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/Users/marutyan/PrivateDev/voiceIME/data")
RUNS_ROOT = ROOT / "runs"
TRACE_DEFAULT = Path(
    "/Users/marutyan/PrivateDev/voiceIME-wt/r3-audio/runs/asr-tts/"
    "r3-twopass-20261122/a-test-novel-include-novel-trace.jsonl"
)
HIT_CUTOFFS = (4, 8, 16, 32)
LIMITS = (8, 16, 20, 24, 32)
ASR_HINT_CHAR_LIMIT = 240
SELECTION_LIMIT = 32
_SMALL_KATAKANA = frozenset("ャュョァィゥェォヮヵヶ")

# 例は各分類の件数を変えず、代表的な出力を一定に再掲するためのID。
MISS_ANALYSIS_EXAMPLE_IDS = {
    "kana_hiragana_mixed": ("novel-000011", "novel-000060", "novel-000118"),
    "near_or_partial_reading": ("novel-000077", "novel-000181", "novel-000443"),
    "split_surface_tokens": ("novel-000209", "novel-000292", "novel-000398"),
    "latin_surface_drift": ("novel-000025", "novel-000029", "novel-000150"),
    "number_as_digits": ("novel-000019", "novel-000109", "novel-000303"),
    "no_direct_signal": ("novel-000005", "novel-000097", "novel-000010"),
}


def select_before_revision(
    text: str,
    index: GlossaryIndex,
    max_entries: int = SELECTION_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[GlossaryEntry]:
    """現行変更前の優先辞書先行と、発音別名を加える前の候補を再現する。"""
    return select_with_options(
        text,
        index,
        max_entries=max_entries,
        min_score=min_score,
        ranking="priority",
        spell_single_letters=False,
    )


def select_with_options(
    text: str,
    index: GlossaryIndex,
    max_entries: int,
    min_score: float,
    *,
    ranking: str,
    spell_single_letters: bool,
    interleave_ratio: tuple[int, int] = PRIORITY_INTERLEAVE_RATIO,
) -> list[GlossaryEntry]:
    """順位方式と一字読み変換を切り替え、条件比較用の候補を返す。"""
    kana_runs = _text_runs(text, "kana", ignore_long_vowel=True)
    latin_runs = _text_runs(text, "latin")
    romanized_runs = _romanized_runs(text, spell_single_letters=spell_single_letters)
    candidate_indexes = index._candidate_key_indexes(kana_runs, latin_runs, romanized_runs)
    scores: dict[int, float] = {}
    for key_index in candidate_indexes:
        key = index.keys[key_index]
        score = index._score_key(key, kana_runs, latin_runs, romanized_runs, min_score)
        if score >= min_score:
            scores[key.entry_index] = max(scores.get(key.entry_index, 0.0), score)

    priority_ranked = sorted(
        scores.items(),
        key=lambda item: (
            not index.entries[item[0]].priority,
            -item[1],
            item[0],
        ),
    )
    score_ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if ranking == "priority":
        ranked = [entry_index for entry_index, _ in priority_ranked]
    elif ranking == "score":
        ranked = [entry_index for entry_index, _ in score_ranked]
    elif ranking == "interleave":
        ranked = _interleave_rankings(
            [entry_index for entry_index, _ in priority_ranked],
            [entry_index for entry_index, _ in score_ranked],
            *interleave_ratio,
            max_entries,
        )
    else:
        raise ValueError(f"unknown ranking mode: {ranking}")
    return [index.entries[entry_index] for entry_index in ranked[:max_entries]]


def _hint_entries(
    entries: Sequence[GlossaryEntry], max_terms: int, max_chars: int
) -> list[GlossaryEntry]:
    """ASRへsurface=reading形式で渡す語を、件数と240文字の両方で絞る。"""
    selected: list[GlossaryEntry] = []
    for entry in entries:
        if len(selected) >= max_terms or not entry.readings:
            continue
        candidate = [*selected, entry]
        joined = "\n".join(f"{item.surface}={item.readings[0]}" for item in candidate)
        if len(joined) <= max_chars:
            selected.append(entry)
    return selected


def _hit_count(selected: Sequence[GlossaryEntry], gold_terms: Sequence[str]) -> int:
    """選択表記が正解語に含まれる正解用語の数を返す。"""
    selected_surfaces = {entry.surface for entry in selected}
    return sum(term in selected_surfaces for term in gold_terms)


def evaluate_selector(
    items: Sequence[SelectionItem],
    entries: Sequence[GlossaryEntry],
    selector: Callable[[str, GlossaryIndex, int], list[GlossaryEntry]],
    selector_name: str,
) -> dict:
    """上位K語、正解外候補、短い読みの内側一致、処理時間を集計する。"""
    index_started = time.perf_counter()
    index = GlossaryIndex(entries)
    index_build_ms = (time.perf_counter() - index_started) * 1000
    vocabulary = {entry.surface for entry in entries}
    hits = dict.fromkeys(HIT_CUTOFFS, 0)
    total_gold = 0
    unavailable_gold = 0
    unrelated_at_16 = 0
    inner_short_at_16 = 0
    asr_hint_gold_hits = 0
    asr_hint_unrelated = 0
    asr_hint_inner_short = 0
    formatter_gold_hits = 0
    formatter_unrelated = 0
    formatter_inner_short = 0
    selection_ms: list[float] = []
    asr_limit_hits = dict.fromkeys(LIMITS, 0)
    formatter_limit_hits = dict.fromkeys(LIMITS, 0)
    asr_limit_selected = dict.fromkeys(LIMITS, 0)
    formatter_limit_selected = dict.fromkeys(LIMITS, 0)

    for item in items:
        eligible_gold = [term for term in item.gold_terms if term in vocabulary]
        total_gold += len(eligible_gold)
        unavailable_gold += len(item.gold_terms) - len(eligible_gold)
        started = time.perf_counter()
        ranked = selector(item.text, index, SELECTION_LIMIT)
        selection_ms.append((time.perf_counter() - started) * 1000)
        gold_set = set(item.gold_terms)
        for cutoff in HIT_CUTOFFS:
            hits[cutoff] += _hit_count(ranked[:cutoff], eligible_gold)

        legacy_runs = _romanized_runs(item.text, spell_single_letters=False)
        for entry in ranked[:16]:
            if entry.surface in gold_set:
                continue
            unrelated_at_16 += 1
            inner_short_at_16 += has_short_reading_boundary_miss(entry, legacy_runs)[1]

        asr_pool = selector(item.text, index, 20)
        asr_hints = _hint_entries(asr_pool, 16, ASR_HINT_CHAR_LIMIT)
        formatter_terms = ranked[:20]
        asr_hint_gold_hits += _hit_count(asr_hints, eligible_gold)
        formatter_gold_hits += _hit_count(formatter_terms, eligible_gold)
        for selected_terms, item_metrics in (
            (asr_hints, "asr"),
            (formatter_terms, "formatter"),
        ):
            for entry in selected_terms:
                if entry.surface in gold_set:
                    continue
                if item_metrics == "asr":
                    asr_hint_unrelated += 1
                    asr_hint_inner_short += has_short_reading_boundary_miss(entry, legacy_runs)[1]
                else:
                    formatter_unrelated += 1
                    formatter_inner_short += has_short_reading_boundary_miss(entry, legacy_runs)[1]

        for limit in LIMITS:
            asr_limited = _hint_entries(asr_pool, min(limit, 20), ASR_HINT_CHAR_LIMIT)
            formatter_limited = ranked[:limit]
            asr_limit_hits[limit] += _hit_count(asr_limited, eligible_gold)
            formatter_limit_hits[limit] += _hit_count(formatter_limited, eligible_gold)
            asr_limit_selected[limit] += len(asr_limited)
            formatter_limit_selected[limit] += len(formatter_limited)

    return {
        "selector": selector_name,
        "utterances": len(items),
        "gold_terms_available": total_gold,
        "gold_terms_not_in_glossary": unavailable_gold,
        "hit_counts": {str(k): hits[k] for k in HIT_CUTOFFS},
        "hit_rates": {
            str(k): hits[k] / total_gold if total_gold else None for k in HIT_CUTOFFS
        },
        "unrelated_candidates_at_16": unrelated_at_16,
        "unrelated_short_read_strictly_inside_at_16": inner_short_at_16,
        "asr_hints_16_240": {
            "gold_hits": asr_hint_gold_hits,
            "gold_rate": asr_hint_gold_hits / total_gold if total_gold else None,
            "unrelated_candidates": asr_hint_unrelated,
            "unrelated_short_read_strictly_inside": asr_hint_inner_short,
        },
        "formatter_candidates_20": {
            "gold_hits": formatter_gold_hits,
            "gold_rate": formatter_gold_hits / total_gold if total_gold else None,
            "unrelated_candidates": formatter_unrelated,
            "unrelated_short_read_strictly_inside": formatter_inner_short,
        },
        "selection_ms_median_at_32": statistics.median(selection_ms) if selection_ms else 0,
        "selection_ms_p90_at_32": percentile(selection_ms, 0.9) if selection_ms else 0,
        "index_build_ms": index_build_ms,
        "limit_sensitivity": {
            "asr_hints_surface_reading_240_chars": {
                str(k): {
                    "gold_hits": asr_limit_hits[k],
                    "hit_rate": asr_limit_hits[k] / total_gold if total_gold else None,
                    "mean_selected_terms": asr_limit_selected[k] / len(items) if items else 0,
                }
                for k in LIMITS
            },
            "formatter_terms": {
                str(k): {
                    "gold_hits": formatter_limit_hits[k],
                    "hit_rate": formatter_limit_hits[k] / total_gold if total_gold else None,
                    "mean_selected_terms": formatter_limit_selected[k] / len(items) if items else 0,
                }
                for k in LIMITS
            },
        },
    }


def _kana_groups(text: str) -> list[tuple[str, bool]]:
    """読みの照合診断用に、ひらがな・カタカナの連続区間を正規化して返す。"""
    groups: list[tuple[str, bool]] = []
    current: list[str] = []
    contains_hiragana = False
    for character in text:
        is_kana = (
            "\u3041" <= character <= "\u3096"
            or "\u30a1" <= character <= "\u30fa"
            or character == "ー"
            or "\u31f0" <= character <= "\u31ff"
        )
        if is_kana:
            current.append(character)
            contains_hiragana |= "\u3041" <= character <= "\u3096"
        elif current:
            groups.append((normalize_kana("".join(current), ignore_long_vowel=False), contains_hiragana))
            current.clear()
            contains_hiragana = False
    if current:
        groups.append((normalize_kana("".join(current), ignore_long_vowel=False), contains_hiragana))
    return groups


def _mora_units(reading: str) -> list[str]:
    """拗音などの小書き仮名を直前へ結び、編集距離をモーラ単位にする。"""
    units: list[str] = []
    for character in normalize_kana(reading, ignore_long_vowel=False):
        if character in _SMALL_KATAKANA and units:
            units[-1] += character
        else:
            units.append(character)
    return units


def _has_near_or_partial_reading(entry: GlossaryEntry, groups: Sequence[tuple[str, bool]]) -> bool:
    """読みの一部が残るか、許容した1〜2モーラ差で連続仮名区間に近いか調べる。"""
    for reading in entry.readings:
        target = _mora_units(reading)
        if not target:
            continue
        for observed, _ in groups:
            observed_units = _mora_units(observed)
            for window_size in range(max(1, len(target) - 2), len(target) + 3):
                if window_size > len(observed_units):
                    continue
                for start in range(len(observed_units) - window_size + 1):
                    window = observed_units[start : start + window_size]
                    edit_distance = Levenshtein.distance(target, window)
                    similarity = fuzz.ratio("".join(target), "".join(window))
                    coverage = len(window) / len(target)
                    if edit_distance == 1 and similarity >= 55 and coverage >= 0.75:
                        return True
                    if (
                        edit_distance == 2
                        and len(target) >= 6
                        and similarity >= 70
                        and coverage >= 0.75
                    ):
                        return True
    return False


def _surface_token_matches(entry: GlossaryEntry, text: str) -> int:
    """ASCII表記の語を順序どおりに追い、近いASR英字token数を数える。"""
    surface_tokens = re.findall(r"[A-Za-z0-9]+", entry.surface.lower())
    text_tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    if len(surface_tokens) < 2:
        return 0
    matched = 0
    next_text_token = 0
    for surface_token in surface_tokens:
        for index in range(next_text_token, len(text_tokens)):
            text_token = text_tokens[index]
            if min(len(surface_token), len(text_token)) < 3:
                continue
            if fuzz.ratio(surface_token, text_token) >= 60:
                matched += 1
                next_text_token = index + 1
                break
    return matched


def _latin_surface_similarity(entry: GlossaryEntry, text: str) -> float:
    """正規化した表記と、ASR英字tokenを1〜5語連結した範囲の最大類似度を返す。"""
    surface = normalize_latin(entry.surface)
    text_tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    best = 0.0
    if not surface:
        return best
    for start in range(len(text_tokens)):
        for end in range(start + 1, min(len(text_tokens), start + 5) + 1):
            candidate = "".join(text_tokens[start:end])
            best = max(best, fuzz.ratio(surface, candidate))
    return best


def _has_number_written_as_digits(entry: GlossaryEntry, text: str) -> bool:
    """表記の数字がASRにも現れ、直前の仮名が読みの先頭と一致するか調べる。"""
    digit_groups = re.findall(r"\d+", entry.surface)
    if not digit_groups:
        return False
    digit_pattern = r"\D*".join(re.escape(group) for group in digit_groups)
    for match in re.finditer(digit_pattern, text):
        kana_before = re.search(
            r"[\u3041-\u3096\u30a1-\u30faー\u31f0-\u31ff]+$",
            text[: match.start()],
        )
        if kana_before is None:
            continue
        prefix = normalize_kana(kana_before.group())
        if len(prefix) >= 3 and any(
            normalize_kana(reading).startswith(prefix) for reading in entry.readings
        ):
            return True
    return False


def analyze_test_novel_misses(
    items: Sequence[SelectionItem], entries: Sequence[GlossaryEntry]
) -> dict:
    """交互2:1の上位32語に入らないtest-novel語を、文字列の手掛かりで分類する。"""
    category_details = {
        "kana_hiragana_mixed": {
            "definition": "正解読みがひらがなを含む連続区間に、長音を無視した正規化後そのまま含まれる。",
        },
        "near_or_partial_reading": {
            "definition": "読みと連続仮名区間の最良一致が、1モーラ差または6モーラ以上で2モーラ差の基準を満たす。部分一致も含む。",
        },
        "split_surface_tokens": {
            "definition": "ASCII表記の複数tokenのうち2つ以上を、順序を保ったままASRの英字tokenへ類似度60%以上で対応できる。",
        },
        "latin_surface_drift": {
            "definition": "上記以外で、正規化表記と連続する1〜5個のASR英字tokenの最大類似度が55%以上。",
        },
        "number_as_digits": {
            "definition": "表記内の数字がASRに現れ、その直前の仮名が正解読みの先頭3文字以上と一致する。",
        },
        "no_direct_signal": {
            "definition": "上の文字列基準に当たらない残り。漢字語への置換、数字以外の表記変更、大きな音崩れを区別せず含む。",
        },
    }
    by_surface = {entry.surface: entry for entry in entries}
    by_id: dict[str, dict] = {}
    selection_index = GlossaryIndex(entries)
    for item in items:
        selected = select_with_options(
            item.text,
            selection_index,
            SELECTION_LIMIT,
            DEFAULT_MIN_SCORE,
            ranking="interleave",
            spell_single_letters=True,
            interleave_ratio=(2, 1),
        )
        selected_surfaces = {entry.surface for entry in selected}
        groups = _kana_groups(item.text)
        flat_kana = "".join(normalize_kana(group) for group, _ in groups)
        for gold_surface in item.gold_terms:
            if gold_surface in selected_surfaces:
                continue
            entry = by_surface.get(gold_surface)
            if entry is None:
                raise ValueError(f"test-novel正解語が辞書にない: {gold_surface}")
            readings = [normalize_kana(reading) for reading in entry.readings]
            has_hiragana_match = any(
                reading in normalize_kana(group) and contains_hiragana
                for reading in readings
                for group, contains_hiragana in groups
            )
            has_split_kana_match = any(
                reading in flat_kana
                and not any(reading in normalize_kana(group) for group, _ in groups)
                for reading in readings
            )
            if has_hiragana_match or has_split_kana_match:
                category = "kana_hiragana_mixed"
            elif _has_near_or_partial_reading(entry, groups):
                category = "near_or_partial_reading"
            elif _has_number_written_as_digits(entry, item.text):
                category = "number_as_digits"
            elif _surface_token_matches(entry, item.text) >= 2:
                category = "split_surface_tokens"
            elif _latin_surface_similarity(entry, item.text) >= 55:
                category = "latin_surface_drift"
            else:
                category = "no_direct_signal"
            by_id[item.item_id] = {
                "item_id": item.item_id,
                "category": category,
                "gold_surface": entry.surface,
                "readings": list(entry.readings),
                "first_pass": item.text,
            }

    categories = {}
    for category, detail in category_details.items():
        category_misses = [row for row in by_id.values() if row["category"] == category]
        example_ids = MISS_ANALYSIS_EXAMPLE_IDS[category]
        examples = [
            by_id[item_id]
            for item_id in example_ids
            if item_id in by_id and by_id[item_id]["category"] == category
        ]
        if len(examples) != len(example_ids):
            raise ValueError(f"miss分析例が期待する分類にない: {category}")
        categories[category] = {
            **detail,
            "count": len(category_misses),
            "examples": examples,
        }
    return {
        "selection": "letter aliases enabled; priority/score interleave=2:1; max_entries=32",
        "missed_terms": len(by_id),
        "miss_rate": len(by_id) / sum(len(item.gold_terms) for item in items) if items else 0,
        "classification_order": list(category_details),
        "categories": categories,
        "classification_is_heuristic": True,
        "note": "カテゴリは優先順で1語1分類。no_direct_signalは音が使えないという断定ではなく、ここに記した文字列規則で手掛かりを抽出できなかった残り。",
    }


def _trace_summary(trace_path: Path, source_path: Path, plain_path: Path) -> dict:
    """test-novel traceの1回目とplain出力の一致、および実際のヒント正解数を照合する。"""
    source_by_id = {row["id"]: row for row in read_jsonl(source_path)}
    plain_by_id = {row["id"]: row for row in read_jsonl(plain_path)}
    trace_rows = read_jsonl(trace_path)
    if set(source_by_id) != set(plain_by_id) or set(source_by_id) != {row["id"] for row in trace_rows}:
        raise ValueError("test-novel source、plain、traceのIDが一致しない")
    first_pass_matches = 0
    gold_hits = 0
    unrelated = 0
    selected_total = 0
    for row in trace_rows:
        item_id = row["id"]
        first_pass_matches += row["first_pass_hyp"] == plain_by_id[item_id]["hyp"]
        gold = set(source_by_id[item_id].get("terms", []))
        hints = row.get("selected_hints", [])
        surfaces = [hint["surface"] for hint in hints]
        selected_total += len(surfaces)
        gold_hits += sum(surface in gold for surface in surfaces)
        unrelated += sum(surface not in gold for surface in surfaces)
    return {
        "trace_sha256": sha256(trace_path),
        "utterances": len(trace_rows),
        "first_pass_matches_plain": first_pass_matches,
        "gold_terms_in_actual_hints": gold_hits,
        "unrelated_actual_hints": unrelated,
        "selected_hint_count": selected_total,
    }


def _parse_args() -> argparse.Namespace:
    """辞書、保存済み評価入力、trace、出力先を受け取る。"""
    parser = argparse.ArgumentParser(description="用語選択の優先度と候補数を再評価する")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--runs-root", type=Path, default=RUNS_ROOT)
    parser.add_argument("--test-novel-trace", type=Path, default=TRACE_DEFAULT)
    parser.add_argument(
        "--output",
        type=Path,
        default=RUNS_ROOT / "term-select" / "mixed-ranking-candidate20.json",
    )
    return parser.parse_args()


def main() -> None:
    """保存済みASR文だけを使い、比較表と集計値を新しいJSONへ保存する。"""
    args = _parse_args()
    v1_path = args.data_root / "text" / "glossary.jsonl"
    v2_path = args.data_root / "text" / "glossary-v2.jsonl"
    excluded_path = args.data_root / "text" / "glossary-v2-excluded.txt"
    excluded = load_term_list(excluded_path)
    entries = load_glossary(v1_path, v2_path, exclude_terms=excluded)
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
    if args.output.exists():
        raise FileExistsError(f"既存評価結果を上書きしない: {args.output}")

    results = {}
    for name, items in datasets.items():
        results[name] = {
            "old_main": evaluate_selector(
                items, entries, select_before_revision, "old_main_priority_first_without_letter_alias"
            ),
            "score_order": evaluate_selector(
                items,
                entries,
                lambda text, index, limit: select_with_options(
                    text,
                    index,
                    limit,
                    DEFAULT_MIN_SCORE,
                    ranking="score",
                    spell_single_letters=True,
                ),
                "score_order_with_letter_alias",
            ),
            "interleave_1_to_1": evaluate_selector(
                items,
                entries,
                lambda text, index, limit: select_with_options(
                    text,
                    index,
                    limit,
                    DEFAULT_MIN_SCORE,
                    ranking="interleave",
                    spell_single_letters=True,
                    interleave_ratio=(1, 1),
                ),
                "interleave_priority_1_score_1",
            ),
            "interleave_2_to_1": evaluate_selector(
                items,
                entries,
                lambda text, index, limit: select_with_options(
                    text,
                    index,
                    limit,
                    DEFAULT_MIN_SCORE,
                    ranking="interleave",
                    spell_single_letters=True,
                    interleave_ratio=(2, 1),
                ),
                "interleave_priority_2_score_1",
            ),
        }

    test_novel_source = args.runs_root / "asr-tts" / "r3-audio-20261122" / "test-novel-source.jsonl"
    test_novel_plain = args.runs_root / "asr-tts" / "r3-audio-20261122" / "test-novel-include-novel-plain.jsonl"
    test_novel_miss_analysis = analyze_test_novel_misses(datasets["test-novel"], entries)
    result = {
        "conditions": {
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "selector_source_sha256": sha256(ROOT / "src" / "voiceime" / "formatter" / "glossary.py"),
            "evaluation_script_sha256": sha256(Path(__file__)),
            "selector_variants": {
                "old_main": "priority-first; no single-letter pronunciation aliases",
                "score_order": "raw score order; single-letter pronunciation aliases",
                "interleave_1_to_1": "one unique term from priority-first rank, then one from score rank",
                "interleave_2_to_1": "two unique terms from priority-first rank, then one from score rank",
            },
            "min_score": DEFAULT_MIN_SCORE,
            "priority_interleave_ratio_default": list(PRIORITY_INTERLEAVE_RATIO),
            "max_ranked_candidates": SELECTION_LIMIT,
            "reported_hit_cutoffs": list(HIT_CUTOFFS),
            "hint_term_limits": [8, 16, 24, 32],
            "asr_candidate_pool_limit": 20,
            "hint_character_limit": ASR_HINT_CHAR_LIMIT,
            "hint_format": "surface=reading; UTF-8 characters counted as Python string length; newline-separated",
            "formatter_term_limits": [8, 16, 24, 32],
            "formatter_current_term_limit": 20,
            "unrelated_definition": "selected surface is absent from that utterance's gold terms; this is annotation-based, not a human semantic judgment",
            "short_interior_definition": "selected non-gold entry has a two-kana reading matching strictly inside a normalized script run",
            "interleave_deduplication": "duplicate indices do not count toward a rank's quota; scan that rank until its quota has new terms or it is exhausted",
            "dictionary": {
                "v1_sha256": sha256(v1_path),
                "v2_sha256": sha256(v2_path),
                "excluded_list_sha256": sha256(excluded_path),
                "entries_after_exclusions": len(entries),
                "excluded_entries_removed": len(load_glossary(v2_path))
                - len(load_glossary(v2_path, exclude_terms=excluded)),
            },
            "inputs": {
                "dev_user_source_sha256": sha256(args.data_root / "dev-user" / "manifest.jsonl"),
                "dev_user_first_pass_sha256": sha256(args.runs_root / "v2gloss" / "asr-v2-t16-s75.hints.jsonl"),
                "test_novel_source_sha256": sha256(test_novel_source),
                "test_novel_first_pass_sha256": sha256(test_novel_plain),
                "val_source_sha256": sha256(args.data_root / "tts" / "val" / "manifest.jsonl"),
                "val_first_pass_sha256": sha256(args.runs_root / "asr-tts" / "haas-val.jsonl"),
            },
            "selection_time_unit": "milliseconds per utterance, index build excluded, max_entries=32",
        },
        "datasets": results,
        "test_novel_top32_miss_analysis": test_novel_miss_analysis,
        "test_novel_trace": _trace_summary(args.test_novel_trace, test_novel_source, test_novel_plain),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    short = {
        name: {
            key: {
                "top_k_rates": value["hit_rates"],
                "asr_hints_16_240": value["asr_hints_16_240"],
                "formatter_candidates_20": value["formatter_candidates_20"],
                "short_inner_at_16": value["unrelated_short_read_strictly_inside_at_16"],
                "median_ms": value["selection_ms_median_at_32"],
                "p90_ms": value["selection_ms_p90_at_32"],
            }
            for key, value in pair.items()
        }
        for name, pair in results.items()
    }
    print(json.dumps({"output": str(args.output), "datasets": short, "trace": result["test_novel_trace"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
