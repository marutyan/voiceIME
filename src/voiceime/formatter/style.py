"""整形後の文の表記を、本人が決めた書き方へそろえる。

整形LLMの出力と学習の正解の両方へ同じ規則を当て、表記の揺れを一か所で決めるために使う。
"""

from __future__ import annotations

import re

# 数字の直後の「パーセント」を記号「%」で書く（2026-11-22 本人の希望）。
# 「何パーセント」のように数字が前に無い場合は、話し言葉の意図が分からないので変えない。
_PERCENT_AFTER_NUMBER = re.compile(r"([0-9０-９])\s*パーセント")


def apply_output_style(text: str) -> str:
    """整形後の文へ表記の規則を当てた文を返す。"""
    return _PERCENT_AFTER_NUMBER.sub(r"\1%", text)
