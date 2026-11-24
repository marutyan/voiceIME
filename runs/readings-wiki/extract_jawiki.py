"""日本語版WikipediaのXMLから読みと照合に必要な記事情報を抽出する。"""

from __future__ import annotations

import argparse
import bz2
import gzip
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

# 記事名と太字に現れる表記、仮名候補、カテゴリ名の範囲。
LATIN = re.compile(r"(?=.*[A-Za-z])[.A-Za-z0-9][A-Za-z0-9 &+.#_/@'!:\-]{0,75}")
KANA = re.compile(r"[ァ-ヺぁ-ゖｦ-ﾟー][ァ-ヺぁ-ゖｦ-ﾟー・･ 　]{0,78}")
DISAMBIG_SUFFIX = re.compile(r"\s+\([^()]+\)$")
CATEGORY = re.compile(r"\[\[(?:カテゴリ|Category)\s*:\s*([^|\]\n]+)", re.I)
# 読みの前後に現れるウィキテキストのうち、本文の対応を変えずに落とせる構文。
COMMENT = re.compile(r"<!--.*?-->", re.S)
REF = re.compile(r"<ref\b[^>]*(?:/>|>.*?</ref\s*>)", re.I | re.S)
FILE = re.compile(r"\[\[(?:File|Image|ファイル|画像):[^\n]*", re.I)
MARKUP = re.compile(r"</?(?:small|span|sup|sub|b|strong)\b[^>]*>|<br\b[^>]*>", re.I)
LINK = re.compile(r"\[\[([^\[\]\n]*?)\]\]")
BOLD = re.compile(r"'''([^\n]{1,150}?)'''")
START_SECTION = re.compile(r"^ *==", re.M)
LANG_TEMPLATE = re.compile(
    r"\{\{(?:lang\s*\|\s*en|lang-en(?:-short)?|en)\s*\|\s*([^{}|]+?)\s*\}\}", re.I
)
RUBY_TEMPLATE = re.compile(
    r"\{\{(?:読み仮名|よみがな|ruby)\s*\|\s*([^{}|]+?)\s*\|\s*([^{}|]+?)\s*\}\}", re.I
)
# 仮名を別の訳語と取り違えにくいよう、直後の括弧の冒頭か「読み」「発音」の明記を求める。
READING_MARKER = r"(?:日本語(?:での)?の?読み(?:方)?|読み(?:方)?|発音)"
LEADING_READING = re.compile(
    r"^\s*(?:" + READING_MARKER + r"\s*[:：]?\s*)?"
    r"[「『\"]?(?P<kana>" + KANA.pattern + r")[」』\"]?"
    r"(?=\s*(?:[、,，;；/／]|と読|と発音|とも読|とも発音|$))"
)
MARKED_READING = re.compile(
    r"(?:^|[、,，;；／])\s*" + READING_MARKER + r"\s*[:：]\s*"
    r"[「『\"]?(?P<kana>" + KANA.pattern + r")[」』\"]?(?=\s*(?:[、,，;；/／]|$))"
)
LATIN_IN_PAREN = re.compile(
    r"(?:^|[、,，;；／])\s*(?:(?:英語?|英字表記|略称|略記|通称|別表記|ローマ字表記)\s*[:：]?\s*)?"
    r"[「『\"]?(?P<form>[.A-Za-z0-9][A-Za-z0-9 &+.#_/@'!:\-]{0,75}?)"
    r"[」』\"]?(?=\s*(?:[、,，;；/／]|$))"
)
# 括弧内で表記が略記・別表記として明示された場合だけ、主表記の読みを結び付ける。
EXPLICIT_ALIAS = re.compile(
    r"(?:[、,，;；／]\s*)(?:"
    r"(?:略称|略記|別表記|通称)\s*[:：]\s*[「『\"]?(?P<after>[.A-Za-z0-9][A-Za-z0-9.+#_-]{0,23})"
    r"|[「『\"]?(?P<before>[.A-Za-z0-9][A-Za-z0-9.+#_-]{0,23})[」』\"]?\s*と(?:略記|略称|も表記))"
)


