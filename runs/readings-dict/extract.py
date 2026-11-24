"""公開辞書の用語と読みを照合し、資料別のJSONLと再現率を作る。"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import lzma
import random
import re
import subprocess
import tarfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator


# 表記は英字を含む語・略語・コマンドに限り、元の綴りと句読点を維持する。
LATIN = re.compile(r"[A-Za-z0-9 ._+/#&:()~!'@-]+")
KANA = re.compile(r"[ァ-ヺ][ァ-ヺー]+")
# 一字読みは実装で使う文字名に、辞書に現れる別表記と日本語の数字を補って判定する。
LETTER_NAMES = tuple(
    "エー/エイ ビー シー/スィー/シイ ディー/デー イー/イイ エフ ジー/ヂー エイチ/エッチ/エーチ "
    "アイ ジェー/ジェイ ケー/ケイ エル エム エヌ/エン オー/オウ ピー キュー/キウ/キュウ "
    "アール/アー エス ティー/テー ユー ブイ/ブィ/ヴィー/ヴイ/ヴィ/ビー "
    "ダブリュー/ダブリュウ/ダヴリュー/ダヴリュウ/タブリュー/ダブル/ダブルユー エックス/エキス "
    "ワイ ゼット/ズィー/ジー".split()
)
DIGIT_NAMES = tuple(
    "ゼロ/レイ/オー/マル ワン/イチ ツー/トゥー/ニ スリー/サン フォー/ヨン/シ ファイブ/ゴ "
    "シックス/ロク セブン/ナナ/シチ エイト/ハチ ナイン/キュウ/ク".split()
)
# 区切り記号を発音する一字読みも、文字ごとの読みの連結から判定する。
MARK_NAMES = {
    ".": "ドット/ピリオド/テン", "-": "ハイフン/マイナス/ダッシュ/ノ",
    "_": "アンダーバー/アンダースコア", "/": "スラッシュ/スラ", " ": "",
    "+": "プラス", "#": "シャープ/ハッシュ", "&": "アンド",
    ":": "コロン", "(": "", ")": "", "~": "チルダ", "'": "", "!": "", "@": "アット",
}
# 各文字の候補を検索中に組み立て直さない。
SPELLED_NAMES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", (*LETTER_NAMES, *DIGIT_NAMES)))
# 文字名に限って、伸ばし方や添え仮名の表記差を吸収する。
LETTER_NORMALIZE = str.maketrans({"ー": "", "ィ": "イ", "ゥ": "ウ"})
# 用語集外では、一般の訳語や普通の音写を避けるため略語・記号・固有名の綴りを優先する。
SPECIAL_SPELLING = re.compile(r"[0-9.+/#_]|[A-Z]{2}|[a-z][A-Z]")
# 技術語に見えても、会社名・人名など一般辞書の同綴語として紛れやすい表記を除く。
EXCLUDED_POS = {"人名", "地名", "地域", "組織"}
EXCLUDED_DOMAINS = {"人名", "キャラ", "国名", "地名", "地形", "観光", "店名", "大学名", "企業名", "組織名"}
# 入力資料で出力しなかったものも集計に残すため、処理する資料名を固定する。
SOURCES = ("neologd", "sudachidict", "sudachi-synonyms", "unidic", "ipadic", "alkana",
           "jst-thesaurus", "ipsj-wordlist", "jmdict", "skk", "wdic-tech", "wdic-telecom")
# WDICで人名・一般の企業・放送局・趣味などを扱う索引は処理しない。
WDIC_SKIP = {
    "TYMAN", "TYORGM", "TYORGR", "TYORGS", "TTPROD", "CYENT", "CYORG", "WAHAM", "WBCASTT", "WBCASTY",
    "WBORG", "WCYOGO", "CZBBS", "CZPASO", "CZUG", "CZYOGO",
}
# プログラム名として分類された見出しでは、小文字の独特な名前や固有名も対象にできる。
WDIC_NAME_FILES = {"PNOS", "PNSVR", "PNAPLLG", "PNAPLLI", "PNAPLLT", "PNAPLNU", "PTPROGN"}
# FOLDOCは分野の判定だけに使う。製品・規格・手法などに対応する分類に絞る。
FOLDOC_TOPICS = {
    "algorithm", "architecture", "artificial intelligence", "compiler", "cryptography",
    "data", "database", "electronics", "file format", "hardware", "language", "library",
    "mathematics", "networking", "operating system", "parallel", "programming", "protocol",
    "security", "software", "standard", "storage", "system", "tool", "utility", "web",
}


@dataclass(frozen=True)
class Candidate:
    """読みの根拠と、その辞書が分野を示したかを保持する。"""

    surface: str
    reading: str
    evidence: str
    technical: bool = False
    technical_name: bool = False


def latin(text: str) -> str:
    """全角英数字をそろえ、英字を含む有効な表記だけを返す。"""
    word = unicodedata.normalize("NFKC", text).strip()
    return word if len(word) >= 2 and LATIN.fullmatch(word) and re.search(r"[A-Za-z]", word) else ""


def katakana(text: str) -> str:
    """仮名のかな種と幅をそろえ、語中の空白と中点を除く。"""
    normalized = unicodedata.normalize("NFKC", text)
    kana = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in normalized)
    kana = re.sub(r"[\s・]+", "", kana)
    return kana if KANA.fullmatch(kana) else ""


@lru_cache(maxsize=16384)
def letter_reading(surface: str, reading: str) -> bool:
    """文字ごとの読みを連結して候補に一致するか調べる。長音の有無は同じ扱いにする。"""
    target = reading.translate(LETTER_NORMALIZE)
    offsets = {0: {0}}
    spelling = surface.upper()
    for index, char in enumerate(spelling):
        if not (starts := offsets.pop(index, None)):
            continue
        names = SPELLED_NAMES.get(char, MARK_NAMES.get(char, "")).split("/")
        if char in MARK_NAMES:
            names.append("")
        choices = [(index + 1, name) for name in names]
        # 製品番号を「イチサン」と「ジュウサン」のどちらで読んでも、
        # 他の文字が一字読みなら特殊読みとしては扱わない。
        if char in "123456789":
            digits = re.match(r"[0-9]{2,4}(?![0-9])", spelling[index:])
            if digits:
                choices.append((index + len(digits[0]), cardinal_reading(digits[0])))
        for end, name in choices:
            normalized = name.translate(LETTER_NORMALIZE)
            matches = {i + len(normalized) for i in starts if target.startswith(normalized, i)}
            if matches:
                offsets.setdefault(end, set()).update(matches)
    return len(target) in offsets.get(len(spelling), ())


def cardinal_reading(digits: str) -> str:
    """ASCII数字2〜4桁の日本語の位取り読みを作り、一字読みの判定にだけ使う。"""
    units = ("", "イチ", "ニ", "サン", "ヨン", "ゴ", "ロク", "ナナ", "ハチ", "キュウ")
    tens = ("", "ジュウ", "ニジュウ", "サンジュウ", "ヨンジュウ", "ゴジュウ",
            "ロクジュウ", "ナナジュウ", "ハチジュウ", "キュウジュウ")
    hundreds = ("", "ヒャク", "ニヒャク", "サンビャク", "ヨンヒャク", "ゴヒャク",
                "ロッピャク", "ナナヒャク", "ハッピャク", "キュウヒャク")
    thousands = ("", "セン", "ニセン", "サンゼン", "ヨンセン", "ゴセン", "ロクセン",
                 "ナナセン", "ハッセン", "キュウセン")
    a, b, c, d = map(int, digits.zfill(4))
    return thousands[a] + hundreds[b] + tens[c] + units[d]


def zip_rows(path: Path, pattern: str, encoding: str = "utf-8") -> Iterator[list[str]]:
    """指定したCSVを解凍しながら行単位で読む。"""
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if re.search(pattern, name)]
        if len(members) != 1:
            raise ValueError(f"{path}: CSVの候補が1件ではありません")
        with io.TextIOWrapper(archive.open(members[0]), encoding=encoding, newline="") as stream:
            yield from csv.reader(stream)


def mecab_archive(path: Path, *, neologd: bool) -> Iterator[Candidate]:
    """NEologdの全seedまたはIPAdicの全CSVから、名詞の表記と読み欄を読む。"""
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            filename = Path(member.name).name
            if neologd:
                if not member.name.endswith(".csv.xz") or "/seed/" not in member.name:
                    continue
            elif not member.name.endswith(".csv"):
                continue
            with archive.extractfile(member) as member_stream:
                binary_stream = lzma.LZMAFile(member_stream) if neologd else member_stream
                encoding = "utf-8" if neologd else "euc_jp"
                # IPAdicの古い外字は置換する。置換文字を含む表記・読みは形式検査で落ちる。
                with io.TextIOWrapper(binary_stream, encoding=encoding, errors="strict" if neologd else "replace",
                                      newline="") as stream:
                    for row in csv.reader(stream):
                        if len(row) >= 13 and row[4] == "名詞" and not EXCLUDED_POS.intersection(row[5:8]):
                            if surface := latin(row[0]):
                                yield Candidate(surface, row[11], f"{filename} / {row[0]}")


def unidic(path: Path) -> Iterator[Candidate]:
    """UniDic 2.1.2の書字形に対して発音形を取り、古い外来語も確認する。"""
    for row in zip_rows(path, r"/lex\.csv$"):
        if row[4] == "名詞" and not EXCLUDED_POS.intersection(row[5:8]):
            if surface := latin(row[0]):
                yield Candidate(surface, row[13], f"lex.csv / {row[0]}")


def sudachi(directory: Path, it_groups: set[str]) -> Iterator[Candidate]:
    """Sudachi V1の各辞書で、見出しと読み欄を結びつける。"""
    for stem in ("small_lex", "core_lex", "notcore_lex"):
        records = zip_rows(directory / f"{stem}.zip", rf"{stem}\.csv$")
        columns = next(records)
        if columns[4] != "Headword" or columns[11] != "ReadingForm" or "SynonymGroups" not in columns:
            raise ValueError(f"{stem}: Sudachi V1の列名が一致しません")
        domain_column = columns.index("SynonymGroups")
        for row in records:
            if row[5] == "名詞" and not EXCLUDED_POS.intersection(row[6:9]):
                if surface := latin(row[4] or row[0]):
                    groups = set(row[domain_column].split("/"))
                    is_technical = bool(groups & it_groups)
                    yield Candidate(surface, row[11], f"{stem}.csv / {row[4] or row[0]}", is_technical)


def synonyms(path: Path) -> tuple[list[Candidate], set[str]]:
    """対訳・別称・略語展開を避け、同一語形内の英字原綴りと仮名表記を結ぶ。"""
    by_form: defaultdict[tuple[str, ...], list[list[str]]] = defaultdict(list)
    it_groups = set()
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if not row or row[2] == "2" or not row[3] or row[4] not in {"0", "1"} or row[6] == "3":
                continue
            domains = row[7].strip("()").split(",")
            if EXCLUDED_DOMAINS.intersection(domains):
                continue
            if "IT" in domains:
                it_groups.add(row[0])
            by_form[tuple(row[:1] + row[3:6])].append(row)

    candidates = []
    for form, rows in by_form.items():
        # 仮名と英字が同じ略語・語義に属し、英字側が原綴りと明記された場合だけ結ぶ。
        # 「略語」と「正式名称」は、同じグループでも別の語形になる。
        is_technical = any("IT" in r[7].strip("()").split(",") for r in rows)
        for row in rows:
            if row[6] != "1" or not (surface := latin(row[8])):
                continue
            for other in rows:
                if other[6] in {"0", "2"} and katakana(other[8]):
                    candidates.append(Candidate(surface, other[8], f"グループ{form[0]} / {row[8]} → {other[8]}",
                                                is_technical))
    return candidates, it_groups


def jst(path: Path) -> Iterator[Candidate]:
    """JSTの計算機科学で、仮名の読み欄または自動発音欄を調べる。"""
    for row in zip_rows(path, r"mecab_thesaurus\.csv$", "cp932"):
        if "EG01" in re.split(r"[^A-Z0-9]+", row[17]) and (surface := latin(row[0])):
            yield Candidate(surface, katakana(row[11]) or row[12],
                            f"JSTシソーラスID {row[14]} / {row[0]}", True)


def ipsj(path: Path) -> Iterator[Candidate]:
    """情報科用語リストに併記された英字表記と仮名表記を読む。"""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            forms = row["用語"].split("|")
            if not row["カテゴリ"] or len(forms) != 2:
                continue
            # 用語欄は訳語も扱う。略語の正式名称や括弧書きの略語は採らない。
            for form, alternate in (forms, reversed(forms)):
                if ((surface := latin(form)) and "(" not in surface and not surface.isupper()
                        and katakana(alternate)):
                    yield Candidate(surface, alternate, f"用語「{form}」「{alternate}」", True)


def jmdict(path: Path) -> Iterator[Candidate]:
    """JMdictの分野タグと読み制約を使い、英字の見出しに対応する仮名だけを採る。"""
    with tarfile.open(path, "r:gz") as archive:
        member = next(item for item in archive if item.name.endswith(".json"))
        with archive.extractfile(member) as stream:
            entries = json.load(stream)["words"]
    for entry in entries:
        senses = [s for s in entry["sense"] if {"comp", "electr", "elec"}.intersection(s["field"])]
        if not senses:
            continue
        for word in entry["kanji"]:
            if not (surface := latin(word["text"])) or {"sK", "ik", "iK"}.intersection(word["tags"]):
                continue
            for kana in entry["kana"]:
                allowed_kanji = kana["appliesToKanji"]
                if "*" not in allowed_kanji and word["text"] not in allowed_kanji:
                    continue
                if any(
                    ("*" in sense["appliesToKanji"] or word["text"] in sense["appliesToKanji"])
                    and ("*" in sense["appliesToKana"] or kana["text"] in sense["appliesToKana"])
                    for sense in senses
                ):
                    yield Candidate(surface, kana["text"], f"JMdict {entry['id']} / {word['text']}", True)


def skk(path: Path) -> Iterator[Candidate]:
    """SKKのかな入力から英字候補への変換と、英単語キーの仮名候補を読む。"""
    with path.open(encoding="euc_jp", errors="replace") as stream:
        for line in stream:
            if line.startswith(";;") or " /" not in line:
                continue
            key, values = line.rstrip("\n").split(" /", 1)
            for item in values.rstrip("/").split("/"):
                value, _, note = item.partition(";")
                if katakana(key) and (surface := latin(value)):
                    yield Candidate(surface, key, f"SKK-JISYO.L / かなキー「{key}」")
                elif (surface := latin(key)) and katakana(value):
                    if note.startswith(("[動物]", "[地名]", "[人名]")):
                        continue
                    yield Candidate(surface, value, f"SKK-JISYO.L / 英字キー「{key}」")


def alkana(path: Path) -> Iterator[Candidate]:
    """公開データの辞書リテラルを読み、外部コードを実行しない。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    [assignment] = tree.body
    for surface, reading in ast.literal_eval(assignment.value).items():
        if word := latin(surface):
            yield Candidate(word, reading, f"alkana/data.py / {surface}")


