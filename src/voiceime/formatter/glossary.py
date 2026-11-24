"""用語集の読み込みと、ASRの出力に近い語だけを選ぶ絞り込み。

用語集全体（数百〜数千語）をプロンプトへ入れると整形が遅くなるため、
ASRの出力にカタカナの読みか英字の表記が近い語だけを選んでLLMへ渡す。
`python -m voiceime.formatter.glossary` で、絞り込みの取りこぼしの割合を測れる。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
import time
import unicodedata
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Literal, Sequence

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

# プロンプトへ渡す用語の最大件数。件数が増えるほど整形の入力が長くなり遅くなる。
DEFAULT_MAX_ENTRIES = 20
# 部分一致の類似度（0〜100）の下限。4文字の読みで1文字違い（75）までを拾う値にしている。
DEFAULT_MIN_SCORE = 75.0
# 評価でvalの正解率を保ち、1:1よりtest-novelの正解率が高かった比率。
PRIORITY_INTERLEAVE_RATIO = (2, 1)
# この文字数以下の読み・表記は曖昧一致だと誤検出が多いため、完全な部分文字列の一致だけを認める。
SHORT_KEY_LENGTH = 2
# 高頻度のn-gramは一般語を大量に引くため、索引からの候補取得に使わない上限。
SELECTION_MAX_TRIGRAM_POSTINGS = 500
SELECTION_MAX_BIGRAM_POSTINGS = 100
# 追加読みの完全一致は、元の読みや表記の100点の一致を優先する。
ALT_READING_SCORE = 99.0
# 短い追加読みは一般語の一部に現れやすいため、カタカナ区間全体の一致だけを認める。
ALT_READING_SUBSTRING_MIN_LENGTH = 5

# 略語の一字読みを用語集へ補う。読みのない略語でもASRの候補にできる。
_ENGLISH_LETTER_READINGS = {
    "A": "エー", "B": "ビー", "C": "シー", "D": "ディー", "E": "イー",
    "F": "エフ", "G": "ジー", "H": "エイチ", "I": "アイ", "J": "ジェー",
    "K": "ケー", "L": "エル", "M": "エム", "N": "エヌ", "O": "オー",
    "P": "ピー", "Q": "キュー", "R": "アール", "S": "エス", "T": "ティー",
    "U": "ユー", "V": "ブイ", "W": "ダブリュー", "X": "エックス", "Y": "ワイ",
    "Z": "ゼット",
}
# 数字を含む略語は、各数字を英語で読む形を一字読みへ加える。
_DIGIT_READINGS = {
    "0": "ゼロ", "1": "ワン", "2": "ツー", "3": "スリー", "4": "フォー",
    "5": "ファイブ", "6": "シックス", "7": "セブン", "8": "エイト", "9": "ナイン",
}
_ASCII_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_UPPERCASE_SEQUENCE_PATTERN = re.compile(r"[A-Z]{2,}")


@dataclass(frozen=True)
class GlossaryEntry:
    """用語集の1語。`alt_readings`は選択専用の読み、`aliases`は整形前に直す誤認識表記。"""

    surface: str
    readings: tuple[str, ...]
    replace_from: tuple[str, ...] = ()
    priority: bool = True
    alt_readings: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


def add_abbreviation_readings(
    entries: Iterable[GlossaryEntry], *, enabled: bool = True
) -> list[GlossaryEntry]:
    """略語の一字読みを、用語集ファイルを変えずに読み込み結果へ加える。"""
    result: list[GlossaryEntry] = []
    for entry in entries:
        tokens = _ASCII_TOKEN_PATTERN.findall(entry.surface)
        has_abbreviation_token = any(
            any(character.isdigit() for character in token)
            or _UPPERCASE_SEQUENCE_PATTERN.search(token)
            for token in tokens
        )
        all_tokens_are_abbreviations = bool(tokens) and all(
            any(character.isdigit() for character in token)
            or _UPPERCASE_SEQUENCE_PATTERN.search(token)
            or len(token) == 1
            for token in tokens
        )
        if not enabled or not has_abbreviation_token or not all_tokens_are_abbreviations:
            result.append(entry)
            continue

        spelled_reading = "".join(
            _ENGLISH_LETTER_READINGS.get(character.upper(), _DIGIT_READINGS.get(character, ""))
            for token in tokens
            for character in token
        )
        readings = list(entry.readings)
        if spelled_reading and spelled_reading not in readings:
            readings.append(spelled_reading)
        result.append(replace(entry, readings=tuple(readings)))
    return result


def entry_from_record(record: dict, *, priority: bool = True) -> GlossaryEntry:
    """JSONの1件を用語に変換する。旧形式の`reading`と任意の置換欄にも対応する。"""
    readings = record.get("readings")
    if readings is None:
        readings = [record["reading"]] if record.get("reading") else []
    elif isinstance(readings, str):
        readings = [readings]
    replace_from = record.get("replace_from", [])
    if isinstance(replace_from, str) or not isinstance(replace_from, list):
        raise ValueError("replace_fromは文字列の配列で指定する")
    if not all(isinstance(value, str) for value in replace_from):
        raise ValueError("replace_fromは文字列の配列で指定する")
    aliases = record.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(value, str) for value in aliases):
        raise ValueError("aliasesは文字列の配列で指定する")
    return GlossaryEntry(
        surface=record["surface"],
        readings=tuple(readings),
        replace_from=tuple(replace_from),
        priority=priority,
        aliases=tuple(aliases),
    )


def merge_entries(entries: Iterable[GlossaryEntry]) -> list[GlossaryEntry]:
    """同じ表記の語をまとめ、読み・確定置換候補・別名の登録順を保つ。"""
    readings_by_surface: dict[str, list[str]] = {}
    replacements_by_surface: dict[str, list[str]] = {}
    priorities_by_surface: dict[str, bool] = {}
    alt_readings_by_surface: dict[str, list[str]] = {}
    aliases_by_surface: dict[str, dict[str, None]] = {}
    for entry in entries:
        merged = readings_by_surface.setdefault(entry.surface, [])
        merged.extend(r for r in entry.readings if r not in merged)
        replacements = replacements_by_surface.setdefault(entry.surface, [])
        replacements.extend(alias for alias in entry.replace_from if alias not in replacements)
        priorities_by_surface[entry.surface] = priorities_by_surface.get(entry.surface, False) or entry.priority
        alt_readings = alt_readings_by_surface.setdefault(entry.surface, [])
        alt_readings.extend(reading for reading in entry.alt_readings if reading not in alt_readings)
        aliases_by_surface.setdefault(entry.surface, {}).update(dict.fromkeys(entry.aliases))
    return [
        GlossaryEntry(
            surface,
            tuple(readings),
            tuple(replacements_by_surface[surface]),
            priorities_by_surface[surface],
            tuple(alt_readings_by_surface[surface]),
            tuple(aliases_by_surface[surface]),
        )
        for surface, readings in readings_by_surface.items()
    ]


def load_term_list(path: str | Path) -> set[str]:
    """1行1語のテキストファイルから用語表記の集合を読み込む。空行は無視し、前後の空白を除く。"""
    text = Path(path).read_text(encoding="utf-8")
    return {stripped for line in text.splitlines() if (stripped := line.strip())}


def exclude_glossary(
    entries: Iterable[GlossaryEntry], exclude_terms: Iterable[str] | None
) -> list[GlossaryEntry]:
    """指定した表記の語を用語集から除き、残りの順序を保って返す。"""
    if not exclude_terms:
        return list(entries)
    excluded = exclude_terms if isinstance(exclude_terms, (set, frozenset)) else set(exclude_terms)
    return [entry for entry in entries if entry.surface not in excluded]


def load_glossary(
    *paths: str | Path,
    exclude_terms: Iterable[str] | None = None,
    expand_abbreviation_readings: bool = False,
    alt_readings_path: str | Path | None = None,
) -> list[GlossaryEntry]:
    """用語集のファイル（1行1語のJSONL、または配列のJSON）を読み込む。

    複数のファイル（学習用の用語集と本人用の用語集など）を渡すと、指定の順に並べ、同じ表記の語は読みと別名をまとめる。
    `exclude_terms`を指定すると、該当する`surface`の語を読み込み結果から除く。
    `alt_readings_path`は選択専用の読みを既存の語にだけ足す。元の読みと置換候補はそのまま使う。
    """
    if not paths:
        raise ValueError("用語集のファイルを1つ以上指定する")
    records = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        if text.lstrip().startswith("["):
            source_records = json.loads(text)
        else:
            source_records = [json.loads(line) for line in text.splitlines() if line.strip()]
        # v2の大量候補は、本人用とv1の語を選んだ後に空き枠を埋める。
        is_expanded_glossary = Path(path).name.startswith("glossary-v2")
        records.extend(
            entry_from_record(record, priority=not is_expanded_glossary)
            for record in source_records
        )
    entries = merge_entries(records)
    if expand_abbreviation_readings:
        entries = add_abbreviation_readings(entries)
    entries = exclude_glossary(entries, exclude_terms)
    if alt_readings_path is None:
        return entries

    extra: dict[str, dict[str, None]] = {}
    for record in _read_jsonl(alt_readings_path):
        surface, readings = record["surface"], record["readings"]
        if not isinstance(surface, str) or not isinstance(readings, list) or not all(
            isinstance(reading, str) and re.fullmatch(r"[ァ-ヺー]+", normalize_kana(reading))
            for reading in readings
        ):
            raise ValueError(f"追加読みはsurfaceとカタカナのreadings配列で指定する: {alt_readings_path}")
        extra.setdefault(surface, {}).update(dict.fromkeys(readings))
    return [
        replace(entry, alt_readings=tuple(extra[entry.surface]))
        if entry.surface in extra else entry
        for entry in entries
    ]


def glossary_from_rows(
    rows: Iterable[dict],
    *,
    exclude_terms: Iterable[str] | None = None,
    expand_abbreviation_readings: bool = False,
) -> list[GlossaryEntry]:
    """manifestの各行の`glossary`を合わせて、全体の用語集として使う。`exclude_terms`で指定語を除ける。"""
    entries = merge_entries(
        entry_from_record(g) for row in rows for g in row.get("glossary", [])
    )
    if expand_abbreviation_readings:
        entries = add_abbreviation_readings(entries)
    return exclude_glossary(entries, exclude_terms)


def to_katakana(text: str) -> str:
    """ひらがなをカタカナへ1文字ずつ置き換える。文字数は変えない（置換位置の対応を保つため）。"""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


# 読みの揺れ（長音、中黒、空白）で一致が落ちないよう、比較の前に取り除く文字。
_KANA_IGNORED = str.maketrans("", "", "ー・ 　-")
# 英字の表記の揺れ（空白、ハイフン、ピリオドなど）を無視するために取り除く文字。
_LATIN_IGNORED = str.maketrans("", "", " 　-_.・")
# カタカナ区間の正規化で読みの揺れとして除く文字。
_KANA_IGNORED_CHARS = frozenset("ー・ 　-")
# 英数字区間の正規化で表記の揺れとして除く文字。
_LATIN_IGNORED_CHARS = frozenset(" 　-_.・")
# 用語の読みと英字表記を元文の別々の連続区間で照合する。
TextScript = Literal["kana", "latin"]


@dataclass(frozen=True)
class TextMatch:
    """照合に成功した元の文の範囲と類似度。"""

    start: int
    end: int
    score: float


@dataclass(frozen=True)
class _TextRun:
    """ひとつながりのカタカナまたは英数字と、元の文字位置との対応。"""

    text: str
    start: int
    end: int
    source_starts: tuple[int, ...]
    source_ends: tuple[int, ...]


def normalize_kana(text: str, ignore_long_vowel: bool = True) -> str:
    """用語読みをNFKC・カタカナへ揃え、必要に応じて長音や区切り記号を無視する。"""
    normalized = to_katakana(unicodedata.normalize("NFKC", text))
    if ignore_long_vowel:
        return normalized.translate(_KANA_IGNORED)
    return normalized.translate(str.maketrans("", "", "・ 　-"))


def normalize_latin(text: str) -> str:
    """英字表記をNFKC・小文字へ揃え、空白や区切り記号を比較から外す。"""
    return unicodedata.normalize("NFKC", text).lower().translate(_LATIN_IGNORED)


def _is_script_character(character: str, script: TextScript) -> bool:
    """元の文の文字がカタカナ区間または英数字区間に属するかを調べる。"""
    if script == "kana":
        normalized = unicodedata.normalize("NFKC", character)
        return bool(normalized) and all(
            "\u30a1" <= item <= "\u30ff" or "\u31f0" <= item <= "\u31ff" or unicodedata.combining(item)
            for item in normalized
        )
    normalized = unicodedata.normalize("NFKC", character)
    return bool(normalized) and all(item.isascii() and item.isalnum() for item in normalized)


def _normalized_run(raw: str, start: int, script: TextScript, ignore_long_vowel: bool) -> _TextRun:
    """連続部分を正規化し、合成文字があっても元位置へ戻せる対応表を作る。"""
    expanded_chars: list[str] = []
    expanded_starts: list[int] = []
    expanded_ends: list[int] = []
    for offset, character in enumerate(raw):
        normalized = unicodedata.normalize("NFKC", character)
        normalized = to_katakana(normalized) if script == "kana" else normalized.lower()
        expanded_chars.extend(normalized)
        expanded_starts.extend([start + offset] * len(normalized))
        expanded_ends.extend([start + offset + 1] * len(normalized))

    normalized = unicodedata.normalize("NFKC", raw)
    normalized = to_katakana(normalized) if script == "kana" else normalized.lower()
    expanded = "".join(expanded_chars)
    if expanded == normalized:
        normalized_starts = expanded_starts
        normalized_ends = expanded_ends
    else:
        normalized_starts = []
        normalized_ends = []
        matcher = difflib.SequenceMatcher(a=expanded, b=normalized, autojunk=False)
        for tag, source_start, source_end, target_start, target_end in matcher.get_opcodes():
            if tag == "equal":
                normalized_starts.extend(expanded_starts[source_start:source_end])
                normalized_ends.extend(expanded_ends[source_start:source_end])
                continue
            if source_start < source_end:
                original_start = min(expanded_starts[source_start:source_end])
                original_end = max(expanded_ends[source_start:source_end])
            else:
                original_start = start + min(source_start, len(raw) - 1)
                original_end = original_start + 1
            normalized_starts.extend([original_start] * (target_end - target_start))
            normalized_ends.extend([original_end] * (target_end - target_start))

    ignored = _KANA_IGNORED_CHARS if script == "kana" and ignore_long_vowel else frozenset("・ 　-")
    if script == "latin":
        ignored = _LATIN_IGNORED_CHARS
    kept_chars: list[str] = []
    kept_starts: list[int] = []
    kept_ends: list[int] = []
    for index, character in enumerate(normalized):
        if character in ignored:
            continue
        kept_chars.append(character)
        kept_starts.append(normalized_starts[index])
        kept_ends.append(normalized_ends[index])
    return _TextRun("".join(kept_chars), start, start + len(raw), tuple(kept_starts), tuple(kept_ends))


def _text_runs(text: str, script: TextScript, ignore_long_vowel: bool = False) -> list[_TextRun]:
    """指定した文字種の連続部分を正規化し、元の文字位置を保って返す。"""
    runs: list[_TextRun] = []
    run_start: int | None = None

    def save_run() -> None:
        """現在の文字種区間を保存して、一時状態を空にする。"""
        nonlocal run_start
        if run_start is not None:
            run = _normalized_run(text[run_start:index], run_start, script, ignore_long_vowel)
            if run.text:
                runs.append(run)
        run_start = None

    for index, character in enumerate(text):
        if not _is_script_character(character, script):
            save_run()
            continue
        run_start = index if run_start is None else run_start
    index = len(text)
    save_run()
    return runs


# 用語集のカタカナ読みと、ASRが英字で出した読みを同じ検索キーへそろえる。
_KANA_ROMAJI = {
    **dict(zip("あいうえお", ("a", "i", "u", "e", "o"))),
    **dict(zip("かきくけこ", ("ka", "ki", "ku", "ke", "ko"))),
    **dict(zip("がぎぐげご", ("ga", "gi", "gu", "ge", "go"))),
    **dict(zip("さしすせそ", ("sa", "shi", "su", "se", "so"))),
    **dict(zip("ざじずぜぞ", ("za", "ji", "zu", "ze", "zo"))),
    **dict(zip("たちつてと", ("ta", "chi", "tsu", "te", "to"))),
    **dict(zip("だぢづでど", ("da", "ji", "zu", "de", "do"))),
    **dict(zip("なにぬねの", ("na", "ni", "nu", "ne", "no"))),
    **dict(zip("はひふへほ", ("ha", "hi", "fu", "he", "ho"))),
    **dict(zip("ばびぶべぼ", ("ba", "bi", "bu", "be", "bo"))),
    **dict(zip("ぱぴぷぺぽ", ("pa", "pi", "pu", "pe", "po"))),
    **dict(zip("まみむめも", ("ma", "mi", "mu", "me", "mo"))),
    **dict(zip("やゆよ", ("ya", "yu", "yo"))),
    **dict(zip("らりるれろ", ("ra", "ri", "ru", "re", "ro"))),
    **dict(zip("わゐゑを", ("wa", "wi", "we", "o"))),
    "ん": "n",
    "ゔ": "vu",
    "ぁ": "a",
    "ぃ": "i",
    "ぅ": "u",
    "ぇ": "e",
    "ぉ": "o",
}

# よう音と外来音は、単独の仮名を順に読むより一般的な英字表記へ寄せる。
_KANA_ROMAJI_PAIRS = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo",
    "てぃ": "ti", "でぃ": "di", "とぅ": "tu", "どぅ": "du",
    "うぃ": "wi", "うぇ": "we", "うぉ": "wo",
    "くぁ": "kwa", "くぃ": "kwi", "くぇ": "kwe", "くぉ": "kwo",
    "ぐぁ": "gwa", "ぐぃ": "gwi", "ぐぇ": "gwe", "ぐぉ": "gwo",
    "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo",
}


def _to_hiragana(character: str) -> str:
    """ひらがなとカタカナを、ローマ字変換用のひらがなへそろえる。"""
    normalized = unicodedata.normalize("NFKC", character)
    return "".join(
        chr(ord(item) - 0x60) if "\u30a1" <= item <= "\u30f6" else item
        for item in normalized
    )


def _kana_to_romaji(text: str) -> str:
    """ひらがな・カタカナを簡易ローマ字へ変換し、読みと英字表記を照合できるようにする。"""
    normalized = unicodedata.normalize("NFKC", text)
    output: list[str] = []
    geminate = False
    index = 0
    while index < len(normalized):
        current = _to_hiragana(normalized[index])
        if current == "っ":
            geminate = True
            index += 1
            continue
        if current == "ー":
            index += 1
            continue
        next_character = _to_hiragana(normalized[index + 1]) if index + 1 < len(normalized) else ""
        pair = current + next_character
        if pair in _KANA_ROMAJI_PAIRS:
            syllable = _KANA_ROMAJI_PAIRS[pair]
            index += 2
        else:
            syllable = _KANA_ROMAJI.get(current, current.lower() if current.isascii() and current.isalnum() else "")
            index += 1
        if geminate and syllable:
            output.append("t" if syllable.startswith("ch") else syllable[0])
            geminate = False
        output.append(syllable)
    return "".join(output)


def _is_kana_character(character: str) -> bool:
    """Unicode正規化後のひらがな・カタカナを判定する。"""
    return (
        "\u3041" <= character <= "\u3096"
        or "\u30a1" <= character <= "\u30fa"
        or character == "ー"
        or "\u31f0" <= character <= "\u31ff"
    )


def _whole_run_scores(
    key: str, runs: Sequence[_TextRun], min_score: float
) -> list[TextMatch]:
    """キー全体と文字種区間全体を比べ、区間の内側だけの一致を除く。"""
    if not key:
        return []
    matches = []
    for run in runs:
        score = 100.0 * Levenshtein.normalized_similarity(key, run.text)
        if score >= min_score:
            matches.append(TextMatch(run.start, run.end, score))
    return matches


def _short_reading_matches_in_runs(
    reading: str,
    kana_runs: Sequence[_TextRun],
    latin_runs: Sequence[_TextRun],
    min_score: float,
    script: TextScript | None = None,
) -> list[TextMatch]:
    """短い読みをカタカナ区間全体またはローマ字区間全体と照合する。"""
    normalized_reading = normalize_kana(reading)
    if not normalized_reading or len(normalized_reading) > SHORT_KEY_LENGTH:
        return []

    matches = []
    if script in (None, "kana"):
        matches.extend(
            TextMatch(run.start, run.end, 100.0)
            for run in kana_runs
            if run.text == normalized_reading
        )
    if script in (None, "latin"):
        romanized_key = normalize_latin(_kana_to_romaji(reading))
        matches.extend(_whole_run_scores(romanized_key, latin_runs, min_score))
    return matches


def _is_katakana_character(character: str) -> bool:
    """ASR出力をローマ字へ変換する対象のカタカナを判定する。"""
    return "\u30a1" <= character <= "\u30fa" or character == "ー" or "\u31f0" <= character <= "\u31ff"


def _romanized_runs(text: str, *, spell_single_letters: bool = True) -> list[str]:
    """英数字と仮名をローマ字へそろえ、必要なら仮名に隣接する一字英字も発音へ変換する。"""
    runs: list[str] = []
    units: list[tuple[TextScript, str]] = []
    kana_buffer: list[str] = []
    latin_buffer: list[str] = []

    def save_kana() -> None:
        if kana_buffer:
            units.append(("kana", _kana_to_romaji("".join(kana_buffer))))
            kana_buffer.clear()

    def save_latin() -> None:
        if latin_buffer:
            units.append(("latin", "".join(latin_buffer)))
            latin_buffer.clear()

    def save_run() -> None:
        save_kana()
        save_latin()
        if not units:
            return
        runs.append("".join(value for _, value in units))
        if spell_single_letters:
            spelled_units = []
            for unit_index, (script, value) in enumerate(units):
                adjacent_to_kana = any(
                    0 <= neighbor < len(units) and units[neighbor][0] == "kana"
                    for neighbor in (unit_index - 1, unit_index + 1)
                )
                if script == "latin" and len(value) == 1 and value.isalpha() and adjacent_to_kana:
                    value = _kana_to_romaji(_ENGLISH_LETTER_READINGS[value.upper()])
                spelled_units.append(value)
            spelled_run = "".join(spelled_units)
            if spelled_run != runs[-1]:
                runs.append(spelled_run)
        units.clear()

    for character in text:
        normalized = unicodedata.normalize("NFKC", character)
        for item in normalized:
            if _is_katakana_character(item):
                save_latin()
                kana_buffer.append(item)
            elif item.isascii() and item.isalnum():
                save_kana()
                latin_buffer.append(item.lower())
            elif "\u3041" <= item <= "\u3096":
                save_kana()
                save_latin()
                save_run()
            elif item.isspace() or unicodedata.category(item)[0] in {"P", "S"}:
                save_kana()
                save_latin()
                continue
            else:
                save_kana()
                save_latin()
                save_run()
    save_run()
    return runs


def _selection_surface_key(text: str) -> str:
    """英字表記を小文字化し、空白・記号を除いた検索キーへそろえる。"""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


@dataclass(frozen=True)
class _SearchKey:
    """索引に登録する表記または読みと、それが属する用語集の位置。"""

    text: str
    entry_index: int
    script: TextScript
    source: Literal["reading", "surface"]
    short_reading: str | None = None


# 別名の端と隣の文字が同じ文字種なら、カタカナ語や英数字の識別子の途中とみなす。
_ALIAS_WORD_CHARACTERS = (r"[ァ-ヺーヽヾㇰ-ㇿｦ-ﾟ\u3099\u309a]", r"[A-Za-z0-9Ａ-Ｚａ-ｚ０-９_]")


def _compile_aliases(entries: Sequence[GlossaryEntry]) -> list[tuple[re.Pattern[str], GlossaryEntry]]:
    """完全一致用のパターンを最長順に作り、行き先が複数ある別名は除く。"""
    targets: dict[str, dict[str, GlossaryEntry]] = {}
    for entry in entries:
        for alias in entry.aliases:
            if alias:
                targets.setdefault(alias, {}).setdefault(entry.surface, entry)
    patterns = []
    for alias in sorted(targets, key=len, reverse=True):
        if len(targets[alias]) != 1:
            continue
        pattern = re.escape(alias)
        for characters in _ALIAS_WORD_CHARACTERS:
            if re.fullmatch(characters, alias[0]):
                pattern = rf"(?<!{characters}){pattern}"
            if re.fullmatch(characters, alias[-1]):
                pattern = rf"{pattern}(?!{characters})"
        # 重なった出現箇所も調べ、先に採った長い別名と重ならない箇所を残す。
        patterns.append((re.compile(rf"(?=({pattern}))"), next(iter(targets[alias].values()))))
    return patterns


class GlossaryIndex:
    """読み・表記の索引を一度作り、発話ごとに候補語だけを採点する。"""

    def __init__(self, entries: Sequence[GlossaryEntry]) -> None:
        self.entries = tuple(entries)
        self._alias_patterns = _compile_aliases(self.entries)
        self.keys: list[_SearchKey] = []
        self._short_keys: dict[str, list[int]] = defaultdict(list)
        self._bigrams: dict[str, list[int]] = defaultdict(list)
        self._trigrams: dict[str, list[int]] = defaultdict(list)
        # 追加読みを別の索引に置き、既存の曖昧照合で使うn-gramの頻度を変えない。
        self._alt_readings: dict[str, list[int]] = defaultdict(list)
        alt_substring_lengths: set[int] = set()

        for entry_index, entry in enumerate(self.entries):
            if entry.alt_readings:
                canonical_readings = {normalize_kana(reading) for reading in entry.readings}
                for reading in {normalize_kana(reading) for reading in entry.alt_readings} - canonical_readings:
                    if len(reading) >= 3:
                        self._alt_readings[reading].append(entry_index)
                    if len(reading) >= ALT_READING_SUBSTRING_MIN_LENGTH:
                        alt_substring_lengths.add(len(reading))
            keys: dict[
                tuple[str, TextScript], tuple[Literal["reading", "surface"], str | None]
            ] = {}
            entry_short_reading = next(
                (
                    reading
                    for reading in entry.readings
                    if 0 < len(normalize_kana(reading)) <= SHORT_KEY_LENGTH
                ),
                None,
            )
            for reading in entry.readings:
                kana_key = normalize_kana(reading)
                short_reading = (
                    reading if 0 < len(kana_key) <= SHORT_KEY_LENGTH else None
                )
                if any(_is_kana_character(character) for character in kana_key):
                    key = (kana_key, "kana")
                    existing = keys.get(key)
                    if existing is None:
                        keys[key] = ("reading", short_reading)
                    elif existing[0] == "surface" or short_reading is not None:
                        keys[key] = ("reading", short_reading or existing[1])
                roman_key = _selection_surface_key(_kana_to_romaji(reading))
                if roman_key:
                    key = (roman_key, "latin")
                    existing = keys.get(key)
                    if existing is None:
                        keys[key] = ("reading", short_reading)
                    elif existing[0] == "surface" or short_reading is not None:
                        keys[key] = ("reading", short_reading or existing[1])
            surface_key = _selection_surface_key(entry.surface)
            if surface_key.isascii() and surface_key:
                keys.setdefault((surface_key, "latin"), ("surface", entry_short_reading))

            for (key_text, script), (source, short_reading) in keys.items():
                key_index = len(self.keys)
                self.keys.append(
                    _SearchKey(key_text, entry_index, script, source, short_reading)
                )
                if len(key_text) <= 2:
                    self._short_keys[key_text].append(key_index)
                else:
                    for gram in {key_text[offset : offset + 3] for offset in range(len(key_text) - 2)}:
                        self._trigrams[gram].append(key_index)
                if 3 <= len(key_text) <= 8:
                    for gram in {key_text[offset : offset + 2] for offset in range(len(key_text) - 1)}:
                        self._bigrams[gram].append(key_index)
        self._alt_substring_lengths = sorted(alt_substring_lengths)

    def replace_aliases(self, text: str) -> tuple[str, list[GlossaryEntry]]:
        """元のASR文で一致した別名を一度だけ置換し、用語選択で優先する語も返す。"""
        if not self._alias_patterns:
            return text, []
        occupied: set[int] = set()
        matches: dict[int, tuple[int, GlossaryEntry]] = {}
        for pattern, entry in self._alias_patterns:
            for match in pattern.finditer(text):
                start, end = match.span(1)
                positions = range(start, end)
                if occupied.isdisjoint(positions):
                    occupied.update(positions)
                    matches[start] = (end, entry)
        if not matches:
            return text, []
        parts = []
        entries: dict[str, GlossaryEntry] = {}
        offset = 0
        for start, (end, entry) in sorted(matches.items()):
            parts.extend((text[offset:start], entry.surface))
            entries.setdefault(entry.surface, entry)
            offset = end
        parts.append(text[offset:])
        return "".join(parts), list(entries.values())

    def _alt_reading_matches(self, kana_runs: Sequence[_TextRun]) -> set[int]:
        """長い追加読みは区間内でも探し、短い追加読みは区間全体で照合する。"""
        matches: set[int] = set()
        for run in kana_runs:
            matches.update(self._alt_readings.get(run.text, ()))
            for length in self._alt_substring_lengths:
                if length >= len(run.text):
                    break
                for offset in range(len(run.text) - length + 1):
                    matches.update(self._alt_readings.get(run.text[offset : offset + length], ()))
        return matches

    def _candidate_key_indexes(
        self,
        kana_runs: Sequence[_TextRun],
        latin_runs: Sequence[_TextRun],
        romanized_runs: Sequence[str],
    ) -> set[int]:
        """発話に含まれる文字n-gramで索引を引き、採点対象のキーを絞る。"""
        candidates: set[int] = set()
        for run in kana_runs:
            if run.text in self._short_keys:
                candidates.update(self._short_keys[run.text])
            self._add_ngram_candidates(run.text, candidates)

        for run in latin_runs:
            if run.text in self._short_keys:
                candidates.update(self._short_keys[run.text])
        for run in romanized_runs:
            if run in self._short_keys:
                candidates.update(self._short_keys[run])
            self._add_ngram_candidates(run, candidates)
        return candidates

    def _add_ngram_candidates(self, run: str, candidates: set[int]) -> None:
        """頻度の低い文字n-gramだけを索引から引き、頻出語による候補膨張を抑える。"""
        for offset in range(len(run) - 1):
            posting = self._bigrams.get(run[offset : offset + 2], ())
            if len(posting) <= SELECTION_MAX_BIGRAM_POSTINGS:
                candidates.update(posting)
        for offset in range(len(run) - 2):
            posting = self._trigrams.get(run[offset : offset + 3], ())
            if len(posting) <= SELECTION_MAX_TRIGRAM_POSTINGS:
                candidates.update(posting)

    @staticmethod
    def _score_key(
        key: _SearchKey,
        kana_runs: Sequence[_TextRun],
        latin_runs: Sequence[_TextRun],
        romanized_runs: Sequence[str],
        min_score: float,
    ) -> float:
        """一致率に用語キー全体の被覆率を掛け、短い一致で長い語が上がらないようにする。"""
        if key.source == "reading" and key.short_reading is not None:
            matches = _short_reading_matches_in_runs(
                key.short_reading,
                kana_runs,
                latin_runs,
                min_score,
                key.script,
            )
            return max((match.score for match in matches), default=0.0)
        if key.source == "surface" and key.short_reading is not None:
            return max(
                (match.score for match in _whole_run_scores(key.text, latin_runs, min_score)),
                default=0.0,
            )
        if len(key.text) <= 2:
            return 100.0
        runs = [run.text for run in kana_runs] if key.script == "kana" else romanized_runs
        best_score = 0.0
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
            best_score = max(best_score, min(alignment.score, coverage_score))
        return best_score

    def select(
        self,
        text: str,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> list[GlossaryEntry]:
        """優先順位と得点順位を交互にたどり、重複を除いた上位候補を返す。"""
        if max_entries <= 0:
            return []
        kana_runs = _text_runs(text, "kana", ignore_long_vowel=True)
        latin_runs = _text_runs(text, "latin")
        romanized_runs = _romanized_runs(text)
        scores: dict[int, float] = {}
        candidate_indexes = self._candidate_key_indexes(kana_runs, latin_runs, romanized_runs)
        for key_index in candidate_indexes:
            key = self.keys[key_index]
            score = self._score_key(key, kana_runs, latin_runs, romanized_runs, min_score)
            if score >= min_score:
                scores[key.entry_index] = max(scores.get(key.entry_index, 0.0), score)
        if self._alt_readings and min_score <= ALT_READING_SCORE:
            for entry_index in self._alt_reading_matches(kana_runs):
                scores[entry_index] = max(scores.get(entry_index, 0.0), ALT_READING_SCORE)

        ranked = sorted(
            scores.items(),
            key=lambda item: (
                not self.entries[item[0]].priority,
                -item[1],
                item[0],
            ),
        )
        score_ranked = sorted(
            scores.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )
        interleaved = _interleave_rankings(
            [entry_index for entry_index, _ in ranked],
            [entry_index for entry_index, _ in score_ranked],
            *PRIORITY_INTERLEAVE_RATIO,
            max_entries,
        )
        return [self.entries[entry_index] for entry_index in interleaved]


def _interleave_rankings(
    priority_ranked: Sequence[int],
    score_ranked: Sequence[int],
    priority_count: int,
    score_count: int,
    max_entries: int,
) -> list[int]:
    """2本の順位を交互に取り、重複を飛ばしながら各側の枠数を満たす。"""
    if priority_count <= 0 or score_count <= 0:
        raise ValueError("順位の交互比率は両側とも1以上にする")
    selected: list[int] = []
    seen: set[int] = set()
    positions = [0, 0]
    rankings = (priority_ranked, score_ranked)
    quotas = (priority_count, score_count)

    while len(selected) < max_entries:
        added_in_round = False
        for rank_index, (ranking, quota) in enumerate(zip(rankings, quotas)):
            if len(selected) >= max_entries:
                break
            added_from_rank = 0
            while positions[rank_index] < len(ranking) and added_from_rank < quota:
                entry_index = ranking[positions[rank_index]]
                positions[rank_index] += 1
                if entry_index in seen:
                    continue
                selected.append(entry_index)
                seen.add(entry_index)
                added_from_rank += 1
                added_in_round = True
                if len(selected) == max_entries:
                    break
        if not added_in_round:
            break
    return selected


# 同じ用語集を繰り返し渡す呼び出しで、構築済み索引を再利用する。
_INDEX_CACHE: OrderedDict[int, tuple[object, tuple[GlossaryEntry, ...], GlossaryIndex]] = OrderedDict()
# 長時間動くプロセスで辞書を多数読み替えた場合の索引キャッシュ上限。
_INDEX_CACHE_LIMIT = 8


def _get_glossary_index(entries: Sequence[GlossaryEntry] | GlossaryIndex) -> GlossaryIndex:
    """同じ読み込み済み辞書を繰り返し使う呼び出しで索引を再利用する。"""
    if isinstance(entries, GlossaryIndex):
        return entries
    snapshot = tuple(entries)
    cache_key = id(entries)
    cached = _INDEX_CACHE.get(cache_key)
    if cached is not None and cached[0] is entries and cached[1] == snapshot:
        _INDEX_CACHE.move_to_end(cache_key)
        return cached[2]
    index = GlossaryIndex(snapshot)
    _INDEX_CACHE[cache_key] = (entries, snapshot, index)
    _INDEX_CACHE.move_to_end(cache_key)
    while len(_INDEX_CACHE) > _INDEX_CACHE_LIMIT:
        _INDEX_CACHE.popitem(last=False)
    return index


def _find_matches_in_runs(
    key: str,
    runs: list[_TextRun],
    script: TextScript,
    min_score: float,
    short_key_requires_whole_run: bool,
    ignore_long_vowel: bool = False,
    allow_shorter_run: bool = False,
    exact_only: bool = False,
) -> list[TextMatch]:
    """共有の文字種区間で、完全一致または指定された類似度以上の部分一致を探す。"""
    normalized_key = normalize_kana(key, ignore_long_vowel) if script == "kana" else normalize_latin(key)
    if not normalized_key:
        return []
    if exact_only:
        return [TextMatch(run.start, run.end, 100.0) for run in runs if run.text == normalized_key]
    matches: list[TextMatch] = []
    if len(normalized_key) <= SHORT_KEY_LENGTH:
        for run in runs:
            if short_key_requires_whole_run:
                if run.text == normalized_key:
                    matches.append(TextMatch(run.start, run.end, 100.0))
                continue
            offset = 0
            while (start := run.text.find(normalized_key, offset)) >= 0:
                end = start + len(normalized_key)
                matches.append(
                    TextMatch(run.source_starts[start], run.source_ends[end - 1], 100.0)
                )
                offset = end
        return matches

    for run in runs:
        if len(run.text) < len(normalized_key) and not allow_shorter_run:
            continue
        offset = 0
        while offset < len(run.text):
            if offset + len(normalized_key) > len(run.text) and not allow_shorter_run:
                break
            alignment = fuzz.partial_ratio_alignment(
                normalized_key,
                run.text[offset:],
                score_cutoff=min_score,
            )
            if alignment is None:
                break
            start = offset + alignment.dest_start
            end = offset + alignment.dest_end
            if end <= start:
                break
            missing = len(normalized_key) - (end - start)
            if missing > 0:
                expand_left = min(start - offset, missing)
                start -= expand_left
                missing -= expand_left
                end += min(len(run.text) - end, missing)
            matches.append(
                TextMatch(run.source_starts[start], run.source_ends[end - 1], alignment.score)
            )
            if allow_shorter_run:
                break
            offset = max(end, start + 1)
    return matches


def find_term_matches(
    key: str,
    text: str,
    min_score: float = DEFAULT_MIN_SCORE,
    script: TextScript = "kana",
    short_key_requires_whole_run: bool = True,
    ignore_long_vowel: bool = False,
    exact_only: bool = False,
) -> list[TextMatch]:
    """元の文の指定文字種区間で用語を探し、置換可能な元位置を返す。

    `exact_only`では長音を保ち、正規化後の区間全体が読みと一致した場合だけ返す。
    """
    if exact_only:
        ignore_long_vowel = False
    return _find_matches_in_runs(
        key,
        _text_runs(text, script, ignore_long_vowel),
        script,
        min_score,
        short_key_requires_whole_run,
        ignore_long_vowel,
        exact_only=exact_only,
    )


def find_short_reading_matches(
    reading: str, text: str, min_score: float = 0.0
) -> list[TextMatch]:
    """短い読みを、境界がそろったカタカナまたは英数字の区間で探す。"""
    return _short_reading_matches_in_runs(
        reading,
        _text_runs(text, "kana", ignore_long_vowel=True),
        _text_runs(text, "latin"),
        min_score,
    )


def score_entry(
    entry: GlossaryEntry,
    text: str,
    kana_runs: list[_TextRun],
    latin_runs: list[_TextRun],
) -> float:
    """読みはカタカナ区間、英字の表記は英数字区間で照合して最高点を返す。"""
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


def score_entry_in_text(entry: GlossaryEntry, text: str) -> float:
    """用語集選択と同じ正規化・類似度で、1語と全文の一致点を返す。"""
    return score_entry(
        entry,
        text,
        _text_runs(text, "kana", ignore_long_vowel=True),
        _text_runs(text, "latin"),
    )


def score_entry_readings(entry: GlossaryEntry, text: str) -> float:
    """surface一致を除き、用語の読みだけでASR出力との類似度を返す。"""
    kana_runs = _text_runs(text, "kana", ignore_long_vowel=True)
    return max(
        (
            match.score
            for reading in entry.readings
            for match in _find_matches_in_runs(
                reading, kana_runs, "kana", 0.0, True, True, True
            )
        ),
        default=0.0,
    )


def select_glossary(
    text: str,
    entries: Sequence[GlossaryEntry] | GlossaryIndex,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    min_score: float = DEFAULT_MIN_SCORE,
    *,
    selection_index: GlossaryIndex | None = None,
) -> list[GlossaryEntry]:
    """ASR出力に近い語を索引から探し、2本の順位を交互に最大`max_entries`件返す。"""
    index = selection_index or _get_glossary_index(entries)
    return index.select(text, max_entries, min_score)


def _is_ascii_word_character(character: str) -> bool:
    """英字用語の単語境界で語中とみなすASCII英数字と下線を判定する。"""
    return character == "_" or (character.isascii() and character.isalnum())


def select_screen_glossary(screen_text: str, entries: list[GlossaryEntry]) -> list[GlossaryEntry]:
    """画面文字列にsurfaceが現れる用語集項目を、用語集の順で返す。"""
    # 未登録語は読みが無く、ASRへ渡せない。
    # 読みを得る手段を用意した段階で、対象を広げる。
    normalized_screen = screen_text.casefold()
    selected: list[GlossaryEntry] = []
    for entry in entries:
        surface = entry.surface.casefold()
        if not surface:
            continue
        has_english = any(
            character.isascii() and character.isalpha() for character in entry.surface
        )
        offset = 0
        while (start := normalized_screen.find(surface, offset)) >= 0:
            end = start + len(surface)
            # ASCII英数字と下線で英字の語中を防ぎ、日本語の助詞は境界として扱う。
            if not has_english or (
                (start == 0 or not _is_ascii_word_character(normalized_screen[start - 1]))
                and (end == len(normalized_screen) or not _is_ascii_word_character(normalized_screen[end]))
            ):
                selected.append(entry)
                break
            offset = start + 1
    return selected


def select_glossary_with_priority(
    text: str,
    entries: Sequence[GlossaryEntry] | GlossaryIndex,
    priority_entries: Sequence[GlossaryEntry] | GlossaryIndex,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    min_score: float = DEFAULT_MIN_SCORE,
    *,
    selection_index: GlossaryIndex | None = None,
    priority_index: GlossaryIndex | None = None,
    alias_entries: Sequence[GlossaryEntry] = (),
) -> list[GlossaryEntry]:
    """別名が一致した語、画面の優先語、通常の候補の順に上限まで返す。"""
    if max_entries <= 0:
        return []
    priority = select_glossary(
        text,
        priority_entries,
        max_entries,
        min_score,
        selection_index=priority_index,
    )
    selected = select_glossary(
        text,
        entries,
        max_entries,
        min_score,
        selection_index=selection_index,
    )
    result: list[GlossaryEntry] = []
    seen: set[str] = set()
    for entry in (*alias_entries, *priority, *selected):
        if entry.surface in seen:
            continue
        seen.add(entry.surface)
        result.append(entry)
        if len(result) == max_entries:
            break
    return result


def measure_selection(
    rows: list[dict],
    entries: list[GlossaryEntry],
    input_field: str,
    max_entries: int,
    min_score: float,
) -> dict:
    """各行の正解の用語（`glossary`の表記）が絞り込みで選ばれた割合と、選ばれた件数・時間を測る。

    用語集全体に無い正解の用語は、絞り込みでは拾えないため分母から外し、件数を別に数える。
    """
    known = {e.surface for e in entries}
    hit = total = missing_from_glossary = 0
    counts, elapsed_ms, misses = [], [], []
    selection_index = GlossaryIndex(entries)
    for row in rows:
        start = time.perf_counter()
        selected = select_glossary(
            row[input_field],
            entries,
            max_entries,
            min_score,
            selection_index=selection_index,
        )
        elapsed_ms.append((time.perf_counter() - start) * 1000)
        counts.append(len(selected))
        chosen = {e.surface for e in selected}
        for g in row.get("glossary", []):
            if g["surface"] not in known:
                missing_from_glossary += 1
                continue
            total += 1
            if g["surface"] in chosen:
                hit += 1
            else:
                misses.append({"id": row["id"], "surface": g["surface"], "text": row[input_field]})
    return {
        "n_rows": len(rows),
        "glossary_size": len(entries),
        "max_entries": max_entries,
        "min_score": min_score,
        "gold_terms": total,
        "recall": hit / total if total else None,
        "miss_rate": 1 - hit / total if total else None,
        "gold_terms_not_in_glossary": missing_from_glossary,
        "mean_selected": statistics.mean(counts) if counts else 0,
        "median_ms": statistics.median(elapsed_ms) if elapsed_ms else 0,
        "misses": misses,
    }


def _read_jsonl(path: str | Path) -> list[dict]:
    """1行1件のJSONLを読み込む。"""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    """絞り込みの取りこぼしの割合をmanifestで測り、JSONで標準出力へ書く。"""
    parser = argparse.ArgumentParser(description="用語集の絞り込みの取りこぼしの割合を測る")
    parser.add_argument("--manifest", required=True, help="`glossary`と入力の欄を持つJSONL")
    parser.add_argument(
        "--glossary", nargs="+", help="用語集全体（複数可）。省略時はmanifestの全行の`glossary`の和集合"
    )
    parser.add_argument("--input-field", default="spoken_text")
    parser.add_argument("--asr-run", help="ASRの推論結果（`hyp`を入力に使う）")
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    args = parser.parse_args()

    rows = _read_jsonl(args.manifest)
    entries = load_glossary(*args.glossary) if args.glossary else glossary_from_rows(rows)
    input_field = args.input_field
    if args.asr_run:
        hyp_by_id = {r["id"]: r["hyp"] for r in _read_jsonl(args.asr_run)}
        rows = [dict(r, asr_hyp=hyp_by_id[r["id"]]) for r in rows if r["id"] in hyp_by_id]
        input_field = "asr_hyp"
    result = measure_selection(rows, entries, input_field, args.max_entries, args.min_score)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