def latin_form(value: str) -> str | None:
    """英字を少なくとも1字含む表記を返す。"""
    text = unicodedata.normalize("NFKC", value).strip()
    return text if LATIN.fullmatch(text) else None


def title_form(title: str) -> str:
    """記事名から曖昧さ回避用の括弧を落とす。"""
    return DISAMBIG_SUFFIX.sub("", unicodedata.normalize("NFKC", title))


def category_names(text: str) -> list[str]:
    """記事とカテゴリページの直上カテゴリを取得する。"""
    return sorted({item.strip().replace("_", " ") for item in CATEGORY.findall(text)})


def strip_blocks(text: str) -> str:
    """冒頭の入れ子になったテンプレートと表を取り除く。"""
    pieces = []
    position = 0
    stack = []
    for token in re.finditer(r"\{\{|\}\}|\{\||\|\}", text):
        value = token[0]
        if value in ("{{", "{|"):
            if not stack:
                pieces.append(text[position : token.start()])
                start = token.start()
            stack.append("}}" if value == "{{" else "|}")
        elif stack and value == stack[-1]:
            stack.pop()
            if not stack:
                pieces.append("\n" if "\n" in text[start : token.end()] else " ")
                position = token.end()
    if not stack:
        pieces.append(text[position:])
    return "".join(pieces)


def lead_text(text: str) -> str:
    """記事冒頭から出典や画像を落とし、太字と表示文字列を残す。"""
    text = text[:20000]
    if section := START_SECTION.search(text):
        text = text[: section.start()]
    text = FILE.sub("", REF.sub("", COMMENT.sub("", text)))
    text = LANG_TEMPLATE.sub(r"\1", text)
    text = RUBY_TEMPLATE.sub(
        lambda match: f"'''{match[1]}'''（読み：{match[2]}）", text
    )
    text = strip_blocks(text)
    text = LINK.sub(lambda match: match[1].rsplit("|", 1)[-1], text)
    return MARKUP.sub("", text).lstrip()[:1800]


def paren_after(text: str) -> tuple[str, str] | None:
    """語に隣接する最初の括弧を取り出す。"""
    text = text.lstrip(" \t　'」』")
    if not text or text[0] not in "（(":
        return None
    depth = 0
    for index, character in enumerate(text[:320]):
        if character in "（(":
            depth += 1
        elif character in "）)":
            depth -= 1
            if depth == 0:
                return text[1:index].replace("'''", "").replace("''", ""), text[
                    index + 1 :
                ]
        elif character == "\n":
            return None
    return None


def paren_readings(paren: str) -> Iterator[tuple[str, str]]:
    """冒頭に連続する仮名と、明示された読みを取り、英語の原綴りや語釈は飛ばす。"""
    for reading in MARKED_READING.finditer(paren):
        yield reading["kana"].strip(), "読みと明記"
    for index, part in enumerate(re.split(r"[、,，;；/／]", paren, maxsplit=8)):
        part = re.sub(r"^\s*(?:または|あるいは|もしくは)\s*", "", part)
        reading = LEADING_READING.match(part)
        if not reading or index >= 4:
            break
        yield reading["kana"].strip(), "英字の直後"