def foldoc(path: Path) -> set[str]:
    """英語の計算機辞典から分野が明記された見出しを取得する。"""
    with tarfile.open(path, "r:gz") as archive, archive.extractfile("Dictionary") as stream:
        # 冒頭の分野タグだけを使い、FOLDOC本文は出力に載せない。
        raw = stream.read().decode("utf-8", errors="replace")
    technical = set()
    for match in re.finditer(r"^([^\s].*)\n\n\t<([^>\n]+)>", raw, re.MULTILINE):
        word, topics = match.groups()
        if not latin(word) or not FOLDOC_TOPICS.intersection(re.split(r",\s*", topics)):
            continue
        # 一般語と同じ小文字単語をFOLDOC掲載だけで未知語へ入れない。
        if SPECIAL_SPELLING.search(word):
            technical.add(latin(word))
    return technical


def wdic(path: Path, seven_zip: str) -> Iterator[Candidate]:
    """分類済みのWDIC見出しと明示された読みを取り出す。原文は展開先へ書かない。"""
    listing = subprocess.check_output([seven_zip, "l", "-slt", str(path)], encoding="utf-8")
    members = re.findall(r"^Path = ([A-Z0-9]+)\.DV6$", listing, re.MULTILINE)
    if not members:
        raise ValueError(f"{path}: DV6の項目がありません")
    for part in members:
        if part in WDIC_SKIP:
            continue
        # DV6の見出しは行頭の#、読み欄は直後のメタデータ内のyomi。
        text = subprocess.check_output(
            [seven_zip, "e", "-so", "-spd", str(path), f"{part}.DV6"], encoding="utf-8-sig",
        )
        for entry in re.split(r"^#", text, flags=re.MULTILINE)[1:]:
            title, _, rest = entry.partition("\n")
            title = title.strip()
            # 同綴語を区別する括弧書きは見出しIDに残し、表記から除く。
            surface = latin(re.sub(r" \([^()]+\)$", "", title))
            if not surface or surface.startswith("/") or len(surface) > 44 or " aka " in surface.casefold():
                continue
            for line in rest.splitlines():
                if not re.match(r"^\t[a-z]+:", line):
                    break
                if line.startswith("\tyomi:"):
                    reading = line.removeprefix("\tyomi:").replace("-", "")
                    # 短い頭字語の後ろに正式名称や訳語を書いた項目を除く。
                    if surface.isupper() and surface.isalpha() and len(katakana(reading)) > 2 * len(surface) + 2:
                        continue
                    yield Candidate(surface, reading, f"{part}.DV6 / {title}", True, part in WDIC_NAME_FILES)


