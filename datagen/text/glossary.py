"""技術用語の用語集を、教師LLMの出力から作る。

段階（手元で実行し、依頼のJSONLをColabの colab_client.py で処理する）：
1. gen-requests：小分類ごとに用語の候補を出させる依頼を作る。
2. review-requests：候補を重複除去し、読みと表記の扱い（style）を見直させる依頼を作る。
3. build：見直しの結果を検査し、train / held-out に分けて glossary.jsonl を書く。

使い方：uv run python datagen/text/glossary.py <段階> --work <作業ディレクトリ>
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import (
    CATEGORIES,
    KATAKANA_USUAL_WORDS,
    DATA_DIR,
    KATAKANA_READING_RE,
    SEED,
    extract_json,
    has_latin,
    read_jsonl,
    surface_pattern,
    write_jsonl,
)
from glossary_prompts import (
    CLASSIFY_SYSTEM,
    CLASSIFY_USER,
    GEN_SYSTEM,
    GEN_USER,
    GEN_USER_EXCLUDE,
    REVIEW_SYSTEM,
    REVIEW_USER,
    SUBAREAS,
)

# 小分類1つあたりに出させる候補の数。4分野38小分類で約2,700候補になり、重複と除外の後に約1,500語を残す。
N_PER_SUBAREA = 70
# 見直しの依頼1件に入れる候補の数。出力が長くなりすぎず、取りこぼしが出にくい大きさにする。
REVIEW_BATCH = 40
# 種類の判定の依頼1件に入れる候補の数。
CLASSIFY_BATCH = 50
# 用語集に残す語の種類。一般の英単語（common）は日本語の文中ではカタカナで書くのが普通なので除く。
KEEP_KINDS = ("name", "abbrev", "code")
# 年を含む名前（例：KDD 2024）を見つける正規表現。
YEAR_RE = re.compile(r"(?<![0-9])(19|20)[0-9]{2}(?![0-9])")
# 教師LLMが系統的に誤った読みを、目視の点検で見つけて直す置き換え（誤り → 正しい読み）。
READING_FIXES = {"アールシーシーエヌ": "アールシーエヌエヌ"}
# 点検で見つけた個別の読みの誤りと抜けを、用語ごとに置き換える（表記 → 読みのリスト）。
READING_OVERRIDES = {
    "YOLO": ["ヨーロー", "ヨロ"],
    "Slurm": ["スラーム"],
    "TensorRT": ["テンソルアールティー", "テンサーアールティー"],
    "PEFT": ["ペフト", "ピーイーエフティー"],
}
# held-outにする用語の割合（docs/PLAN.mdの約20%）。
HELD_OUT_RATIO = 0.2
# 用語集の目標の語数。これを超えた分は分野ごとの比率を保って無作為に減らす。
MAX_TERMS = 1600
# 文章生成プロンプトの例文に使う用語。例文から書き写されてもheld-outが漏れないよう、必ずtrainに置く。
EXAMPLE_TERMS = ("PyTorch", "DataLoader", "YOLO", "LGTM", "GitHub", "Slack")


def norm_key(surface: str) -> str:
    """表記の揺れ（大文字小文字、空白、ハイフン、点）を無視して同じ用語を見つけるためのキーを作る。"""
    return re.sub(r"[\s\-_.]", "", surface.lower())


def clean_readings(readings: object) -> list[str]:
    """読みの候補からスペースと中黒を除き、カタカナだけの読みを重複なく返す。"""
    if not isinstance(readings, list):
        return []
    out: list[str] = []
    for r in readings:
        if not isinstance(r, str):
            continue
        r = re.sub(r"[\s・･=＝]", "", r)
        if KATAKANA_READING_RE.match(r) and r not in out:
            out.append(r)
    return out


def gen_requests(work: Path, round_: int) -> None:
    """小分類ごとに候補を出させる依頼を作る。

    1回目の候補は有名な語に重なりやすいため、2回目は同じ分野で既に出た語を示し、それ以外の語を出させる。
    """
    known: dict[str, list[str]] = defaultdict(list)
    if round_ == 2:
        for c in collect_candidates(work):
            known[c["category"]].append(c["surface"])
    reqs = []
    for cat in CATEGORIES:
        for j, sub in enumerate(SUBAREAS[cat]):
            user = GEN_USER.format(n=N_PER_SUBAREA, subarea=sub)
            if round_ == 2:
                user += GEN_USER_EXCLUDE.format(known="、".join(known[cat]))
            reqs.append(
                {
                    "id": f"gen{round_}-{cat}-{j:02d}",
                    "messages": [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": user}],
                    "temperature": 0.7,
                    "max_tokens": 6000,
                    "seed": SEED + 1000 * round_ + len(reqs),
                }
            )
    n = write_jsonl(work / f"glossary_gen{round_}_requests.jsonl", reqs)
    print(f"wrote {n} requests")


def collect_candidates(work: Path) -> list[dict]:
    """候補を出させた結果を読み、表記の揺れを除いた候補の一覧を返す。"""
    cands: dict[str, dict] = {}
    n_raw = n_bad = 0
    rows = [r for p in sorted(work.glob("glossary_gen*_outputs.jsonl")) for r in read_jsonl(p)]
    for row in sorted(rows, key=lambda r: r["id"]):
        cat = row["id"].split("-", 1)[1].rsplit("-", 1)[0]
        try:
            items = extract_json(row["text"])
        except ValueError:
            print(f"parse error: {row['id']}")
            continue
        for it in items if isinstance(items, list) else []:
            n_raw += 1
            surface = str(it.get("surface", "")).strip() if isinstance(it, dict) else ""
            readings = clean_readings(it.get("readings")) if isinstance(it, dict) else []
            # 英字を含まない表記（カタカナ語など）は方針により用語集に入れない
            if not surface or not has_latin(surface) or re.search(r"[ぁ-んァ-ヺ一-龯]", surface) or not readings:
                n_bad += 1
                continue
            key = norm_key(surface)
            if key in cands:
                for r in readings:
                    if r not in cands[key]["readings"]:
                        cands[key]["readings"].append(r)
            else:
                cands[key] = {"surface": surface, "readings": readings, "category": cat}
    print(f"raw={n_raw} invalid={n_bad} unique={len(cands)}")
    return list(cands.values())


def review_requests(work: Path) -> None:
    """重複を除いた候補を、見直しの依頼に分けて書く。"""
    cands = collect_candidates(work)
    write_jsonl(work / "glossary_candidates.jsonl", cands)
    reqs = []
    for cat in CATEGORIES:
        group = [c for c in cands if c["category"] == cat]
        for b in range(0, len(group), REVIEW_BATCH):
            chunk = group[b : b + REVIEW_BATCH]
            items = "\n".join(f'{{"surface": "{c["surface"]}", "readings": {c["readings"]}}}' for c in chunk)
            items = items.replace("'", '"')
            reqs.append(
                {
                    "id": f"review-{cat}-{b // REVIEW_BATCH:03d}",
                    "messages": [
                        {"role": "system", "content": REVIEW_SYSTEM},
                        {"role": "user", "content": REVIEW_USER.format(items=items)},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 6000,
                    "seed": SEED + len(reqs),
                }
            )
    n = write_jsonl(work / "glossary_review_requests.jsonl", reqs)
    print(f"wrote {n} review requests")


def assign_split(terms: list[dict], rng: random.Random) -> None:
    """用語を分野ごとに層別して約20%をheld-outにする。

    一方の表記がもう一方の中に語として現れる用語（例：GPTとGPT-4）は同じ組にまとめて同じ側へ置く。
    別々に分けると、trainの文に出したtrainの用語の中にheld-outの用語が現れてしまうため。
    """
    parent = list(range(len(terms)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    pats = [surface_pattern(t["surface"]) for t in terms]
    for i, ti in enumerate(terms):
        for j, tj in enumerate(terms):
            if i != j and pats[i].search(tj["surface"]):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(terms)):
        groups[find(i)].append(i)

    for t in terms:
        t["split"] = "train"
    for cat in CATEGORIES:
        cat_groups = [g for g in groups.values() if terms[g[0]]["category"] == cat]
        cat_groups = [g for g in cat_groups if not any(terms[i]["surface"] in EXAMPLE_TERMS for i in g)]
        rng.shuffle(cat_groups)
        n_cat = sum(1 for t in terms if t["category"] == cat)
        target = round(n_cat * HELD_OUT_RATIO)
        n_held = 0
        for g in cat_groups:
            if n_held >= target:
                break
            for i in g:
                terms[i]["split"] = "held-out"
            n_held += len(g)


def load_reviewed(work: Path, stats: Counter[str]) -> dict[str, dict]:
    """見直しの結果を読み、残す候補（keep、表記と読みが正しく、styleがlatinかeither）を返す。"""
    cands = {norm_key(c["surface"]): c for c in read_jsonl(work / "glossary_candidates.jsonl")}
    reviewed: dict[str, dict] = {}
    seen: set[str] = set()
    for row in sorted(read_jsonl(work / "glossary_review_outputs.jsonl"), key=lambda r: r["id"]):
        cat = row["id"].split("-", 1)[1].rsplit("-", 1)[0]
        try:
            items = extract_json(row["text"])
        except ValueError:
            stats["review_parse_error"] += 1
            continue
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            surface = str(it.get("surface", "")).strip()
            key = norm_key(surface)
            if key not in cands:
                stats["review_unknown_surface"] += 1
                continue
            seen.add(key)
            if not it.get("keep", False):
                stats["drop_not_keep"] += 1
                continue
            style = it.get("style")
            if style == "katakana":
                stats["drop_katakana_style"] += 1
                continue
            if style not in ("latin", "either"):
                stats["drop_bad_style"] += 1
                continue
            readings = clean_readings(it.get("readings"))
            if not readings or not has_latin(surface) or re.search(r"[ぁ-んァ-ヺ一-龯]", surface):
                stats["drop_bad_reading_or_surface"] += 1
                continue
            reviewed[key] = {"surface": surface, "readings": readings, "category": cat, "style": style}
    stats["missing_in_review"] = len(set(cands) - seen)
    return reviewed


def classify_requests(work: Path) -> None:
    """見直しで残った候補について、語の種類と分野を判定させる依頼を書く。"""
    reviewed = list(load_reviewed(work, Counter()).values())
    reqs = []
    for b in range(0, len(reviewed), CLASSIFY_BATCH):
        chunk = reviewed[b : b + CLASSIFY_BATCH]
        items = "\n".join(json.dumps({"surface": t["surface"]}, ensure_ascii=False) for t in chunk)
        reqs.append(
            {
                "id": f"classify-{b // CLASSIFY_BATCH:03d}",
                "messages": [
                    {"role": "system", "content": CLASSIFY_SYSTEM},
                    {"role": "user", "content": CLASSIFY_USER.format(items=items)},
                ],
                "temperature": 0.2,
                "max_tokens": 6000,
                "seed": SEED + 2000 + len(reqs),
            }
        )
    n = write_jsonl(work / "glossary_classify_requests.jsonl", reqs)
    print(f"wrote {n} classify requests for {len(reviewed)} terms")


def build(work: Path) -> None:
    """見直しと種類の判定の結果から用語集を作り、分割して書く。"""
    stats: Counter[str] = Counter()
    reviewed = load_reviewed(work, stats)
    kinds: dict[str, dict] = {}
    for row in read_jsonl(work / "glossary_classify_outputs.jsonl"):
        try:
            items = extract_json(row["text"])
        except ValueError:
            stats["classify_parse_error"] += 1
            continue
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and norm_key(str(it.get("surface", ""))) in reviewed:
                kinds[norm_key(str(it["surface"]))] = it
    dropped_common: list[str] = []
    for key in list(reviewed):
        k = kinds.get(key)
        if k is None:
            stats["drop_missing_in_classify"] += 1
            del reviewed[key]
        elif k.get("kind") not in KEEP_KINDS:
            stats[f"drop_kind_{k.get('kind')}"] += 1
            dropped_common.append(reviewed[key]["surface"])
            del reviewed[key]
        elif YEAR_RE.search(reviewed[key]["surface"]):
            # 「KDD 2024」のように年を付けた名前は、用語として使う場面が限られるため除く
            stats["drop_with_year"] += 1
            del reviewed[key]
        else:
            reviewed[key]["kind"] = k["kind"]
            if reviewed[key]["surface"] in READING_OVERRIDES:
                reviewed[key]["readings"] = list(READING_OVERRIDES[reviewed[key]["surface"]])
            for wrong, right in READING_FIXES.items():
                reviewed[key]["readings"] = list(dict.fromkeys(r.replace(wrong, right) for r in reviewed[key]["readings"]))
            if k.get("category") in CATEGORIES:
                reviewed[key]["category"] = k["category"]
    write_jsonl(work / "glossary_dropped_common.jsonl", [{"surface": s} for s in sorted(dropped_common)])

    # 同じ読みが複数の用語に付くと、読みから表記を決められないため、読みを先に持つ用語へ残す。
    terms = sorted(reviewed.values(), key=lambda t: (CATEGORIES.index(t["category"]), t["surface"].lower()))
    owner: dict[str, str] = {}
    for t in terms:
        kept = []
        for r in t["readings"]:
            if r in owner:
                stats["reading_collision_removed"] += 1
            else:
                owner[r] = t["surface"]
                kept.append(r)
        t["readings"] = kept
    n_before = len(terms)
    terms = [t for t in terms if t["readings"]]
    stats["drop_all_readings_collided"] = n_before - len(terms)

    rng = random.Random(SEED)
    if len(terms) > MAX_TERMS:
        keep_ids: set[int] = set()
        for cat in CATEGORIES:
            idx = [i for i, t in enumerate(terms) if t["category"] == cat]
            k = round(len(idx) * MAX_TERMS / len(terms))
            protected = [i for i in idx if terms[i]["surface"] in EXAMPLE_TERMS]
            rest = [i for i in idx if i not in protected]
            keep_ids.update(protected + rng.sample(rest, max(0, k - len(protected))))
        stats["drop_downsample"] = len(terms) - len(keep_ids)
        terms = [t for i, t in enumerate(terms) if i in keep_ids]

    missing_examples = set(EXAMPLE_TERMS) - {t["surface"] for t in terms}
    if missing_examples:
        print(f"WARNING: 例文の用語が用語集にない：{missing_examples}")
    assign_split(terms, rng)
    # 分割を決めた後に除くので、残りの用語の train / held-out は除く前と変わらない
    dropped_katakana = [t for t in terms if t["surface"] in KATAKANA_USUAL_WORDS]
    terms = [t for t in terms if t["surface"] not in KATAKANA_USUAL_WORDS]
    stats["drop_katakana_usual_word"] = len(dropped_katakana)
    write_jsonl(work / "glossary_dropped_katakana_usual.jsonl", dropped_katakana)
    out = [
        {
            "surface": t["surface"],
            "readings": t["readings"],
            "category": t["category"],
            "split": t["split"],
            "style": t["style"],
            "kind": t["kind"],
        }
        for t in terms
    ]
    n = write_jsonl(DATA_DIR / "glossary.jsonl", out)
    print(f"wrote {n} terms to {DATA_DIR / 'glossary.jsonl'}")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    for cat in CATEGORIES:
        c = Counter(t["split"] for t in out if t["category"] == cat)
        s = Counter(t["style"] for t in out if t["category"] == cat)
        print(f"  {cat}: train={c['train']} held-out={c['held-out']} latin={s['latin']} either={s['either']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["gen-requests", "review-requests", "classify-requests", "build"])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--round", type=int, default=1, choices=[1, 2])
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    if args.stage == "gen-requests":
        gen_requests(args.work, args.round)
    else:
        {"review-requests": review_requests, "classify-requests": classify_requests, "build": build}[args.stage](args.work)


if __name__ == "__main__":
    main()
