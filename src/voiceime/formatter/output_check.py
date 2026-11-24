"""整形モデルの出力が貼り付けに適した形かを判定する。"""

from __future__ import annotations

import re
import unicodedata

# 「ー」以外の同じ文字が5文字、2文字以上の並びが4回で崩れとみなす。
# 数十回の生成ループを早く止め、1〜3回の短い反復は許す。
LONG_VOWEL_MARK = "ー"
MIN_REPEATED_CHARACTER_COUNT = 5
MIN_REPEATED_SEQUENCE_LENGTH = 2
MIN_REPEATED_SEQUENCE_COUNT = 4

# 既存の長さ許容幅を名前付きにし、空白を除いた句読点込みの文字数で判定する。
MIN_OUTPUT_LENGTH_RATIO = 0.15
MAX_OUTPUT_LENGTH_RATIO = 1.8
MAX_OUTPUT_LENGTH_ALLOWANCE = 32

# 整形文の前に説明ラベルが付いた失敗を検出する。
_PREFACE_PATTERN = re.compile(
    r"^(?:整形結果|整形後(?:の文)?|回答|出力|結果)\s*[:：]"
    r"|^(?:here(?:'s| is)\s+)?(?:the\s+)?(?:formatted\s+(?:text|result)|result)\s*:",
    re.IGNORECASE,
)
_REPEATED_CHARACTER_PATTERN = re.compile(
    rf"(.)\1{{{MIN_REPEATED_CHARACTER_COUNT - 1},}}",
    re.DOTALL,
)
_REPEATED_SEQUENCE_PATTERN = re.compile(
    rf"(.{{{MIN_REPEATED_SEQUENCE_LENGTH},}}?)(?:\1){{{MIN_REPEATED_SEQUENCE_COUNT - 1},}}",
    re.DOTALL,
)


def _normalized_length(text: str) -> int:
    """全角・互換文字をNFKCで揃え、句読点を含む非空白文字数を返す。"""
    normalized = unicodedata.normalize("NFKC", text)
    return sum(not character.isspace() for character in normalized)


def _repetition_signatures(text: str) -> set[tuple[str, str]]:
    """文中の長い同一文字と、4回以上続く2文字以上の並びを特定する。"""
    normalized = unicodedata.normalize("NFKC", text)
    signatures = {
        ("character", match.group(1))
        for match in _REPEATED_CHARACTER_PATTERN.finditer(normalized)
        if match.group(1) != LONG_VOWEL_MARK
    }
    for match in _REPEATED_SEQUENCE_PATTERN.finditer(normalized):
        sequence = match.group(1)
        # 同一文字だけの列は上の検査で扱い、「ー」は同一文字の条件から除く。
        if len(set(sequence)) == 1 and sequence[0] != LONG_VOWEL_MARK:
            continue
        signatures.add(("sequence", sequence))
    return signatures


def _repetition_signatures_after(text: str, start: int) -> set[tuple[str, str]]:
    """NFKC済み文字列の指定位置以降で新たに完成した繰り返しを特定する。"""
    signatures: set[tuple[str, str]] = set()
    char_window_start = max(0, start - MIN_REPEATED_CHARACTER_COUNT + 1)
    for match in _REPEATED_CHARACTER_PATTERN.finditer(text[char_window_start:]):
        match_end = char_window_start + match.end()
        if match_end > start and match.group(1) != LONG_VOWEL_MARK:
            signatures.add(("character", match.group(1)))

    for end in range(start + 1, len(text) + 1):
        for length in range(MIN_REPEATED_SEQUENCE_LENGTH, end // MIN_REPEATED_SEQUENCE_COUNT + 1):
            sequence = text[end - length : end]
            repeated_start = end - length * MIN_REPEATED_SEQUENCE_COUNT
            if text[repeated_start:end] != sequence * MIN_REPEATED_SEQUENCE_COUNT:
                continue
            if len(set(sequence)) > 1 or sequence[0] == LONG_VOWEL_MARK:
                signatures.add(("sequence", sequence))
            break
    return signatures


class RepetitionChecker:
    """ASR文に既にある反復を許し、整形出力に新しく現れた反復を判定する。"""

    def __init__(self, raw_text: str):
        """ASR側の繰り返しを一度調べ、生成中に再利用する。"""
        self._raw_signatures = _repetition_signatures(raw_text)

    def has_new_repetition(self, formatted_text: str) -> bool:
        """整形文全体に新しい反復があるか確認する。"""
        return bool(_repetition_signatures(formatted_text) - self._raw_signatures)

    def has_new_repetition_since(self, previous_text: str, formatted_text: str) -> bool:
        """生成chunk追加後の末尾だけを調べ、同じ判定を早く返す。"""
        normalized = unicodedata.normalize("NFKC", formatted_text)
        previous_length = len(unicodedata.normalize("NFKC", previous_text))
        # NFKCの境界変化を含めるため、直前の1文字から再確認する。
        signatures = _repetition_signatures_after(normalized, max(0, previous_length - 1))
        return bool(signatures - self._raw_signatures)


def is_valid_output(raw_text: str, formatted_text: str) -> bool:
    """整形後の繰り返し・長さ・前置き・コードフェンスを確認する。

    検査を通った文だけを貼り付け候補として扱う。
    """
    candidate = formatted_text.lstrip()
    if candidate.startswith(("```", "~~~")) or _PREFACE_PATTERN.match(candidate):
        return False
    if RepetitionChecker(raw_text).has_new_repetition(formatted_text):
        return False

    raw_length = _normalized_length(raw_text)
    formatted_length = _normalized_length(formatted_text)
    return not (
        formatted_length < raw_length * MIN_OUTPUT_LENGTH_RATIO
        or formatted_length > raw_length * MAX_OUTPUT_LENGTH_RATIO + MAX_OUTPUT_LENGTH_ALLOWANCE
    )
