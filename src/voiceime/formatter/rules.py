"""LLMを使わない比較用の系：フィラーを除き、読みと完全一致するカタカナ区間だけを用語表記へ置き換える。

LLMの系と出力を比べ、言い直しや句読点、文の整形のようにLLMが本当に必要な誤りを切り分けるために使う。
フィラーの一覧は整形の系の部品であり、評価のフィラーの一覧（`src/voiceime/eval/`）とは別に持つ。
評価の一覧を系に使うと、系を評価の定義へ合わせ込むことになるため。
"""

from __future__ import annotations

import re
from typing import Sequence

from voiceime.formatter.glossary import GlossaryEntry, find_term_matches, normalize_kana

# 出現位置によらずフィラーとみなす語。長いものから順に照合するよう並べる。
STRONG_FILLERS = ("えーっと", "えーと", "ええと", "えっと", "えー", "あのー", "そのー", "うーん", "んー", "あー", "まあ")
# 指示語や連体詞と区別できないため、直後に読点があるときだけフィラーとみなす語。
WEAK_FILLERS = ("あの", "その", "なんか", "ええ", "ま")

# フィラーと直後の読点を取り除く正規表現。
FILLER_PATTERN = re.compile(
    "(?:" + "|".join(STRONG_FILLERS) + ")[、,]?\\s*|(?:" + "|".join(WEAK_FILLERS) + ")[、,]\\s*"
)
# 文末とみなす記号。無ければ句点を足す。
SENTENCE_END = ("。", "？", "?", "！", "!")
def remove_fillers(text: str) -> str:
    """フィラーを取り除く。"""
    return FILLER_PATTERN.sub("", text)


def replace_terms(text: str, glossary: Sequence[GlossaryEntry]) -> str:
    """カタカナ区間全体が用語読みと一致する箇所だけを表記へ置き換える。"""
    pairs = sorted(
        ((reading, entry.surface) for entry in glossary for reading in entry.readings),
        key=lambda pair: -len(normalize_kana(pair[0])),
    )
    for reading, surface in pairs:
        matches = find_term_matches(
            reading,
            text,
            script="kana",
            exact_only=True,
        )
        # 元の文字位置を壊さないよう、後ろの一致から順に置換する。
        for match in reversed(matches):
            text = text[: match.start] + surface + text[match.end :]
    return text


def format_with_rules(asr_text: str, glossary: Sequence[GlossaryEntry]) -> str:
    """フィラー除去、用語の置換、文末の句点の付与を順に行う。"""
    text = replace_terms(remove_fillers(asr_text).strip(), glossary)
    if text and not text.endswith(SENTENCE_END):
        text += "。"
    return text
