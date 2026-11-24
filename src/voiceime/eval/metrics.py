"""CER、用語、フィラー、遅延の共通計算をまとめる。"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from statistics import median
from typing import Any

import numpy as np
from rapidfuzz.distance import Levenshtein

# 評価でフィラーとして数える語形をここに集約する。`like` は指示どおり除外する。
FILLER_FORMS = (
    "えーと",
    "えーっと",
    "えっと",
    "えー",
    "あー",
    "あのー",
    "あの",
    "その",
    "そのー",
    "まあ",
    "なんか",
    "うーん",
    "んー",
    "ええ",
    "um",
    "uh",
    "er",
    "ah",
)

# 長い語形を先に照合し、`えーと` を `えー` と二重に数えない。
_FILLER_PATTERN = re.compile(
    "|".join(
        (
            rf"(?<![A-Za-z0-9_]){re.escape(form)}(?![A-Za-z0-9_])"
            if form.isascii() and form.isalpha()
            else re.escape(form)
        )
        for form in sorted(FILLER_FORMS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


# CERで同じ語とみなす書き方の組（2026-11-22 本人の承認）。左を右へそろえてから比べる。
# 「%」は記号として後で除かれるため、「15パーセント」と「15%」はどちらも「15」になる。
CER_EQUIVALENT_FORMS = (("パーセント", "%"), ("とき", "時"))


def normalize_for_cer(text: str) -> str:
    """NFKC、小文字化と同じ語の書き方の統一の後、句読点・記号・空白を除く。"""
    normalized = unicodedata.normalize("NFKC", text).lower()
    for form, canonical in CER_EQUIVALENT_FORMS:
        normalized = normalized.replace(form, canonical)
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and unicodedata.category(character)[0] not in {"P", "S"}
    )


def calculate_cer(
    references: Sequence[str], hypotheses: Sequence[str]
) -> dict[str, int | float | None]:
    """文字誤りを置換・挿入・削除に分け、コーパスCERを返す。"""
    if len(references) != len(hypotheses):
        raise ValueError("references と hypotheses の件数が一致しません")

    substitutions = 0
    insertions = 0
    deletions = 0
    reference_characters = 0
    for reference, hypothesis in zip(references, hypotheses, strict=True):
        normalized_reference = normalize_for_cer(reference)
        normalized_hypothesis = normalize_for_cer(hypothesis)
        operations = Levenshtein.editops(
            normalized_reference, normalized_hypothesis
        )
        substitutions += sum(operation.tag == "replace" for operation in operations)
        insertions += sum(operation.tag == "insert" for operation in operations)
        deletions += sum(operation.tag == "delete" for operation in operations)
        reference_characters += len(normalized_reference)

    edit_errors = substitutions + insertions + deletions
    rate = (
        edit_errors / reference_characters if reference_characters else None
    )
    return {
        "edit_errors": edit_errors,
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "reference_characters": reference_characters,
        "rate": rate,
    }


def replace_glossary_surfaces_with_readings(
    text: str, glossary: Sequence[Mapping[str, Any]]
) -> str:
    """表記の違いをCERから除くため、用語surfaceを最初の読みへ置換する。"""
    replacement_by_surface: dict[str, str] = {}
    surfaces: list[str] = []
    for entry in glossary:
        surface = entry.get("surface")
        readings = entry.get("readings")
        if (
            not isinstance(surface, str)
            or not surface
            or not isinstance(readings, list)
            or not readings
            or not isinstance(readings[0], str)
        ):
            continue
        normalized_surface = surface.casefold()
        if normalized_surface not in replacement_by_surface:
            replacement_by_surface[normalized_surface] = readings[0]
            surfaces.append(surface)

    if not surfaces:
        return text

    ordered_surfaces = sorted(surfaces, key=len, reverse=True)
    surface_pattern = re.compile(
        "|".join(re.escape(surface) for surface in ordered_surfaces),
        re.IGNORECASE,
    )

    def replace_match(match: re.Match[str]) -> str:
        """一致したsurfaceに対応する読みを返す。"""
        matched_surface = match.group()
        normalized_surface = matched_surface.casefold()
        if normalized_surface in replacement_by_surface:
            return replacement_by_surface[normalized_surface]
        # re.IGNORECASEがcasefoldと異なるUnicode文字を一致させた場合も置換する。
        for surface in ordered_surfaces:
            if re.fullmatch(re.escape(surface), matched_surface, re.IGNORECASE):
                return replacement_by_surface[surface.casefold()]
        return matched_surface

    return surface_pattern.sub(replace_match, text)


def calculate_term_accuracy(
    terms: Sequence[str], glossary: Sequence[Mapping[str, Any]], hypothesis: str
) -> dict[str, int | float | None]:
    """正解termsを出現回数で数え、厳密表記と読みを許す正答率を返す。"""
    readings_by_surface: dict[str, set[str]] = defaultdict(set)
    for entry in glossary:
        surface = entry.get("surface")
        readings = entry.get("readings")
        if isinstance(surface, str) and isinstance(readings, list):
            readings_by_surface[surface].update(
                reading for reading in readings if isinstance(reading, str)
            )

    exact_correct = 0
    loose_correct = 0
    for surface, expected_count in Counter(terms).items():
        exact_correct += min(expected_count, hypothesis.count(surface))
        matching_forms = {surface, *readings_by_surface.get(surface, ())}
        loose_matches = sum(hypothesis.count(form) for form in matching_forms)
        loose_correct += min(expected_count, loose_matches)

    total = len(terms)
    return {
        "correct": exact_correct,
        "total": total,
        "accuracy": exact_correct / total if total else None,
        "loose_correct": loose_correct,
        "loose_accuracy": loose_correct / total if total else None,
    }


def calculate_term_accuracy_split(
    terms: Sequence[str],
    glossary: Sequence[Mapping[str, Any]],
    hypothesis: str,
    unseen_terms: Collection[str],
) -> dict[str, dict[str, int | float | None]]:
    """正解termsを見えない用語とそれ以外へ分け、同じ定義で正答率を返す。"""
    unseen_set = (
        unseen_terms
        if isinstance(unseen_terms, (set, frozenset))
        else set(unseen_terms)
    )
    unseen = [term for term in terms if term in unseen_set]
    seen = [term for term in terms if term not in unseen_set]
    return {
        "unseen": calculate_term_accuracy(unseen, glossary, hypothesis),
        "seen": calculate_term_accuracy(seen, glossary, hypothesis),
    }


def count_inserted_terms(
    terms: Sequence[str],
    glossary: Sequence[Mapping[str, Any]],
    hypothesis: str,
    *,
    spoken_text: str | None = None,
) -> int:
    """基準文の用語回数を超えてhypに現れたsurfaceの出現数を数える。

    spoken_textが指定されたASRでは、surfaceまたは読みの出現回数を基準にする。
    """
    expected_counts = Counter(terms)
    glossary_surfaces = {
        entry["surface"]
        for entry in glossary
        if isinstance(entry.get("surface"), str)
    }
    if spoken_text is not None:
        expected_counts = Counter(
            {
                surface: _count_glossary_form_occurrences(
                    spoken_text, surface, glossary
                )
                for surface in glossary_surfaces
            }
        )
    return sum(
        max(hypothesis.count(surface) - expected_counts[surface], 0)
        for surface in glossary_surfaces
    )


def _count_glossary_form_occurrences(
    text: str, surface: str, glossary: Sequence[Mapping[str, Any]]
) -> int:
    """surfaceとそのreadingsを選択肢として、重複しない出現数を数える。"""
    forms = {surface} if surface else set()
    for entry in glossary:
        if entry.get("surface") != surface:
            continue
        readings = entry.get("readings")
        if isinstance(readings, list):
            forms.update(
                reading
                for reading in readings
                if isinstance(reading, str) and reading
            )

    if not forms:
        return 0

    pattern = re.compile(
        "|".join(re.escape(form) for form in sorted(forms, key=len, reverse=True)),
        re.IGNORECASE,
    )
    return sum(1 for _ in pattern.finditer(text))


def count_fillers(text: str) -> dict[str, int]:
    """定義済み語形の出現数を数え、英語語形は大小文字をまとめる。"""
    counts = {form: 0 for form in FILLER_FORMS}
    for match in _FILLER_PATTERN.finditer(text):
        form = match.group(0)
        canonical_form = form.lower() if form.isascii() else form
        counts[canonical_form] += 1
    return counts


def count_residual_fillers(reference_text: str, hypothesis: str) -> int:
    """正解文にある同じフィラー語形の回数を出力から差し引く。"""
    reference_counts = count_fillers(reference_text)
    hypothesis_counts = count_fillers(hypothesis)
    return sum(
        max(hypothesis_counts[form] - reference_counts[form], 0)
        for form in FILLER_FORMS
    )


def calculate_filler_metrics(
    references: Sequence[str],
    hypotheses: Sequence[str],
    manifest_fillers: Sequence[int],
) -> dict[str, int | float | None]:
    """有効な出力の残存数を、manifest全体のフィラー数で割る。"""
    if len(references) != len(hypotheses):
        raise ValueError("references と hypotheses の件数が一致しません")
    if any(
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for count in manifest_fillers
    ):
        raise ValueError("manifest_fillers は0以上の整数である必要があります")

    residual_count = sum(
        count_residual_fillers(reference, hypothesis)
        for reference, hypothesis in zip(references, hypotheses, strict=True)
    )
    manifest_count = sum(manifest_fillers)
    return {
        "residual_count": residual_count,
        "manifest_count": manifest_count,
        "residual_rate": residual_count / manifest_count if manifest_count else None,
    }


def calculate_tag_metrics(
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """各tagの件数、CER、正規化後の完全一致率と応答疑い数を集計する。"""
    samples_by_tag: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for sample in samples:
        reference = sample["target_text"]
        hypothesis = sample["hyp"]
        tags = sample.get("tags", [])
        for tag in dict.fromkeys(tags):
            samples_by_tag[tag].append((reference, hypothesis))

    results: dict[str, dict[str, Any]] = {}
    for tag, tagged_samples in samples_by_tag.items():
        references = [reference for reference, _ in tagged_samples]
        hypotheses = [hypothesis for _, hypothesis in tagged_samples]
        normalized_pairs = [
            (normalize_for_cer(reference), normalize_for_cer(hypothesis))
            for reference, hypothesis in tagged_samples
        ]
        exact_matches = sum(
            normalized_reference == normalized_hypothesis
            for normalized_reference, normalized_hypothesis in normalized_pairs
        )
        suspected_responses = (
            sum(
                len(normalized_hypothesis) > 1.5 * len(normalized_reference)
                for normalized_reference, normalized_hypothesis in normalized_pairs
            )
            if tag == "instruction_like"
            else None
        )
        results[tag] = {
            "count": len(tagged_samples),
            "cer": calculate_cer(references, hypotheses),
            "exact_matches": exact_matches,
            "exact_match_rate": exact_matches / len(tagged_samples),
            "suspected_responses": suspected_responses,
        }
    return results


def summarize_latency(latencies: Iterable[float]) -> dict[str, int | float | None]:
    """遅延の件数、中央値、線形補間による90パーセンタイルを返す。"""
    values = [float(value) for value in latencies]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("latency_s は有限の0以上の値である必要があります")
    if not values:
        return {"count": 0, "median_s": None, "p90_s": None}
    return {
        "count": len(values),
        "median_s": float(median(values)),
        "p90_s": float(np.percentile(values, 90, method="linear")),
    }
