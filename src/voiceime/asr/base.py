"""ASRの方式に共通する入出力の型と、音声の読み込み、用語集からのプロンプト作成。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

# すべての方式が受け取る音声の標本化周波数（Hz）。`docs/PLAN.md`のデータ形式に合わせる。
SAMPLE_RATE = 16000


@dataclass
class Transcription:
    """1発話の認識結果。`details`には方式ごとの内訳（時間は秒、生成したtoken数など）を入れ、全体の遅延は呼び出し側が測る。"""

    text: str
    details: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Term:
    """用語集の1語。`surface`は正しい表記、`reading`はカタカナの読み（manifestの最初の読み）。"""

    surface: str
    reading: str


class Transcriber(Protocol):
    """音声（16kHzモノラルのfloat32配列）を文字にする方式の共通の形。

    `glossary`には用語の一覧を渡す。用語のヒントを使えない方式は無視する。
    モデルの読み込みは生成時に済ませ、`transcribe`の時間に含めない。
    """

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription: ...


def terms_from_manifest(entries: list[dict]) -> list[Term]:
    """manifestの`glossary`を`Term`の一覧にする。計画の形式の`readings`（配列）と、古い`reading`（文字列）の両方を読む。"""
    terms = []
    for entry in entries:
        readings = entry.get("readings") or [entry["reading"]]
        terms.append(Term(surface=entry["surface"], reading=readings[0]))
    return terms


def load_audio(path: Path) -> np.ndarray:
    """WAVを読み、float32のモノラル配列（値の範囲は-1〜1）で返す。16kHz以外は誤りとして止める。"""
    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"{path}の標本化周波数が{sample_rate}Hzで、{SAMPLE_RATE}Hzではない")
    if audio.ndim != 1:
        raise ValueError(f"{path}がモノラルではない（shape={audio.shape}）")
    return audio


def glossary_prompt(glossary: list[Term] | None) -> str | None:
    """用語の表記を読点でつないだ文字列を、Whisperの`initial_prompt`として返す。用語が無ければNone。

    Whisperは直前の文脈として与えた文字列の表記に寄せて書き起こすため、用語の英字表記を出やすくする目的で使う。
    """
    if not glossary:
        return None
    return "、".join(term.surface for term in glossary)
