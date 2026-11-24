"""用語集と文章データの生成で共通に使う定数、パス、文字列処理をまとめる。

教師LLMの出力を検査する規則（英字の判定、用語の出現判定など）を一か所に置き、
用語集の作成、文章の作成、検査の各段階で同じ判定を使うために置く。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Iterator

# 大きな成果物は作業ツリーの外（本体のdata/）へ置く決まりのため、絶対パスで持つ。
DATA_DIR = Path("/Users/marutyan/PrivateDev/voiceIME/data/text")

# データ生成の乱数seed。docs/PLAN.mdの決まり（データ生成は0）に合わせる。
SEED = 0

# 用語集の分野。課題で指定された4分野に対応する。
CATEGORIES = ("ml-research", "programming", "cloud-infra", "it-products")

# 用語集から除く、日本語の文では普通カタカナで書く一般の英単語（予約語と一般的な関数名）。
# 教師LLMはコードの識別子として用語集に入れたが、「セット」「リスト」「クラス」のように書くのが普通なので、
# 用語集の組み立てで除き、文章の検査では印を外してカタカナのまま残す。コマンド名（grep、awk、pip など）や、
# argmax、state_dict のような一般の英単語でない識別子は除かない。
KATAKANA_USUAL_WORDS = frozenset(
    """
    set list class filter max min mean scale chunk offset break continue print return import get if for else from
    append extend sort split slice tuple null test train view try except finally while yield constructor
    reduce reshape flatten gather scatter pop squeeze transpose permute norm async await def
    """.split()
)

LATIN_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]")
# 読みとして認める文字。カタカナと長音記号だけにする（スペースや中黒は前処理で除く）。
KATAKANA_READING_RE = re.compile(r"^[ァ-ヺー]+$")
KATAKANA_CHAR = r"ァ-ヺー"


def read_jsonl(path: Path) -> Iterator[dict]:
    """JSONLを1行ずつ辞書として読む。"""
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    """辞書の列をJSONLへ書き、書いた行数を返す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def has_latin(text: str) -> bool:
    """英字（全角を含む）が含まれるかを返す。"""
    return LATIN_RE.search(text) is not None


def surface_pattern(surface: str) -> re.Pattern[str]:
    """英字表記の用語が、前後を英数字に挟まれずに現れる箇所を探す正規表現を作る。

    「BERT」が「RoBERTa」の一部として一致しないようにするため、前後に英数字が無いことを条件にする。
    大文字小文字は区別する（docs/PLAN.mdの用語の正答率が表記の完全一致で測るため）。
    """
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(surface) + r"(?![A-Za-z0-9])")


def reading_pattern(reading: str) -> re.Pattern[str]:
    """カタカナの読みが、前後をカタカナに挟まれずに現れる箇所を探す正規表現を作る。

    「ラスト」が「イラスト」の一部として一致しないようにするため、前後にカタカナが無いことを条件にする。
    """
    return re.compile(rf"(?<![{KATAKANA_CHAR}])" + re.escape(reading) + rf"(?![{KATAKANA_CHAR}])")


def extract_json(text: str) -> object:
    """LLMの出力から最初のJSON（配列またはオブジェクト）を取り出して返す。

    Gemma 4は思考を無効にしても空の思考ブロックやコードブロックの記号を付けることがあるため、
    最初の「[」または「{」から対応する終わりまでを取り出して読む。
    """
    text = re.sub(r"```(?:json)?", "", text)
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    if not starts:
        raise ValueError("JSONが見つからない")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[min(starts):])
    return obj


def parse_items(text: str) -> list[dict]:
    """LLMの出力から、JSONのオブジェクトを読めるものだけ順に取り出して返す。

    出力が長さの上限で途中で切れた場合や、一部のオブジェクトだけが壊れている場合でも、
    完全に読めるオブジェクトは使うため、配列全体ではなくオブジェクト単位で読む。
    文字列の中の改行などの制御文字は許す（strict=False）。
    """
    decoder = json.JSONDecoder(strict=False)
    items: list[dict] = []
    pos = text.find("{")
    while pos >= 0:
        try:
            obj, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.find("{", pos + 1)
            continue
        if isinstance(obj, dict):
            items.append(obj)
        pos = text.find("{", end)
    return items
