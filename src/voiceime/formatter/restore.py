"""整形の出力に残った用語の読みを、渡した用語一覧の表記へ戻す。

整形LLMは、学習で見たことのない用語を一覧から写さず、カタカナの読みのまま出すことがある
（`docs/experiments/2026-11-23-restore-readings.md`）。一覧にある語に限って読みを表記へ戻し、取りこぼしを減らす。
"""

from __future__ import annotations

from collections.abc import Sequence

from voiceime.formatter.glossary import GlossaryEntry

# 戻す対象にする読みの最小の文字数。短い読み（「バッチ」「データ」など）は普通の語として
# 文に現れるため対象外にする。valで5文字以下を含めるとCERが悪化し、6文字以上では悪化しなかった。
MIN_RESTORE_READING_LENGTH = 6


def restore_listed_readings(text: str, entries: Sequence[GlossaryEntry]) -> str:
    """一覧の語のうち、表記が文に無く読みが文にあるものを、表記へ置き換えた文を返す。"""
    replacements: list[tuple[str, str]] = []
    for entry in entries:
        if entry.surface in text:
            continue
        for reading in entry.readings:
            if len(reading) >= MIN_RESTORE_READING_LENGTH and reading in text:
                replacements.append((reading, entry.surface))
    # 長い読みから置き換え、短い読みが長い読みの一部を先に書き換えないようにする。
    for reading, surface in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(reading, surface)
    return text