def glossary_index(paths: list[Path]) -> dict[str, dict[str, set[str]]]:
    """2版の同一表記の読みを合わせ、大小文字の異なる語も区別して保持する。"""
    index: defaultdict[str, defaultdict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if word := latin(row["surface"]):
                    index[word.casefold()][word].update(katakana(reading).replace("ー", "") for reading in row["readings"])
    return index


def pair_list(path: Path) -> set[tuple[str, str]]:
    """TSVの表記とカンマ区切りの読みを、完全一致の集計用に読む。"""
    pairs = set()
    with path.open(encoding="utf-8", newline="") as stream:
        for surface, readings, *_ in csv.reader(stream, delimiter="\t"):
            for reading in readings.split(","):
                if not latin(surface) or not katakana(reading):
                    raise ValueError(f"{path}: 表記か読みが無効です: {surface!r} {reading!r}")
                pairs.add((latin(surface), katakana(reading)))
    return pairs


def resembles_known_reading(reading: str, known: Iterable[str]) -> bool:
    """一般辞書では、別の語義を混ぜないよう既存の読みと全体が近い場合だけ採る。"""
    reading = reading.replace("ー", "")
    for base in known:
        # 前後に略称や別表記をつないだ読みと、短い同綴語を避ける。
        if min(len(base), len(reading)) < 4 or abs(len(base) - len(reading)) > 2:
            continue
        if SequenceMatcher(None, base, reading, autojunk=False).ratio() >= 0.78:
            return True
    return False


def recall(pairs: set[tuple[str, str]], seeds: set[tuple[str, str]]) -> dict:
    """表記・読みの組と、指定読みを1つ以上拾った表記の両方を集計する。"""
    hits = pairs & seeds
    return {
        "pair_count": len(seeds),
        "pair_hits": len(hits),
        "surface_count": len({word for word, _ in seeds}),
        "surface_hits": len({word for word, _ in hits}),
        "hits": sorted(hits),
    }


def digest(path: Path) -> str:
    """入力と生成物の内容を再現手順で比較できるようにする。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extract(args: argparse.Namespace) -> dict:
    """読みの候補を資料ごとに選び、出力と機械集計を保存する。"""
    upstream = args.inputs
    glossary = glossary_index(args.glossary)
    seeds = pair_list(args.seed)
    rejected = pair_list(args.reject)
    reviewed = pair_list(args.reviewed)
    syn_rows, it_groups = synonyms(upstream / "synonyms.txt")
    jst_rows = list(jst(upstream / "jst.zip"))
    ipsj_rows = list(ipsj(upstream / "ipsj.csv"))
    jmdict_rows = list(jmdict(upstream / "jmdict.tgz"))
    wdic_tech = list(wdic(upstream / "wdc152t.7z", args.seven_zip))
    wdic_telecom = list(wdic(upstream / "wdc152w.7z", args.seven_zip))
    foldoc_words = foldoc(upstream / "foldoc.tar.gz")
    domain_words = foldoc_words | {surface for surface, _ in reviewed}
    direct_pairs = set()
    # WDICの表記や読みは他の辞書の採否に使わず、利用条件を資料単位で追えるようにする。
    for rows in (syn_rows, jst_rows, ipsj_rows, jmdict_rows):
        for row in rows:
            if row.technical and (reading := katakana(row.reading)):
                domain_words.add(row.surface)
                direct_pairs.add((row.surface, reading.replace("ー", "")))
    known_domain: defaultdict[str, set[str]] = defaultdict(set)
    for word in domain_words:
        known_domain[word.casefold()].add(word)
    all_inputs: dict[str, Iterable[Candidate]] = {
        "neologd": mecab_archive(upstream / "neologd.tar.gz", neologd=True),
        "sudachidict": sudachi(upstream, it_groups),
        "sudachi-synonyms": syn_rows,
        "unidic": unidic(upstream / "unidic.zip"),
        "ipadic": mecab_archive(upstream / "ipadic.tar.gz", neologd=False),
        "alkana": alkana(upstream / "alkana-data.py"),
        "jst-thesaurus": jst_rows,
        "ipsj-wordlist": ipsj_rows,
        "jmdict": jmdict_rows,
        "skk": skk(upstream / "skk-L"),
        "wdic-tech": wdic_tech,
        "wdic-telecom": wdic_telecom,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    report = {}
    union: set[tuple[str, str]] = set()
    raw_union: set[tuple[str, str]] = set()
    existing_seed_hits = {
        (surface, reading) for surface, reading in seeds
        if reading.replace("ー", "") in glossary.get(surface.casefold(), {}).get(surface, ())
    }
    for source in SOURCES:
        counts: Counter[str] = Counter()
        rows = {}
        raw_pairs: set[tuple[str, str]] = set()
        for row in all_inputs[source]:
            counts["latin_rows"] += 1
            if not (reading := katakana(row.reading)):
                counts["invalid_kana"] += 1
                continue
            variants = glossary.get(row.surface.casefold(), {})
            surface = row.surface
            if surface not in variants:
                # 大小文字だけで別の追加語にせず、競合しない用語集表記に合わせる。
                if len(variants) == 1:
                    surface = next(iter(variants))
                elif variants:
                    counts["ambiguous_glossary_surface"] += 1
                    continue
                elif not variants and source in {"alkana", "skk"} and len(known_domain[surface.casefold()]) == 1:
                    surface = next(iter(known_domain[surface.casefold()]))
            in_glossary = surface in variants
            pair = surface, reading
            normalized = reading.replace("ー", "")
            has_domain_evidence = (row.technical or (surface, normalized) in direct_pairs or pair in reviewed)
            if not in_glossary and (not has_domain_evidence or not (
                row.technical_name or SPECIAL_SPELLING.search(surface) or pair in reviewed
            )):
                counts["outside_domain"] += 1
                continue
            if source == "alkana" and not in_glossary:
                # 読み上げ用の英和データに固有名の読みを推定させない。
                counts["outside_domain"] += 1
                continue
            if letter_reading(surface, reading):
                counts["letter_reading"] += 1
                continue
            if pair in rejected:
                counts["manually_rejected"] += 1
                continue
            old_readings = variants.get(surface, ())
            if normalized in old_readings:
                raw_pairs.add(pair)
                counts["existing_reading"] += 1
                continue
            if not has_domain_evidence:
                if source == "alkana" and surface not in foldoc_words:
                    counts["english_pronunciation_only"] += 1
                    continue
                if source == "skk" and "英字キー" in row.evidence:
                    counts["translation_only"] += 1
                    continue
                if not resembles_known_reading(reading, old_readings):
                    counts["unconfirmed_reading"] += 1
                    continue
            raw_pairs.add(pair)
            item = {"surface": surface, "reading": reading, "source": source,
                    "evidence": row.evidence, "in_glossary": in_glossary}
            if pair not in rows or row.evidence < rows[pair]["evidence"]:
                rows[pair] = item
        ordered = [rows[pair] for pair in sorted(rows)]
        path = args.output / f"{source}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for item in ordered:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        union.update(rows)
        raw_union.update(raw_pairs)
        report[source] = {
            "rows": len(ordered),
            "surfaces": len({surface for surface, _ in rows}),
            "in_glossary": sum(item["in_glossary"] for item in ordered),
            "new_surfaces": len({item["surface"] for item in ordered if not item["in_glossary"]}),
            "filter_counts": dict(counts),
            "sha256": digest(path),
            "seed": recall(set(rows), seeds),
            "seed_before_existing_reading_filter": recall(raw_pairs, seeds),
            "sample": random.Random(20261124).sample(ordered, min(30, len(ordered))),
        }
        print(source, report[source]["rows"], report[source]["new_surfaces"], report[source]["seed"]["pair_hits"], flush=True)

    glossary_surfaces = {word for variants in glossary.values() for word in variants}
    return {
        "inputs": {path.name: digest(path) for path in [*args.glossary, args.seed]},
        "glossary_latin_surfaces": len(glossary_surfaces),
        "sources": report,
        "union": {
            "rows": len(union),
            "surfaces": len({surface for surface, _ in union}),
            "new_pairs": sum(surface not in glossary_surfaces for surface, _ in union),
            "new_surfaces": len({surface for surface, _ in union if surface not in glossary_surfaces}),
            "seed": recall(union, seeds),
            "seed_before_existing_reading_filter": recall(raw_union, seeds),
            "existing_seed": recall(existing_seed_hits, seeds),
            "uncovered_seed": sorted(seeds - union - existing_seed_hits),
        },
    }


def main() -> None:
    """取得済みの辞書と照合用の入力を指定して実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--glossary", nargs=2, type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seven-zip", default="7zz", help="WDIC配布用7zを読み出すコマンド")
    parser.add_argument("--reject", type=Path, default=Path(__file__).with_name("rejected.tsv"))
    parser.add_argument("--reviewed", type=Path, default=Path(__file__).with_name("reviewed.tsv"))
    args = parser.parse_args()
    report = extract(args)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
