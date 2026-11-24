"""評価用の文を参照せず、用語集だけから教師モデルへの要求を作る。"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

# 1要求にまとめる用語数。短い応答で全用語を走査するために使う。
BATCH_SIZE = 24
# 一般的な読みの候補を1件だけ求め、表記順や別の用語との混同を防ぐ。
PROMPT = """英語・ローマ字を含む技術用語の、日本語話者が実際に使いそうな別の発音を調べています。
各行は「番号 / 用語の表記 / 既知の読み」です。表記全体を同じ順で読み、省略・翻訳・別の製品名は禁止です。
別の自然な発音（英語読み、ローマ字読み、連結した読み、文字名と単語読みの切替）があると判断できる場合のみ、1語につき最有力の1候補を出してください。
単なる長音・促音・濁点の揺れや、全字を機械的にアルファベット名で読む形は別処理で扱います。
出力は「番号:カタカナ」だけを1行ずつ。説明、箇条書き、コード柵は不要。既知の読みしかなければその番号を飛ばし、候補が皆無なら「なし」とだけ書いてください。

"""


def request_terms(paths: list[Path]) -> list[tuple[str, list[str]]]:
    """表記単位で既知読みをまとめ、英字を含む用語を辞書順で返す。"""
    terms: dict[str, dict[str, None]] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            surface = record["surface"]
            if not re.search(r"[A-Za-z]", unicodedata.normalize("NFKC", surface)):
                continue
            readings = record.get("readings") or record.get("reading") or []
            if isinstance(readings, str):
                readings = [readings]
            terms.setdefault(surface, {}).update(dict.fromkeys(readings))
    return [(surface, list(terms[surface])) for surface in sorted(terms)]


def main() -> None:
    """用語集の順序と生成条件を固定したJSONLを作る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glossary", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    terms = request_terms(args.glossary)
    with args.output.open("x", encoding="utf-8") as output:
        for offset in range(0, len(terms), BATCH_SIZE):
            batch = terms[offset : offset + BATCH_SIZE]
            lines = [
                f"{number} / {surface} / {'、'.join(readings)}"
                for number, (surface, readings) in enumerate(batch, 1)
            ]
            request = {
                "id": str(offset // BATCH_SIZE),
                "surfaces": [surface for surface, _ in batch],
                "messages": [{"role": "user", "content": PROMPT + "\n".join(lines)}],
                "temperature": 0.0,
                "top_p": 1.0,
                "max_tokens": 640,
                "seed": 0,
            }
            output.write(json.dumps(request, ensure_ascii=False) + "\n")
    print(f"teacher terms={len(terms)}", flush=True)


if __name__ == "__main__":
    main()