def mentions(title: str, text: str) -> Iterator[tuple[str, str, str]]:
    """記事の最初の文で表記と仮名が対応する箇所を返す。"""
    # 括弧のないページは本文を走査せずに飛ばす。
    prefix = text[:20000]
    if "(" not in prefix and "（" not in prefix and "読み" not in prefix:
        return
    page_form = title_form(title)
    intro = lead_text(prefix).split("\n\n", 1)[0].split("。", 1)[0][:750]
    terms = [
        (match[1].strip("「」『』 "), match.end()) for match in BOLD.finditer(intro)
    ]
    if latin_form(page_form) or KANA.fullmatch(page_form):
        opening = re.match(
            r"^\s*[「『']*" + re.escape(page_form) + r"['」』]*(?=\s*[（(])",
            intro,
            re.I,
        )
        if opening:
            terms.append((page_form, opening.end()))
    for index, (term, end) in enumerate(terms):
        surface = latin_form(term)
        tail = intro[end:]
        for _ in range(3):
            group = paren_after(tail)
            if group is None:
                break
            paren, tail = group
            readings = list(paren_readings(paren)) if surface else []
            for reading, method in readings:
                yield surface, reading, method
            # 大文字小文字を除いて主表記と記事名が対応する文だけで略記を採る。
            if readings and index == 0 and surface.casefold() == page_form.casefold():
                for alias in EXPLICIT_ALIAS.finditer(paren):
                    for reading, _ in readings:
                        yield (
                            alias["after"] or alias["before"],
                            reading,
                            "冒頭の略記・別表記",
                        )
            kana = unicodedata.normalize("NFKC", term).strip()
            if KANA.fullmatch(kana) and (index == 0 or kana == page_form):
                for alternate in LATIN_IN_PAREN.finditer(paren):
                    if alternate_form := latin_form(alternate["form"]):
                        yield alternate_form, kana, "仮名の見出しと併記"
        if surface and (reading := MARKED_READING.match(tail.lstrip(" \t　:：、"))):
            yield surface, reading["kana"].strip(), "読みと明記"


def write_record(target: BinaryIO, record: dict) -> None:
    """本文を含まない中間レコードをJSONLに書く。"""
    target.write(
        (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    )


def extract(stream: BinaryIO, output: BinaryIO) -> Counter[str]:
    """XMLを1ページずつ処理して読み終えた本文をメモリから解放する。"""
    events = ET.iterparse(stream, events=("start", "end"))
    _, root = next(events)
    ns = root.tag.partition("}")[0] + "}" if "}" in root.tag else ""
    names = {
        name: ns + name
        for name in ("page", "title", "ns", "redirect", "revision", "id", "text")
    }
    counts: Counter[str] = Counter()
    for event, node in events:
        if event != "end" or node.tag != names["page"]:
            continue
        counts["pages"] += 1
        if counts["pages"] % 250000 == 0:
            print(dict(counts), file=sys.stderr, flush=True)
        namespace = node.findtext(names["ns"])
        if namespace not in ("0", "14"):
            root.clear()
            continue
        title = node.findtext(names["title"], "")
        redirect = node.find(names["redirect"])
        revision = node.find(names["revision"])
        text = revision.findtext(names["text"], "") if revision is not None else ""
        if namespace == "14":
            if redirect is None:
                write_record(
                    output, {"c": title.split(":", 1)[-1], "p": category_names(text)}
                )
                counts["category_pages"] += 1
        elif redirect is not None:
            counts["redirect_pages"] += 1
            target = redirect.get("title", "").replace("_", " ")
            # 転送チェーンに日本語のページも含まれるため、名前の対応を残す。
            if target and "#" not in target:
                write_record(output, {"r": title, "t": target})
        elif revision is not None:
            counts["article_pages"] += 1
            pairs = sorted(set(mentions(title, text))) if text else []
            if pairs:
                write_record(
                    output,
                    {
                        "t": title,
                        "id": revision.findtext(names["id"]),
                        "p": category_names(text),
                        "m": pairs,
                    },
                )
                counts["articles_with_mentions"] += 1
        root.clear()
    return counts


def main() -> None:
    """圧縮済みダンプまたは標準入力から中間結果を作る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="XML.bz2または標準入力を示す -")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    stream = sys.stdin.buffer if args.input == "-" else bz2.open(args.input, "rb")
    with stream, gzip.open(args.output, "wb", compresslevel=3) as output:
        counts = extract(stream, output)
        write_record(output, {"stats": counts})
    print(json.dumps(counts, ensure_ascii=False), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
