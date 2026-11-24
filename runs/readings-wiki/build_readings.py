"""公開資料の読みを用語集と照合し、追加候補と資料別の監査集計を作る。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from extract_jawiki import latin_form, title_form
from voiceime.formatter.glossary import (
    _DIGIT_READINGS,
    _ENGLISH_LETTER_READINGS,
    _kana_to_romaji,
    normalize_kana,
)

# 直接付いた専門カテゴリか、その直上2階層の技術カテゴリを照合する。
TECH_CATEGORY = re.compile(
    r"計算機|ソフト(?:ウェア|ウエア)|プログラミング|プログラム言語|プログラム変換|"
    r"オペレーティングシステム|(?:^| )(?:UNIX|Linux|BSD|Windows|macOS)(?:$| |の)|"
    r"コマンド(?:ライン)?|^シェル(?:$|\s|\s*\(|スクリプト)|UNIXシェル|"
    r"エディタ|コンパイラ|インタプリタ|ライブラリ|"
    r"コンピュータ(?:$|の(?!文化|社会|利用)|科学|グラフィックス|ネットワーク|アーキテクチャ|ハードウェア|用語|ストレージ)|"
    r"(?:パーソナル|マイクロ|スーパー)コンピュータ|ゲームエンジン|ゲーム開発ツール|"
    r"ネットワーク(?:技術|機器|プロトコル|ソフトウェア)|インターネット(?:技術|標準|プロトコル)|"
    r"通信(?:プロトコル|規格|方式)|無線LAN|電子メール|IEEE(?: 802|規格|標準)|IETF標準|^HTTP$|"
    r"スマートフォン|携帯電話端末|Android端末|タブレット型端末|電波望遠鏡|"
    r"ウェブ(?:ブラウザ|サーバ|標準|技術|アプリ|検索)|"
    r"(?:Web|HTTP)(?:サーバ|技術|アプリ)|データベース|ファイル(?:システム|フォーマット|形式)|"
    r"文字コード|データ圧縮|(?:音声|画像|動画|映像)(?:ファイル|フォーマット|圧縮)|コーデック|"
    r"半導体|集積回路|電子(?:工学|部品|回路)|マイクロ(?:コントローラ|プロセッサ)|"
    r"人工知能|深層学習|機械学習|ニューラルネットワーク|自然言語処理|計算言語学|"
    r"コンピュータビジョン|情報(?:工学|科学|検索|セキュリティ|処理)|サイバーセキュリティ|"
    r"暗号(?:技術|ソフトウェア|アルゴリズム)|分散コンピューティング|クラウドコンピューティング|"
    r"(?:ACM|IEEE|USENIX)の(?:学術誌|論文誌|国際会議|会議)|情報処理学会|電子情報通信学会|ネットワーク標準",
    re.I,
)
# 分野の親カテゴリがあっても、作品・企業・人物など個別のカテゴリは対象から外す。
OUT_OF_SCOPE = re.compile(
    r"曖昧さ回避|存命人物|出身の人物|の人物(?:$|\s)|[0-9]年(?:生|没)$|"
    r"(?:俳優|歌手|作家|声優|選手|政治家|実業家|音楽家|バンド|ミュージシャン)$|"
    r"(?:物理学者|数学者|工学者|計算機科学者|人工知能学者|プログラマ|科学教育者|博物館フェロー)$|"
    r"(?:企業|会社|メーカー|の姓|の人名|の男性名|の女性名|人物の愛称|の地名|の都市|の民族)$|"
    r"コンピュータゲームメーカー|上場企業|廃業した企業|設立の企業|"
    r"の(?:楽曲|シングル|アルバム|映画|映画作品|小説|漫画|テレビ番組|テレビドラマ|アニメ作品)$|"
    r"音楽(?:グループ|デュオ|プロデューサー)|アイドルグループ|歌手グループ|ヒップホップ・グループ|のDJ$|"
    r"スポーツチーム|登場人物|登場キャラクター|の車種|漫画作品|出版物|出版社|"
    r"(?<!学術)雑誌(?:$|[ (])|ラジオ番組|(?:の|歴史上の)テレビ番組|同人(?:誌)?即売会|"
    r"国営放送|国際放送|ラジオ局|テレビ局|のメディア$|インターネット・ミーム|"
    r"^トランプ$|^架空の|ヘリコプター|無人航空機|ボードゲーム|"
    r"ゲームソフト|ゲーム作品|ゲームのシリーズ|コンピュータゲーム(?!エンジン|開発ツール)",
    re.I,
)
# 既存語は、カテゴリが未設定でも記事名から技術分野・製品が確認できれば採る。
TECH_TITLE = re.compile(
    r"\((?:プログラミング言語|ソフトウェア|オペレーティングシステム|"
    r"コンピュータ|ファイル形式|通信プロトコル|計算機|電子工学)\)$|"
    r"^(?:SQL Server|ゴリラガラス|ドイツ工業規格)$",
    re.I,
)
# 上位への経路だけで古い測定器や音楽作品を電子工学と判定しない。
NON_TECHNICAL_ANCESTRY = {"計測機器", "電子音楽", "放送"}
# 読みと表記を比べる際に、繰り返し子音や日本語で区別しにくい子音をそろえる。
SOUND_GROUPS = str.maketrans(
    {"l": "r", "v": "b", "p": "b", "c": "k", "q": "k", "z": "s"}
)
KATAKANA = re.compile(r"[ァ-ヺ][ァ-ヺー]{1,78}")
JAPANESE_DIGITS = dict(
    zip(
        "0123456789",
        (
            ("ゼロ", "レイ"),
            ("イチ",),
            ("ニ",),
            ("サン",),
            ("ヨン", "シ"),
            ("ゴ",),
            ("ロク",),
            ("ナナ", "シチ"),
            ("ハチ",),
            ("キュウ", "ク"),
        ),
    )
)
LETTER_VARIANTS = {
    "A": ("エイ",),
    "B": ("ビィ",),
    "C": ("シィ",),
    "D": ("デー", "ディィ"),
    "E": ("イィ",),
    "G": ("ジィ",),
    "H": ("エッチ",),
    "J": ("ジェイ",),
    "K": ("ケイ",),
    "P": ("ピィ",),
    "Q": ("キュウ",),
    "T": ("テー", "ティィ"),
    "U": ("ユウ",),
    "V": ("ヴィー", "ヴイ", "ブィ"),
    "W": ("ダブル", "ダブリュウ"),
    "Z": ("ズィー", "ジー", "ゼッド"),
}
# ラベルの取り違えや表記の取りこぼしを確認する際に、明記の強い根拠から優先する。
EVIDENCE_PRIORITY = {
    "読みと明記": 6,
    "英字の直後": 5,
    "冒頭の略記・別表記": 4,
    "転送先の同表記": 4,
    "仮名の見出しと併記": 3,
    "仮名記事への転送": 2,
    "日本語ラベル": 2,
    "日本語別名": 1,
}


@dataclass(frozen=True)
class Candidate:
    """出力用の5項目と、資料内で根拠が重複した際に使う優先度。"""

    surface: str
    reading: str
    source: str
    evidence: str
    in_glossary: bool
    priority: int


def surface_key(value: str) -> str:
    """大文字小文字・全半角・空白幅だけを照合時にそろえる。"""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def kana_reading(value: str) -> str | None:
    """仮名をカタカナへそろえ、長音を保って空白と中点を外す。"""
    normalized = normalize_kana(value, ignore_long_vowel=False)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized if KATAKANA.fullmatch(normalized) else None


def is_spelled(surface: str, reading: str) -> bool:
    """全ての英数字を順に一字ずつ読んだものと一致するか判定する。"""
    pattern = []
    for character in re.findall(r"[A-Z0-9]", surface.upper()):
        if character.isdigit():
            variants = (_DIGIT_READINGS[character], *JAPANESE_DIGITS[character])
        else:
            variants = (
                _ENGLISH_LETTER_READINGS[character],
                *LETTER_VARIANTS.get(character, ()),
            )
        options = sorted({normalize_kana(value) for value in variants})
        pattern.append("(?:" + "|".join(options) + ")")
    return bool(pattern and re.fullmatch("".join(pattern), normalize_kana(reading)))


def sound_key(value: str) -> str:
    """ラベル間の対応確認に使う子音列。読みの生成には使わない。"""
    roman = _kana_to_romaji(value).translate(SOUND_GROUPS)
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiou]", "", roman))


def sounds_related(surface: str, reading: str) -> bool:
    """資料のラベルを読みと見なす前に、全体に綴りとの対応があるか確かめる。"""
    latin = re.sub(r"[^a-z]", "", surface.lower())
    kana = re.sub(r"[^a-z]", "", _kana_to_romaji(reading))
    if not latin or not kana:
        return False
    # 短い表記への旧製品名・説明語の付け足しを避ける。数字付きは読みの長さが増える。
    if not any(character.isdigit() for character in surface) and len(kana) > max(
        1.85 * len(latin), len(latin) + 3
    ):
        return False
    left, right = sound_key(latin), sound_key(kana)
    # 一般名で終わる項目では、末尾だけ一致する別ブランドの別名を除く。
    words = surface.split()
    first = sound_key(words[0])
    if len(words) > 1 and len(first) >= 2 and len(right) >= 2 and first[0] != right[0]:
        return False
    if (
        latin == kana
        or SequenceMatcher(None, latin, kana, autojunk=False).ratio() >= 0.66
    ):
        return True
    if not left or not right:
        return False
    score = SequenceMatcher(None, left, right, autojunk=False).ratio()
    return score >= 0.7 and (left[0] == right[0] or left[-1] == right[-1])


def plain_english(surface: str, words: set[str]) -> bool:
    """略語・記号・造語がなく、一般英単語だけで書かれた表記を除く。"""
    for part in re.split(r"[ -]+", surface):
        if not re.fullmatch(r"[A-Za-z]+", part) or not (
            part.islower() or part.istitle()
        ):
            return False
        word = part.lower()
        forms = {word, word.removesuffix("s")}
        if word.endswith("ing"):
            stem = word[:-3]
            forms.update((stem, stem + "e"))
            if len(stem) >= 2 and stem[-1] == stem[-2]:
                forms.add(stem[:-1])
        if forms.isdisjoint(words):
            return False
    return True


def load_glossary(paths: Iterable[Path]) -> dict[str, tuple[str, set[str]]]:
    """指定された両用語集の表記と読みを合わせ、既存表記の綴りを保持する。"""
    glossary: dict[str, tuple[str, set[str]]] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if surface := latin_form(row["surface"]):
                _, readings = glossary.setdefault(
                    surface_key(surface), (surface, set())
                )
                values = row.get("readings", [row.get("reading", "")])
                if isinstance(values, str):
                    values = [values]
                readings.update(value for raw in values if (value := kana_reading(raw)))
    return glossary


def wiki_candidates(path: Path, glossary: dict, counts: Counter) -> Iterator[tuple]:
    """記事と転送を、カテゴリと旧版IDを追える候補に整理する。"""
    parents: dict[str, list[str]] = {}
    redirects: dict[str, str] = {}
    articles = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "c" in row:
                parents[row["c"]] = row["p"]
            elif "r" in row:
                redirects[row["r"]] = row["t"]
            elif "stats" in row:
                counts.update(row["stats"])
            else:
                articles[row["t"]] = row
    if not counts["article_pages"]:
        raise ValueError("ダンプ全体の走査件数がありません")

    # 既存用語の転送をたどり、転送先の仮名記事名または冒頭で表記された読みを照合する。
    aliases: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for redirect, target in redirects.items():
        if (
            not (surface := latin_form(title_form(redirect)))
            or surface_key(surface) not in glossary
        ):
            continue
        seen = {redirect}
        while target in redirects and target not in seen:
            seen.add(target)
            target = redirects[target]
        if target in seen or "(" in target or "（" in target:
            continue
        if target in articles:
            aliases[target].append((surface, redirect))
    for title, article in articles.items():
        categories = article["p"]
        if title.endswith("(曖昧さ回避)") or any(
            OUT_OF_SCOPE.search(category) for category in categories
        ):
            counts["out_of_scope_articles"] += 1
            continue
        level = set(categories)
        technical = set()
        for _ in range(3):
            technical.update(
                category for category in level if TECH_CATEGORY.search(category)
            )
            if technical or not level:
                break
            level = {
                parent
                for category in level
                if category not in NON_TECHNICAL_ANCESTRY
                for parent in parents.get(category, [])
                if not OUT_OF_SCOPE.search(parent)
            }
        url = f"https://ja.wikipedia.org/w/index.php?oldid={article['id']}"
        evidence = f"「{title}」 {url}"
        verified_title = bool(TECH_TITLE.search(unicodedata.normalize("NFKC", title)))
        if (technical or verified_title) and kana_reading(title):
            for alias, redirect in aliases[title]:
                counts["kana_redirect_matches"] += 1
                yield (
                    alias,
                    title,
                    "Wikipedia-ja",
                    f"「{redirect}」→「{title}」 {url}",
                    True,
                    "仮名記事への転送",
                    False,
                )
        for form, reading, method in article["m"]:
            if method == "冒頭の略記・別表記" and len(title_form(title).split()) > 1:
                counts["expanded_abbreviation"] += 1
                continue
            known_surface = surface_key(form) in glossary
            if not technical and not (verified_title and known_surface):
                counts["unverified_article_topic"] += 1
                continue
            # 転送先の別概念の読みを移さないよう、対象を明示した組だけを対応付ける。
            yield (
                form,
                reading,
                "Wikipedia-ja",
                evidence,
                bool(technical or verified_title),
                method,
                method != "仮名の見出しと併記",
            )
            for alias, _ in aliases[title]:
                compact_alias = re.sub(r"[ _-]", "", surface_key(alias))
                compact_form = re.sub(r"[ _-]", "", surface_key(form))
                if compact_alias == compact_form and surface_key(alias) != surface_key(
                    form
                ):
                    counts["redirect_matches"] += 1
                    yield (
                        alias,
                        reading,
                        "Wikipedia-ja",
                        evidence,
                        True,
                        "転送先の同表記",
                        True,
                    )


def wikidata_candidates(
    paths: Iterable[Path], excluded_path: Path, counts: Counter
) -> Iterator[tuple]:
    """明示した技術分類にある項目から、英語ラベルと日本語名の組を読む。"""
    excluded_header, *excluded_ids = excluded_path.read_text(
        encoding="utf-8"
    ).splitlines()
    if excluded_header != "?item":
        raise ValueError(f"想定外のSPARQL応答: {excluded_path.name}")
    excluded = set(excluded_ids)
    counts["excluded_entities"] = len(excluded)
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            if stream.readline().rstrip() != "?item\t?en\t?name\t?prop\t?type":
                raise ValueError(f"想定外のSPARQL応答: {path.name}")
            for line in stream:
                item, label, name, prop, item_type = line.rstrip("\n").split("\t")
                counts[path.name] += 1
                if item in excluded:
                    counts["out_of_scope_rows"] += 1
                    continue
                if not label.endswith("@en") or not name.endswith("@ja"):
                    raise ValueError(f"言語タグのないSPARQL応答: {path.name}")
                surface, reading = json.loads(label[:-3]), json.loads(name[:-3])
                entity_id = item.removesuffix(">").rsplit("/", 1)[-1]
                class_id = item_type.removesuffix(">").rsplit("/", 1)[-1]
                method = "日本語別名" if prop.endswith("#altLabel>") else "日本語ラベル"
                evidence = f"{entity_id}「{surface}」{method} (P31={class_id}) https://www.wikidata.org/wiki/{entity_id}"
                yield surface, reading, "Wikidata", evidence, True, method, False


def filter_candidates(
    rows: Iterable[tuple], glossary: dict, words: set[str], counts: Counter
) -> list[Candidate]:
    """一字読み・既出・対象外・ラベル上の別概念を取り除き、同じ資料の根拠をまとめる。"""
    matches: dict[tuple[str, str], Candidate] = {}
    for raw_form, raw_kana, source, evidence, technical, method, explicit in rows:
        surface = latin_form(raw_form)
        reading = kana_reading(raw_kana)
        if not surface or not reading:
            counts["invalid_form_or_reading"] += 1
            continue
        key = surface_key(surface)
        in_glossary = key in glossary
        if not (in_glossary or technical):
            counts["no_technical_category"] += 1
            continue
        if is_spelled(surface, reading):
            counts["letter_by_letter"] += 1
            continue
        if in_glossary:
            surface, existing = glossary[key]
            if reading in existing:
                counts["existing_reading"] += 1
                continue
        elif plain_english(surface, words):
            counts["plain_english"] += 1
            continue
        if not explicit and not sounds_related(surface, reading):
            counts["label_without_phonetic_match"] += 1
            continue
        priority = EVIDENCE_PRIORITY[method]
        if source == "Wikipedia-ja":
            title, url = evidence.rsplit(" ", 1)
            evidence = f"{title}（{method}） {url}"
        candidate = Candidate(surface, reading, source, evidence, in_glossary, priority)
        duplicate_key = (key, reading)
        previous = matches.get(duplicate_key)
        if previous is None or (-priority, evidence) < (
            -previous.priority,
            previous.evidence,
        ):
            matches[duplicate_key] = candidate
    return [matches[key] for key in sorted(matches)]


def load_seed(path: Path) -> dict[tuple[str, str], str]:
    """種の候補を表記・読みの組として読み、長音を含む一致で数えられるようにする。"""
    seed = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        surface, readings = line.split("\t")
        for raw in readings.split(","):
            reading = kana_reading(raw)
            if not reading:
                raise ValueError(f"種に仮名として扱えない読みがあります: {surface}")
            seed[surface_key(surface), reading] = surface
    return seed


def record(row: Candidate) -> dict:
    """採用理由の優先度を内部に留め、共通仕様の5項目に変換する。"""
    value = asdict(row)
    del value["priority"]
    return value


def describe(rows: list[Candidate], seed: dict) -> dict:
    """件数、種の表記・組の一致、固定seedの無作為抽出を返す。"""
    pairs = {(surface_key(row.surface), row.reading) for row in rows}
    hits = sorted(pairs & seed.keys())
    return {
        "pairs": len(rows),
        "surfaces": len({key for key, _ in pairs}),
        "in_glossary_pairs": sum(row.in_glossary for row in rows),
        "new_pairs": sum(not row.in_glossary for row in rows),
        "new_surfaces": len(
            {surface_key(row.surface) for row in rows if not row.in_glossary}
        ),
        "seed_hit_surfaces": len({key for key, _ in hits}),
        "seed_hit_pairs": len(hits),
        "seed_hits": [[seed[pair], pair[1]] for pair in hits],
        "sample": [
            record(row)
            for row in random.Random(20261124).sample(rows, min(30, len(rows)))
        ],
    }


def main() -> None:
    """資料を独立に集計してから両資料の重複を除き、出力を固定する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wikipedia", type=Path)
    parser.add_argument("--wikidata", nargs="+", type=Path, required=True)
    parser.add_argument("--wikidata-excluded", type=Path, required=True)
    parser.add_argument("--glossary", nargs=2, type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--english-words", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    glossary = load_glossary(args.glossary)
    seed = load_seed(args.seed)
    word_data = args.english_words.read_bytes()
    words = {word for word in word_data.decode().splitlines() if word.islower()}
    wiki_counts, data_counts = Counter(), Counter()
    wiki = (
        filter_candidates(
            wiki_candidates(args.wikipedia, glossary, wiki_counts),
            glossary,
            words,
            wiki_counts,
        )
        if args.wikipedia
        else []
    )
    data = filter_candidates(
        wikidata_candidates(args.wikidata, args.wikidata_excluded, data_counts),
        glossary,
        words,
        data_counts,
    )
    combined = {(surface_key(row.surface), row.reading): row for row in [*data, *wiki]}
    merged = [combined[key] for key in sorted(combined)]
    args.output.write_text(
        "".join(json.dumps(record(row), ensure_ascii=False) + "\n" for row in merged),
        encoding="utf-8",
    )

    already_present = {
        pair for pair in seed if pair[0] in glossary and pair[1] in glossary[pair[0]][1]
    }
    seed_spelled = {
        pair for pair, surface in seed.items() if is_spelled(surface, pair[1])
    }
    target = seed.keys() - already_present - seed_spelled
    missing = sorted(seed.keys() - combined.keys())
    summary = {
        "latin_glossary_surfaces": len(glossary),
        "inputs": {
            "english_words_sha256": hashlib.sha256(word_data).hexdigest(),
            "glossary_sha256": [
                hashlib.sha256(path.read_bytes()).hexdigest() for path in args.glossary
            ],
            "wikidata_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [*args.wikidata, args.wikidata_excluded]
            },
        },
        "seed_surfaces": len({key for key, _ in seed}),
        "seed_pairs": len(seed),
        "seed_existing_pairs": [
            [seed[pair], pair[1]] for pair in sorted(already_present)
        ],
        "seed_letter_by_letter_pairs": [
            [seed[pair], pair[1]] for pair in sorted(seed_spelled)
        ],
        "seed_target_pairs": len(target),
        "seed_target_surfaces": len({key for key, _ in target}),
        "seed_missing_pairs": [[seed[pair], pair[1]] for pair in missing],
        "Wikipedia-ja": {**describe(wiki, seed), "counts": dict(wiki_counts)},
        "Wikidata": {**describe(data, seed), "counts": dict(data_counts)},
        "combined": {
            **describe(merged, seed),
            "cross_source_duplicates": len(wiki) + len(data) - len(merged),
            "output_by_source": dict(Counter(row.source for row in merged)),
            "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        },
    }
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
