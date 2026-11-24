"""用語集から規則と教師の追加読みを作り、正規化後の重複や同音衝突を除く。"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from rapidfuzz.distance import Levenshtein

from voiceime.formatter.glossary import (
    _DIGIT_READINGS,
    _ENGLISH_LETTER_READINGS,
    _kana_to_romaji,
    _read_jsonl,
    load_glossary,
    normalize_kana,
)

# 数字の日本語読み。二つ以上ある場合も、読みの中で数字の位置を確認してから差し替える。
JAPANESE_DIGITS = {
    "0": ("ゼロ", "レイ"), "1": ("イチ",), "2": ("ニ",), "3": ("サン",),
    "4": ("ヨン", "シ"), "5": ("ゴ",), "6": ("ロク",), "7": ("ナナ", "シチ"),
    "8": ("ハチ",), "9": ("キュウ", "ク"),
}
# 同じ英字をカタカナにするときに生じる局所的な違い。
KANA_PAIRS = (
    ("v", "ヴァ", "バ"), ("v", "ヴィ", "ビ"), ("v", "ヴ", "ブ"),
    ("v", "ヴェ", "ベ"), ("v", "ヴォ", "ボ"),
    ("t", "ティ", "チ"), ("d", "ディ", "ジ"),
)
# 短い促音は閉鎖音の前で脱落する場合がある。全ての箇所を組み合わせて増やさない。
GEMINATE = re.compile(r"ッ(?=[カ-ゴサ-ゾタ-ドパ-ポ])")
# 表記の数字を部分的な別の数字へ読み替えないため、連続数字をひとまとまりで扱う。
NUMERIC_GROUP = re.compile(r"[0-9]+")
# 教師の説明文などから推測で読みを取り出さないため、行全体の形式を固定する。
TEACHER_LINE = re.compile(r"([1-9][0-9]*)[:：]\s*([ァ-ヺー・ 　]+)")
# 無声・有声や日本語のr/lで対応しうる子音を比較用にそろえる。
CONSONANT_GROUPS = str.maketrans({"l": "r", "v": "b", "p": "b", "c": "k", "q": "k", "z": "s"})


def number_readings(digits: str) -> tuple[str, ...]:
    """数字列の英語・日本語の一字読みと、3桁までの日本語の位取り読みを返す。"""
    japanese = "".join(JAPANESE_DIGITS[digit][0] for digit in digits)
    english = "".join(_DIGIT_READINGS[digit] for digit in digits)
    readings = [japanese, english]
    if len(digits) == 1:
        readings.extend(JAPANESE_DIGITS[digits][1:])
    elif len(digits) <= 3 and not digits.startswith("0"):
        hundreds, tens, ones = map(int, digits.zfill(3))
        hundreds_reading = ("", "ヒャク", "ニヒャク", "サンビャク", "ヨンヒャク", "ゴヒャク",
                            "ロッピャク", "ナナヒャク", "ハッピャク", "キュウヒャク")
        cardinal = hundreds_reading[hundreds]
        if tens:
            cardinal += (JAPANESE_DIGITS[str(tens)][0] if tens > 1 else "") + "ジュウ"
        if ones:
            cardinal += JAPANESE_DIGITS[str(ones)][0]
        readings.append(cardinal)
    return tuple(dict.fromkeys(readings))


def number_variants(surface: str, reading: str) -> Iterable[str]:
    """数字が1区間の表記で、既存読みの先頭か末尾の数字に限って差し替える。"""
    groups = list(NUMERIC_GROUP.finditer(surface))
    if len(groups) != 1:
        return
    group = groups[0]
    alternatives = number_readings(group[0])
    for original in sorted(alternatives, key=len, reverse=True):
        if group.start() == 0 and reading.startswith(original):
            yield from (variant + reading[len(original):] for variant in alternatives)
            break
        if group.end() == len(surface) and reading.endswith(original):
            yield from (reading[:-len(original)] + variant for variant in alternatives)
            break


def spelled_readings(surface: str) -> Iterable[str]:
    """短い大文字略語の各文字を順に読む。演算子を含む語は元の読みを保つ。"""
    if not re.fullmatch(r"[A-Za-z0-9 ._-]+", surface):
        return
    tokens = re.findall(r"[A-Za-z0-9]+", surface)
    if not tokens or sum(map(len, tokens)) > 8 or not all(
        token.isupper() or token.isdigit() or bool(re.search(r"[A-Z]{2}", token))
        for token in tokens
    ):
        return
    for digit_reading in (_DIGIT_READINGS, {k: v[0] for k, v in JAPANESE_DIGITS.items()}):
        yield "".join(
            digit_reading[char] if char.isdigit() else _ENGLISH_LETTER_READINGS[char.upper()]
            for token in tokens
            for char in token
        )


def suffix_variants(surface: str, reading: str) -> Iterable[str]:
    """語尾の綴りと既存読みの両方が対応する場合に、別の読み方を作る。"""
    word_match = re.search(r"[a-z]{4,}$", surface)
    if not word_match:
        return
    word = word_match[0]
    if word.endswith("ed"):
        pairs = (("テッド", "ティド"), ("デッド", "ディド"), ("エッド", "イド"))
    elif word.endswith("d"):
        # -er に付く d を音で読むときは、-er の長音を補う。
        ending = "ード" if word.endswith("erd") and re.search(r"[ァ-ヲ]ディー?$", reading) else "ド"
        pairs = (("ディー", ending), ("ディ", ending))
    elif word.endswith("er"):
        pairs = (("ラー", "レル"), ("ナー", "ネル"), ("ター", "テル"), ("カー", "ケル"))
    else:
        return
    for left, right in pairs:
        if reading.endswith(left) and len(reading) > len(left) + 1:
            yield reading[:-len(left)] + right


def rule_variants(surface: str, readings: Iterable[str]) -> Iterable[str]:
    """1候補に1つの規則を適用する。合成規則で候補を増やして誤選択を広げない。"""
    surface = unicodedata.normalize("NFKC", surface)
    yield from spelled_readings(surface)
    surface = surface.lower()
    for raw_reading in readings:
        reading = normalize_kana(raw_reading, ignore_long_vowel=False)
        yield from number_variants(surface, reading)
        yield from suffix_variants(surface, reading)
        for match in GEMINATE.finditer(reading):
            yield reading[:match.start()] + reading[match.end():]
        for spelling, left, right in KANA_PAIRS:
            if spelling not in surface:
                continue
            for old, new in ((left, right), (right, left)):
                for match in re.finditer(old, reading):
                    if old == "ヴ" and reading[match.end():match.end() + 1] in ("ァ", "ィ", "ェ", "ォ"):
                        continue
                    yield reading[:match.start()] + new + reading[match.end():]
        # 伸ばして読むオ段の「ウ」と末尾の長音を入れ替える。
        # 「ー」だけの有無は索引で吸収するため、別の候補に数えない。
        if re.search(r"[オコゴソゾトドノホボポモヨロョ]ウ$", reading):
            yield reading[:-1] + "ー"


def sound_key(text: str) -> str:
    """読みと綴りで順序を比較できるように、母音、長音と子音の連続を畳む。"""
    roman = _kana_to_romaji(text.replace("ッ", "")).translate(CONSONANT_GROUPS)
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiou]", "", roman))


def numbers_in_order(surface: str, reading: str) -> bool:
    """候補の読みの中に、表記の数字の読みが桁順に含まれることを確認する。"""
    for digits in NUMERIC_GROUP.findall(surface):
        ends = [
            start + len(key)
            for pronunciation in number_readings(digits)
            if (start := reading.find(key := normalize_kana(pronunciation))) >= 0
        ]
        if not ends:
            return False
        reading = reading[min(ends):]
    return True


def check_teacher_reading(surface: str, readings: tuple[str, ...], candidate: str) -> bool:
    """数字、読みの長さ、先頭・末尾と子音列の順が表記または既存読みと対応するか調べる。"""
    surface = unicodedata.normalize("NFKC", surface)
    normalized = normalize_kana(candidate)
    if not re.fullmatch(r"[ァ-ヺ]{3,}", normalized) or not numbers_in_order(surface, normalized):
        return False
    # 数字の位置は上で確認した。元の読み全体からの省略・付け足しも長さで弾く。
    if readings and not any(
        0.75 <= len(normalized) / max(1, len(normalize_kana(reading))) <= 1.33
        for reading in readings
    ):
        return False
    if normalized in {normalize_kana(reading) for reading in spelled_readings(surface)}:
        return True
    target = sound_key(candidate)
    if len(target) < 2:
        return False
    for reference in (*readings, surface):
        source = sound_key(reference)
        if not source or source[0] != target[0] or source[-1] != target[-1]:
            continue
        max_edits = max(1, min(len(source), len(target)) // 4)
        if Levenshtein.distance(source, target, score_cutoff=max_edits) <= max_edits:
            # 短語では子音の一致だけで遠い音を許さず、仮名自体にも対応を求める。
            if len(target) <= 3 and reference in readings and Levenshtein.normalized_similarity(
                normalize_kana(reference), normalized
            ) < 0.5:
                continue
            return True
    return False


def teacher_candidates(requests_path: Path, responses_path: Path,
                       counts: Counter[str]) -> dict[str, str]:
    """同じ要求IDの回答だけから番号を戻し、欠けた回答や重複は検知する。"""
    request_rows = _read_jsonl(requests_path)
    response_rows = _read_jsonl(responses_path)
    requests = {row["id"]: row["surfaces"] for row in request_rows}
    responses = {row["id"]: row for row in response_rows}
    if requests.keys() != responses.keys() or len(request_rows) != len(requests) or len(response_rows) != len(responses):
        raise ValueError("教師の要求と出力のIDが一対一に対応していません")
    counts["teacher_requests"] = len(requests)
    counts["teacher_terms"] = sum(map(len, requests.values()))
    candidates = {}
    for request_id, surfaces in requests.items():
        response = responses[request_id]
        if response["finish_reason"] != "stop":
            counts["teacher_incomplete_responses"] += 1
            continue
        seen: set[int] = set()
        for line in response["text"].strip().splitlines():
            if not line.strip() or line.strip() in {"なし", "```", "```text"}:
                continue
            match = TEACHER_LINE.fullmatch(unicodedata.normalize("NFKC", line.strip()))
            if not match or not 1 <= int(match[1]) <= len(surfaces):
                counts["teacher_invalid_lines"] += 1
                continue
            number = int(match[1])
            surface = surfaces[number - 1]
            if number in seen:
                candidates.pop(surface, None)
                counts["teacher_duplicate_lines"] += 1
                continue
            seen.add(number)
            candidates[surface] = match[2]
    counts["teacher_parseable_candidates"] = len(candidates)
    return candidates


def build(paths: list[Path], requests: Path | None, responses: Path | None,
          output: Path, report: Path) -> None:
    """出典別の件数と、確かめた追加読みだけを既存用語の表記単位で出す。"""
    entries = load_glossary(*paths)
    counts: Counter[str] = Counter(glossary_entries=len(entries))
    candidates = teacher_candidates(requests, responses, counts) if requests and responses else {}
    canonical: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        for reading in entry.readings:
            canonical[normalize_kana(reading)].add(entry.surface)

    proposed: dict[str, dict[str, tuple[str, str]]] = {}
    owners: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        if not re.search(r"[A-Za-z0-9]", unicodedata.normalize("NFKC", entry.surface)):
            continue
        alternatives = {reading: "rule" for reading in rule_variants(entry.surface, entry.readings)}
        candidate = candidates.get(entry.surface)
        if candidate:
            if check_teacher_reading(entry.surface, entry.readings, candidate):
                counts["teacher_passed_correspondence"] += 1
                if normalize_kana(candidate) not in {normalize_kana(reading) for reading in alternatives}:
                    alternatives[candidate] = "teacher"
            else:
                counts["teacher_rejected_correspondence"] += 1
        for reading, source in alternatives.items():
            key = normalize_kana(reading)
            if not re.fullmatch(r"[ァ-ヺ]{3,}", key) or entry.surface in canonical.get(key, ()):
                continue
            if canonical.get(key):
                counts[f"{source}_canonical_collisions"] += 1
                continue
            proposed.setdefault(entry.surface, {}).setdefault(key, (reading, source))
            owners[key].add(entry.surface)

    with output.open("x", encoding="utf-8") as destination:
        for surface, alternatives in proposed.items():
            readings = []
            for key, (reading, source) in alternatives.items():
                if len(owners[key]) == 1:
                    readings.append(reading)
                    counts[f"{source}_accepted_readings"] += 1
                else:
                    counts[f"{source}_alternate_collisions"] += 1
            if readings:
                counts["entries_with_accepted_readings"] += 1
                destination.write(json.dumps({"surface": surface, "readings": readings}, ensure_ascii=False) + "\n")
    with report.open("x", encoding="utf-8") as destination:
        json.dump(dict(counts), destination, ensure_ascii=False, indent=2, sort_keys=True)
        destination.write("\n")


def main() -> None:
    """規則だけ、または事前生成した教師候補を加えて追加読みを出力する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glossary", nargs="+", required=True, type=Path)
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if bool(args.requests) != bool(args.responses):
        parser.error("--requestsと--responsesは同時に指定してください")
    build(args.glossary, args.requests, args.responses, args.output, args.report)


if __name__ == "__main__":
    main()
