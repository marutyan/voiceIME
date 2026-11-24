"""用語集v2（data/text/glossary-v2.jsonl）を、公開の一覧の種と教師LLMの出力から作る。

段階（手元で実行し、依頼のJSONLを faculty の vLLM へ datagen/text/colab_client.py で送る）：
1. topics-requests（--round 1〜3）：分野ごとに細かい話題を挙げさせる依頼を作る。
2. gen-requests（--round 1〜5）：話題ごとに用語と読みを挙げさせる依頼を作る（回ごとの違いは GEN_ROUNDS）。
3. review-requests（--round 1〜4）：種（seeds.jsonl）とLLMが挙げた語をまとめ、実在、表記、読み、書き方、種類、分野、
   知られている程度を判定させる依頼を作る。各回は前の回までに見直していない候補だけを書く。
4. general-requests：選んだ語の読みが日本語の普通の言葉でもあるかを判定させる依頼を作る（まだ判定していない語だけ）。
5. build：判定の結果から用語を選び、今の用語集（glossary.jsonl）に足して train / held-out に分け、書き出す。

使い方：uv run python datagen/glossary2/glossary2.py <段階> [--round N] [--work <作業ディレクトリ>]
手順と各段階の件数は data/text/README.md の「用語集v2」の節にある。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# 今の用語集の作成と同じ判定（英字の判定、読みの整え方、表記の揺れのキー）を使うため、datagen/text から読み込む。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "text"))
from common import CATEGORIES, DATA_DIR, KATAKANA_USUAL_WORDS, SEED, extract_json, has_latin, parse_items, read_jsonl, write_jsonl  # noqa: E402
from glossary import EXAMPLE_TERMS, YEAR_RE, clean_readings, norm_key  # noqa: E402

from prompts import (  # noqa: E402
    AREAS,
    GEN_SYSTEM,
    GEN_USER,
    GEN_USER_MORE,
    GENERAL_SYSTEM,
    GENERAL_USER,
    N_TERMS_PER_TOPIC,
    N_TOPICS_PER_AREA,
    REVIEW_SYSTEM,
    REVIEW_USER,
    TOPICS_SYSTEM,
    TOPICS_USER,
    TOPICS_USER_MORE,
)
from seeds import MUST_INCLUDE  # noqa: E402

WORK_DIR = DATA_DIR / "work" / "glossary2"
V1_PATH = DATA_DIR / "glossary.jsonl"
V2_PATH = DATA_DIR / "glossary-v2.jsonl"
# 見直しの依頼1件に入れる候補の数。出力が長くなりすぎず、取りこぼしが出にくい大きさにする。
REVIEW_BATCH = 40
# 1語に残す読みの最大数。多すぎる読みは教師LLMの言い換えの水増しが多いため。
MAX_READINGS = 4
# 読みの長さ（カタカナの文字数）の、表記の英数字の数に対する下限。黙字の多い語（Thought → ソート、0.43）より低くする。
MIN_READING_RATIO = 0.35
# 表記として認める最大の長さ。長い句は用語として呼ばれない。
MAX_SURFACE_LEN = 50
# 新しく足した語のうちheld-outにする割合（docs/PLAN.mdの約20%）。
HELD_OUT_RATIO = 0.2
# 用語集の目標の上限（課題の3〜5万語）。超えた分は知られている程度（fame）の低い語から減らす。
MAX_TERMS = 50000
# 文中で普通カタカナで書く語の判定に使う、今の学習文の整形後の文で現れた回数の下限。
KATAKANA_USUAL_MIN_COUNT = 3
# 課題で英字で書く語として名指しされた開発の慣用語。必ず入れる語と同じく、判定に関わらず残す（今の学習文でカタカナで書かれていても残す）。
TASK_NAMED_TERMS = ("pull request", "rebase", "CI/CD")
# 必ず入れる語のうち、教師LLMが読みを付けなかった語や、今の用語集の DETR の読み（ディーイーティーアール）と揃えたい語の読み。
# 教師LLMは DETR を「デター」と読むことが多く、dev-userの確認用の下書きでは「ディーター」と書かれているため、どれも残す。
# Optuna は下書きの「オプチューナ」を、pull request は話し言葉で多い「プルリク」を足す。
MUST_READING_OVERRIDES = {
    "Shadow DETR": ["シャドウデター", "シャドウディーター", "シャドーデター", "シャドウディーイーティーアール"],
    "RT-DETR": ["アールティーデター", "アールティーディーター", "アールティーディーイーティーアール"],
    "Detection Transformer": ["ディテクショントランスフォーマー", "デテクショントランスフォーマー"],
    "Optuna": ["オプチュナ", "オプチューナ"],
    "pull request": ["プルリクエスト", "プルリク"],
}
# 同じ語が複数の出どころから来たとき、表記と分野を採る順（前ほど優先）。
SOURCE_PRIORITY = (
    "must",
    "pwc-methods",
    "llm-gen",
    "pwc-datasets",
    "arxiv",
    "hf-models",
    "hf-datasets",
    "pypi",
    "npm",
    "crates",
    "brew-formula",
    "brew-cask",
    "awesome-ml",
    "awesome-python",
    "awesome-go",
    "awesome-rust",
    "awesome-swift",
)
JAPANESE_RE = re.compile(r"[ぁ-んァ-ヺ一-龯]")


def make_request(rid: str, system: str, user: str, temperature: float, max_tokens: int, seed: int) -> dict:
    """colab_client.py が読む形の依頼を1件作る。"""
    return {
        "id": rid,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
    }


def topics_requests(work: Path, round_: int) -> None:
    """分野ごとに細かい話題を挙げさせる依頼を書く。

    2回目以降は、それより前の回の話題を示し、それと重ならない別の話題を挙げさせる（候補の語数を増やすため）。
    """
    known: dict[str, list[str]] = defaultdict(list)
    for r in range(1, round_):
        for area, topics in load_topics(work, r, by_area=True):
            known[area] += topics
    reqs = []
    for j, area in enumerate(AREAS):
        user = TOPICS_USER.format(n=N_TOPICS_PER_AREA, area=area)
        if round_ >= 2:
            user += TOPICS_USER_MORE.format(known="\n".join(known[area]))
        prefix = "topics" if round_ == 1 else f"topics{round_}"
        reqs.append(make_request(f"{prefix}-{j:03d}", TOPICS_SYSTEM, user, 0.7, 3000, SEED + 100 * round_ + j))
    name = "topics_requests.jsonl" if round_ == 1 else f"topics{round_}_requests.jsonl"
    print(f"wrote {write_jsonl(work / name, reqs)} requests")


def load_topics(work: Path, round_: int, by_area: bool = False) -> list:
    """話題の出力を読み、(分野, 話題) の一覧を返す。by_area なら (分野, 話題の一覧) の一覧を返す。"""
    areas = list(AREAS)
    name = "topics_outputs.jsonl" if round_ == 1 else f"topics{round_}_outputs.jsonl"
    out = []
    for row in sorted(read_jsonl(work / name), key=lambda r: r["id"]):
        area = areas[int(row["id"].split("-")[1])]
        try:
            topics = extract_json(row["text"])
        except ValueError:
            print(f"parse error: {row['id']}")
            continue
        topics = [t.strip() for t in (topics if isinstance(topics, list) else []) if isinstance(t, str) and t.strip()]
        out += [(area, topics)] if by_area else [(area, t) for t in topics]
    return out


# 候補の生成の回ごとの設定：(使う話題の回, その回の話題で既に挙がった語を示すために読む出力。None なら示さない)。
# 1回目だけでは重複が多く語数が足りないため、2回目は同じ話題で1回目に挙がった語を示して別の語を挙げさせ、
# 3回目は別の話題（topics2）について挙げさせ、4回目はその話題で3回目に挙がった語を示して別の語を挙げさせ、
# 5回目はさらに別の話題（topics3）について挙げさせる。
GEN_ROUNDS: dict[int, tuple[int, str | None]] = {
    1: (1, None),
    2: (1, "gen_outputs.jsonl"),
    3: (2, None),
    4: (2, "gen3_outputs.jsonl"),
    5: (3, None),
}


def gen_requests(work: Path, round_: int) -> None:
    """話題ごとに用語と読みを挙げさせる依頼を書く（回ごとの違いは GEN_ROUNDS）。"""
    topics_round, known_file = GEN_ROUNDS[round_]
    known: dict[int, list[str]] = {}
    if known_file:
        for row in read_jsonl(work / known_file):
            known[int(row["id"].split("-")[1])] = [str(it.get("surface", "")) for it in parse_items(row["text"]) if it.get("surface")]
    reqs = []
    for k, (area, topic) in enumerate(load_topics(work, topics_round)):
        user = GEN_USER.format(n=N_TERMS_PER_TOPIC, area=area, topic=topic)
        if known_file:
            user += GEN_USER_MORE.format(known="、".join(known.get(k, [])))
        rid = f"gen-{k:05d}" if round_ == 1 else f"gen{round_}-{k:05d}"
        reqs.append(make_request(rid, GEN_SYSTEM, user, 0.7, 5000, SEED + 10000 * round_ + k))
    name = "gen_requests.jsonl" if round_ == 1 else f"gen{round_}_requests.jsonl"
    print(f"wrote {write_jsonl(work / name, reqs)} requests")


def v1_terms() -> list[dict]:
    """今の用語集（変えずにそのまま含める）を読む。"""
    return list(read_jsonl(V1_PATH))


# 見直しの回ごとの、候補と依頼と出力のファイル名の接尾辞。各回は、それより前の回の後に足した候補だけを見直す。
REVIEW_ROUNDS = ("", "2", "3", "4")


def gen_files(work: Path, kind: str) -> list[Path]:
    """候補の生成の依頼（kind=requests）か出力（kind=outputs）のファイルを、回の順に返す（general_* などは含めない）。"""
    return sorted(p for p in work.glob(f"gen*_{kind}.jsonl") if re.fullmatch(rf"gen\d*_{kind}\.jsonl", p.name))


def collect_candidates(work: Path) -> list[dict]:
    """種とLLMが挙げた語（1回目と2回目）を、表記の揺れで重複を除いてまとめる。今の用語集にある語は除く。"""
    v1_keys = {norm_key(t["surface"]) for t in v1_terms()}
    reqs = {r["id"]: r for p in gen_files(work, "requests") for r in read_jsonl(p)}
    cands: dict[str, dict] = {}
    for s in read_jsonl(work / "seeds.jsonl"):
        key = norm_key(s["term"])
        if s["source"] == "must" or key not in v1_keys:
            cands.setdefault(key, {"term": s["term"], "hint": s["hint"], "source": s["source"], "readings": []})
    n_raw = 0
    rows = [r for p in gen_files(work, "outputs") for r in read_jsonl(p)]
    # 1回目（gen-）を先に、同じ回の中は話題の番号順に読む
    for row in sorted(rows, key=lambda r: (not r["id"].startswith("gen-"), r["id"])):
        topic = reqs[row["id"]]["messages"][1]["content"].split("話題：")[1].split("\n")[0].strip()
        for it in parse_items(row["text"]):
            n_raw += 1
            surface = str(it.get("surface", "")).strip()
            readings = clean_readings(it.get("readings"))
            if not surface or not has_latin(surface) or JAPANESE_RE.search(surface) or not readings:
                continue
            key = norm_key(surface)
            if key in v1_keys:
                continue
            if key in cands:
                cands[key]["readings"] = list(dict.fromkeys(cands[key]["readings"] + readings))
                continue
            cands[key] = {"term": surface, "hint": f"AIが挙げた語（話題：{topic}）", "source": "llm-gen", "readings": readings}
    print(f"llm-gen raw={n_raw} candidates={len(cands)}", Counter(c["source"] for c in cands.values()))
    return list(cands.values())


def review_requests(work: Path, round_: int) -> None:
    """候補を見直しの依頼に分けて書く。依頼の中の番号と候補の対応は candidates{接尾辞}.jsonl の順で決まる。

    2回目以降は、それより前の回に見直した候補に無い候補だけを書く。
    """
    suffix = REVIEW_ROUNDS[round_ - 1]
    cands = collect_candidates(work)
    done = {norm_key(c["term"]) for sfx in REVIEW_ROUNDS[: round_ - 1] for c in read_jsonl(work / f"candidates{sfx}.jsonl")}
    cands = [c for c in cands if norm_key(c["term"]) not in done]
    write_jsonl(work / f"candidates{suffix}.jsonl", cands)
    reqs = []
    for b in range(0, len(cands), REVIEW_BATCH):
        chunk = cands[b : b + REVIEW_BATCH]
        lines = []
        for i, c in enumerate(chunk):
            item = {"i": i, "term": c["term"], "hint": c["hint"]}
            if c["readings"]:
                item["readings"] = c["readings"]
            lines.append(json.dumps(item, ensure_ascii=False))
        rid = f"review{suffix}-{b // REVIEW_BATCH:05d}"
        reqs.append(make_request(rid, REVIEW_SYSTEM, REVIEW_USER.format(items="\n".join(lines)), 0.2, 6000, SEED + 50000 * round_ + len(reqs)))
    print(f"wrote {write_jsonl(work / f'review{suffix}_requests.jsonl', reqs)} requests for {len(cands)} candidates")


def load_reviews(work: Path, stats: Counter[str]) -> list[dict]:
    """見直しの出力を候補と番号で対応させ、判定の付いた候補の一覧を返す。"""
    out = []
    for suffix in REVIEW_ROUNDS:
        if not (work / f"review{suffix}_outputs.jsonl").exists():
            continue
        cands = list(read_jsonl(work / f"candidates{suffix}.jsonl"))
        n_done = 0
        for row in read_jsonl(work / f"review{suffix}_outputs.jsonl"):
            b = int(row["id"].split("-")[1])
            chunk = cands[b * REVIEW_BATCH : (b + 1) * REVIEW_BATCH]
            n_done += len(chunk)
            got = set()
            for it in parse_items(row["text"]):
                i = it.get("i")
                if not isinstance(i, int) or not 0 <= i < len(chunk) or i in got:
                    continue
                got.add(i)
                out.append({**chunk[i], "review": it})
            stats["review_missing"] += len(chunk) - len(got)
        stats["review_request_missing"] += len(cands) - n_done
    return out


def katakana_usual_readings() -> Counter[str]:
    """今の学習文の整形後の文で、カタカナのまま書かれている語とその回数を数える。

    今の整形後の文は「英字で書く語は用語集の英字、それ以外の外来語はカタカナ」で書かれているため、
    ここに何度も出るカタカナ語（データ、モデル、パイプラインなど）は、日本語の文中で普通カタカナで書く語とみなせる。
    """
    counts: Counter[str] = Counter()
    for name in ("train.jsonl", "val.jsonl"):
        for row in read_jsonl(DATA_DIR / name):
            counts.update(re.findall(r"[ァ-ヺー]{2,}", row["target_text"]))
    return counts


def accept(c: dict, stats: Counter[str], katakana_counts: Counter[str], dropped: list[dict]) -> dict | None:
    """判定の付いた候補を、方針に合えば用語の形にして返す。合わなければ理由を数えて None を返す。"""
    rv = c["review"]
    # 必ず入れる語と課題で名指しされた語は、見直しの判定（実在、書き方、種類）に関わらず残し、表記も指定の通りにする。
    # LLMが挙げた候補として先に見直された場合もあるため、出どころではなく表記で判定する。
    must_surfaces = {norm_key(m): m for m in (*MUST_INCLUDE, *TASK_NAMED_TERMS)}
    must = norm_key(c["term"]) in must_surfaces
    surface = must_surfaces[norm_key(c["term"])] if must else str(rv.get("surface") or "").strip()
    # 複数語の名前で、読みを語ごとに分けて書いた出力（例：Multilingual LibriSpeech → ["マルチリンガル", "リブリスピーチ"]）を除くため、
    # 表記の英数字の数に比べて短すぎる読みを捨てる
    n_alnum = sum(ch.isascii() and ch.isalnum() for ch in surface)
    readings = [r for r in clean_readings(rv.get("readings")) if len(r) >= MIN_READING_RATIO * n_alnum][:MAX_READINGS]
    style, kind = rv.get("style"), rv.get("kind")

    def drop(reason: str) -> None:
        stats[f"drop_{reason}"] += 1
        dropped.append({"term": c["term"], "surface": surface, "source": c["source"], "reason": reason, "review": rv})

    if must and surface in MUST_READING_OVERRIDES:
        readings = list(MUST_READING_OVERRIDES[surface])
    if not must and not rv.get("keep", False):
        return drop("not_keep")
    if not readings:
        return drop("no_reading")
    if not must:
        if kind not in ("name", "abbrev", "code", "term"):
            return drop(f"kind_{kind}")
        if style not in ("latin", "either") or (kind == "term" and style != "latin"):
            return drop(f"style_{style}_{kind}")
        if not surface or not has_latin(surface) or JAPANESE_RE.search(surface) or len(surface) > MAX_SURFACE_LEN:
            return drop("bad_surface")
        # モデルやパッケージのID（例：org/name）を名前に直せなかったもの。CI/CD、TCP/IP のような短い組は残す
        if "/" in surface and any(len(p) > 6 for p in surface.split("/")):
            return drop("id_like_surface")
        if YEAR_RE.search(surface):
            return drop("with_year")
        if surface.lower() in KATAKANA_USUAL_WORDS:
            return drop("katakana_usual_word")
        if surface not in TASK_NAMED_TERMS and any(katakana_counts[r] >= KATAKANA_USUAL_MIN_COUNT for r in readings):
            return drop("reading_written_in_katakana")
    category = rv.get("category") if rv.get("category") in CATEGORIES else "ml-research"
    fame = rv.get("fame") if rv.get("fame") in (1, 2, 3) else 3
    return {
        "surface": surface,
        "readings": readings,
        "category": category,
        "style": style if style in ("latin", "either") else "latin",
        "kind": kind if kind in ("name", "abbrev", "code", "term") else "term",
        "fame": fame,
        "source": c["source"],
    }


def word_substrings(surface: str) -> set[str]:
    """表記の中で、前後を英数字に挟まれずに現れる部分文字列をすべて返す（common.surface_pattern と同じ境界）。

    「GPT-4」の中の「GPT」のように、ある用語が別の用語の中に語として現れる関係を、全組を照合せずに求めるために使う。
    """
    alnum = [ch.isascii() and ch.isalnum() for ch in surface]
    n = len(surface)
    starts = [i for i in range(n) if i == 0 or not alnum[i - 1]]
    ends = [j for j in range(1, n + 1) if j == n or not alnum[j]]
    return {surface[i:j] for i in starts for j in ends if i < j and surface[i:j] != surface}


def assign_split(terms: list[dict], new_ids: list[int], rng: random.Random, stats: Counter[str]) -> None:
    """新しく足した語の約20%を、分野ごとに層別してheld-outにする。今の用語集の分割は変えない。

    held-outの語Xが、trainの語の中に語として現れると、trainの文にXが漏れる。そのため
    「held-outの語を含む語はすべてheld-out」になるよう、Xを含む語（その語を含む語も）を一緒にheld-outにする。
    今の用語集のtrainの語や例文の語を含めてしまう候補は、held-outにできないので飛ばす。
    """
    index = {t["surface"]: k for k, t in enumerate(terms)}
    supers: dict[int, list[int]] = defaultdict(list)
    for k, t in enumerate(terms):
        for sub in word_substrings(t["surface"]):
            if sub in index:
                supers[index[sub]].append(k)

    def closure(k: int) -> set[int]:
        seen, stack = {k}, [k]
        while stack:
            for s in supers[stack.pop()]:
                if s not in seen:
                    seen.add(s)
                    stack.append(s)
        return seen

    new_set = set(new_ids)
    for k in new_ids:
        terms[k]["split"] = "train"
    # 今の用語集のheld-outの語を含む新しい語は、held-outにするしかない
    for k, t in enumerate(terms):
        if k not in new_set and t["split"] == "held-out":
            for s in closure(k):
                if s in new_set and terms[s]["split"] != "held-out":
                    terms[s]["split"] = "held-out"
                    stats["held_out_forced_by_v1"] += 1
    protected = set(EXAMPLE_TERMS) | set(MUST_INCLUDE) | set(TASK_NAMED_TERMS)
    for cat in CATEGORIES:
        cat_new = [k for k in new_ids if terms[k]["category"] == cat]
        target = round(len(cat_new) * HELD_OUT_RATIO)
        order = list(cat_new)
        rng.shuffle(order)
        for k in order:
            if sum(1 for j in cat_new if terms[j]["split"] == "held-out") >= target:
                break
            if terms[k]["split"] == "held-out" or terms[k]["surface"] in protected:
                continue
            group = closure(k)
            if any(j not in new_set or terms[j]["surface"] in protected for j in group if terms[j]["split"] != "held-out"):
                stats["held_out_skipped_conflict"] += 1
                continue
            for j in group:
                terms[j]["split"] = "held-out"


def select_new_terms(work: Path, stats: Counter[str]) -> tuple[list[dict], list[dict]]:
    """判定の結果から方針に合う新しい語を選び、表記の揺れでまとめて、(今の用語集, 新しい語) を返す。"""
    katakana_counts = katakana_usual_readings()
    dropped: list[dict] = []
    accepted = [t for c in load_reviews(work, stats) if (t := accept(c, stats, katakana_counts, dropped))]
    write_jsonl(work / "dropped.jsonl", dropped)

    # LLMが表記を直した結果、別の候補や今の用語集と同じ語になったものをまとめる
    v1 = v1_terms()
    v1_keys = {norm_key(t["surface"]) for t in v1}
    merged: dict[str, dict] = {}
    for t in sorted(accepted, key=lambda t: SOURCE_PRIORITY.index(t["source"])):
        key = norm_key(t["surface"])
        if key in v1_keys:
            stats["drop_same_as_v1"] += 1
            continue
        if key in merged:
            m = merged[key]
            # 必ず入れる語は指定した読みを保つため、他の候補の読みを足さない
            if m["source"] != "must":
                m["readings"] = list(dict.fromkeys(m["readings"] + t["readings"]))[:MAX_READINGS]
            m["fame"] = min(m["fame"], t["fame"])
            stats["merged_duplicate"] += 1
            continue
        merged[key] = t
    return v1, list(merged.values())


# 読みが普通の言葉かを判定させる依頼1件に入れる語の数。
GENERAL_BATCH = 50


# 英字と数字を1文字ずつ読んだだけの読み（例：GIL → ジーアイエル、PP → ピーピー）。教師LLMはこの形も「普通の言葉」と判定することがあるが、
# 日本語の会話で別の意味に取り違える恐れは小さいため、読みがすべてこの形の語は普通の言葉の判定で除かない。
SPELLED_OUT_RE = re.compile(
    "^(?:エー|エイ|ビー|シー|ディー|イー|エフ|ジー|エイチ|エッチ|アイ|ジェー|ジェイ|ケー|ケイ|エル|エム|エヌ|オー|ピー|キュー|アール|エス|ティー"
    "|ユー|ブイ|ヴィー|ダブリュー|エックス|ワイ|ゼット|ズィー|ゼロ|ワン|ツー|スリー|フォー|ファイブ|シックス|セブン|エイト|ナイン"
    "|イチ|ニ|サン|ヨン|ゴ|ロク|ナナ|ハチ|キュウ|ジュウ|ヒャク)+$"
)
# 読みが普通の言葉かの判定の回ごとのファイル名の接尾辞。2回目は、1回目の後に足した語だけを判定する。
GENERAL_ROUNDS = ("", "2")


def general_requests(work: Path) -> None:
    """選んだ新しい語と今の用語集の語について、読みが日本語の普通の言葉でもあるかを判定させる依頼を書く。

    パッケージ名には just、all、Click、Rich のように普通の言葉と同じ名前が多く、読み（ジャスト、クリックなど）を
    聞いて英字へ書き換えると関係のない話まで書き換えてしまうため、新しい語からは除く。今の用語集の語は報告だけに使う。
    すでに判定した語は除き、まだ判定していない語だけを次の回の依頼にする。
    """
    judged = load_general(work)
    suffix = next(sfx for sfx in GENERAL_ROUNDS if not (work / f"general{sfx}_outputs.jsonl").exists())
    v1, new_terms = select_new_terms(work, Counter())
    terms = [{"surface": t["surface"], "readings": t["readings"]} for t in v1 + new_terms if t["surface"] not in judged]
    write_jsonl(work / f"general{suffix}_candidates.jsonl", terms)
    reqs = []
    for b in range(0, len(terms), GENERAL_BATCH):
        chunk = terms[b : b + GENERAL_BATCH]
        items = "\n".join(json.dumps({"i": i, **t}, ensure_ascii=False) for i, t in enumerate(chunk))
        rid = f"general{suffix}-{b // GENERAL_BATCH:05d}"
        reqs.append(make_request(rid, GENERAL_SYSTEM, GENERAL_USER.format(items=items), 0.2, 4000, SEED + 200000 + 10000 * len(suffix) + len(reqs)))
    print(f"wrote {write_jsonl(work / f'general{suffix}_requests.jsonl', reqs)} requests for {len(terms)} terms")


def load_general(work: Path) -> dict[str, bool]:
    """読みが普通の言葉かの判定を、表記 → 判定 の辞書で返す。判定の出力が無い語は含めない。"""
    out: dict[str, bool] = {}
    for suffix in GENERAL_ROUNDS:
        if not (work / f"general{suffix}_outputs.jsonl").exists():
            continue
        terms = list(read_jsonl(work / f"general{suffix}_candidates.jsonl"))
        for row in read_jsonl(work / f"general{suffix}_outputs.jsonl"):
            b = int(row["id"].split("-")[1])
            chunk = terms[b * GENERAL_BATCH : (b + 1) * GENERAL_BATCH]
            for it in parse_items(row["text"]):
                i = it.get("i")
                if isinstance(i, int) and 0 <= i < len(chunk) and isinstance(it.get("general"), bool):
                    out[chunk[i]["surface"]] = it["general"]
    return out


def build(work: Path) -> None:
    """判定の結果から新しい語を選び、今の用語集に足して分割し、glossary-v2.jsonl を書く。"""
    stats: Counter[str] = Counter()
    v1, new_terms = select_new_terms(work, stats)
    general = load_general(work)
    stats["general_missing"] = sum(1 for t in new_terms if t["surface"] not in general)
    keep_anyway = set(MUST_INCLUDE) | set(TASK_NAMED_TERMS)
    dropped_general = [
        t for t in new_terms
        if general.get(t["surface"]) and t["surface"] not in keep_anyway and not all(SPELLED_OUT_RE.match(r) for r in t["readings"])
    ]
    stats["drop_general_reading"] = len(dropped_general)
    write_jsonl(work / "dropped_general.jsonl", dropped_general)
    write_jsonl(work / "v1_general_reading.jsonl", [t for t in v1 if general.get(t["surface"])])
    dropped_ids = {id(t) for t in dropped_general}
    new_terms = [t for t in new_terms if id(t) not in dropped_ids]
    missing_must = set(MUST_INCLUDE) - {t["surface"] for t in new_terms} - {t["surface"] for t in v1}
    if missing_must:
        print(f"WARNING: 必ず入れる語が無い：{missing_must}")

    rng = random.Random(SEED)
    budget = MAX_TERMS - len(v1)
    if len(new_terms) > budget:
        # 知られている程度の低い語から、同じ程度の中では無作為に減らす
        rng.shuffle(new_terms)
        new_terms.sort(key=lambda t: (t["source"] != "must", t["fame"]))
        stats["drop_over_budget"] = len(new_terms) - budget
        new_terms = new_terms[:budget]

    new_terms.sort(key=lambda t: (CATEGORIES.index(t["category"]), t["surface"].lower()))
    terms = [dict(t, source="v1") for t in v1] + new_terms
    new_ids = list(range(len(v1), len(terms)))
    assign_split(terms, new_ids, rng, stats)

    fields = ("surface", "readings", "category", "split", "style", "kind", "fame", "source")
    n = write_jsonl(V2_PATH, ({f: t[f] for f in fields if f in t} for t in terms))
    print(f"wrote {n} terms to {V2_PATH}")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    for cat in CATEGORIES:
        c = Counter(t["split"] for t in new_terms if t["category"] == cat)
        print(f"  new {cat}: train={c['train']} held-out={c['held-out']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["topics-requests", "gen-requests", "review-requests", "general-requests", "build"])
    parser.add_argument("--work", type=Path, default=WORK_DIR)
    parser.add_argument("--round", type=int, default=1, choices=[1, 2, 3, 4, 5])
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    if args.stage == "topics-requests":
        topics_requests(args.work, args.round)
    elif args.stage == "gen-requests":
        gen_requests(args.work, args.round)
    elif args.stage == "review-requests":
        review_requests(args.work, args.round)
    elif args.stage == "general-requests":
        general_requests(args.work)
    else:
        build(args.work)


if __name__ == "__main__":
    main()
