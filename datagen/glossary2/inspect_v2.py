"""書き出した用語集v2（data/text/glossary-v2.jsonl）を検査し、音の近い語の一覧と評価データでの被覆を出す。

段階：
- check：表記の重複、空の読み、カタカナ以外の文字を含む読み、一般のカタカナ語の混入、held-outの漏れを数え、
  同じ読みに複数の表記が付く語の一覧（glossary-v2-homophones.jsonl）を書く。目視用に無作為の200語を書く。
- confusables：各語について読みの近い別の語を最大5つ挙げた glossary-v2-confusables.jsonl を書く。
- coverage：test-synth と dev-user の正解文に出る用語のうち、今の用語集と新しい用語集で拾える語の数を数える（評価データは変えない）。

使い方：uv run python datagen/glossary2/inspect_v2.py <段階>
"""

from __future__ import annotations

import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "text"))
from common import DATA_DIR, KATAKANA_READING_RE, KATAKANA_USUAL_WORDS, SEED, read_jsonl, reading_pattern, surface_pattern, write_jsonl  # noqa: E402
from glossary import norm_key  # noqa: E402

from glossary2 import V1_PATH, V2_PATH, WORK_DIR, katakana_usual_readings, word_substrings  # noqa: E402

HOMOPHONES_PATH = DATA_DIR / "glossary-v2-homophones.jsonl"
CONFUSABLES_PATH = DATA_DIR / "glossary-v2-confusables.jsonl"
# 音の近い語として挙げる読みの距離の上限（長い方の読みの長さで割った編集距離）と、1語あたりの最大数。
# 0.45は、6文字の読みで2文字、11文字の読みで4文字までの違い。長い語は近い読みが少ないため、短い語より緩く取り、距離も出力して次の担当が絞れるようにする。
MAX_NORM_DISTANCE = 0.45
MAX_CONFUSABLES = 5
# 目視の点検に使う無作為の語の数（課題の指定）。
N_SAMPLE = 200
# 距離の行列を一度に計算する行数。メモリを抑えるために分ける。
CDIST_CHUNK = 2000


def load_v2() -> list[dict]:
    """用語集v2を読む。"""
    return list(read_jsonl(V2_PATH))


def check() -> None:
    """自動の検査の結果を表示し、同じ読みの語の一覧と目視用の標本を書く。"""
    terms = load_v2()
    v1 = list(read_jsonl(V1_PATH))
    print(f"terms={len(terms)}")
    # 今の用語集の語が、分割も含めてそのまま入っているか
    v2_by_surface = {t["surface"]: t for t in terms}
    changed = [t["surface"] for t in v1 if t["surface"] not in v2_by_surface or v2_by_surface[t["surface"]]["split"] != t["split"]]
    print(f"v1 terms missing or split changed: {len(changed)} {changed[:5]}")

    keys = Counter(norm_key(t["surface"]) for t in terms)
    print(f"duplicate surfaces (norm_key): {sum(1 for v in keys.values() if v > 1)}")
    print(f"exact duplicate surfaces: {sum(1 for v in Counter(t['surface'] for t in terms).values() if v > 1)}")
    print(f"empty readings: {sum(1 for t in terms if not t['readings'])}")
    bad = [(t["surface"], r) for t in terms for r in t["readings"] if not KATAKANA_READING_RE.match(r)]
    print(f"readings with non-katakana chars: {len(bad)} {bad[:5]}")
    print(f"katakana-usual words (予約語など49語): {sum(1 for t in terms if t['surface'].lower() in KATAKANA_USUAL_WORDS)}")
    # 今の学習文の整形後の文でカタカナのまま書かれている語と同じ読みを持つ語（一般のカタカナ語の混入の疑い）
    kc = katakana_usual_readings()
    mixed = [(t["surface"], r, kc[r], t.get("source")) for t in terms for r in t["readings"] if kc[r] >= 3]
    print(f"readings that appear as katakana words in train/val targets (>=3 times): {len(mixed)} {mixed[:10]}")

    # held-outの語が、trainの語の中に語として現れないか（trainの文への漏れ）
    split = {t["surface"]: t["split"] for t in terms}
    leaks = [(t["surface"], s) for t in terms if t["split"] == "train" for s in word_substrings(t["surface"]) if split.get(s) == "held-out"]
    print(f"held-out surfaces inside train surfaces: {len(leaks)} {leaks[:5]}")

    owners: dict[str, list[str]] = defaultdict(list)
    for t in terms:
        for r in t["readings"]:
            owners[r].append(t["surface"])
    homo = [{"reading": r, "surfaces": s} for r, s in sorted(owners.items()) if len(s) > 1]
    write_jsonl(HOMOPHONES_PATH, homo)
    n_terms_homo = len({s for h in homo for s in h["surfaces"]})
    print(f"homophone readings: {len(homo)} (terms involved: {n_terms_homo}) -> {HOMOPHONES_PATH}")

    new = [t for t in terms if t.get("source") != "v1"]
    sample = random.Random(SEED).sample(new, N_SAMPLE)
    write_jsonl(WORK_DIR / "sample200.jsonl", sample)
    print(f"wrote sample of {len(sample)} new terms -> {WORK_DIR / 'sample200.jsonl'}")
    by = Counter((t["category"], t["split"]) for t in terms)
    print("category/split:", sorted(by.items()))
    print("source:", Counter(t.get("source") for t in terms).most_common())
    print("kind:", Counter(t.get("kind") for t in terms).most_common(), "style:", Counter(t.get("style") for t in terms).most_common())


def related(a: str, b: str) -> bool:
    """2つの表記が同じ系統の語か（一方が他方を語として含む、または3文字以上の語を共有する）を返す。

    次の担当が「音は近いが無関係な語」を選ぶとき、GPT-4とGPT-4oのような同じ系統の語を見分けられるようにする。
    """
    if a in word_substrings(b) or b in word_substrings(a):
        return True
    ta = {w.lower() for w in re.split(r"[^A-Za-z0-9]+", a) if len(w) >= 3}
    tb = {w.lower() for w in re.split(r"[^A-Za-z0-9]+", b) if len(w) >= 3}
    return bool(ta & tb)


def confusables() -> None:
    """各語について、読みの編集距離が近い別の語を最大5つ挙げて書く。"""
    terms = load_v2()
    readings = [(k, r) for k, t in enumerate(terms) for r in t["readings"]]
    strs = [r for _, r in readings]
    owner = [k for k, _ in readings]
    # best[k] = {別の語の番号: (距離, 自分の読み, 相手の読み)}
    best: list[dict[int, tuple[float, str, str]]] = [dict() for _ in terms]
    for start in range(0, len(strs), CDIST_CHUNK):
        block = strs[start : start + CDIST_CHUNK]
        # 行：この塊の読み、列：すべての読み。距離は長い方の長さで割った編集距離（0〜1）
        dist = cdist(block, strs, scorer=Levenshtein.normalized_distance, score_cutoff=MAX_NORM_DISTANCE, workers=-1)
        for bi in range(len(block)):
            i = start + bi
            row = dist[bi]
            for j in (row <= MAX_NORM_DISTANCE).nonzero()[0]:
                kj = owner[j]
                if kj == owner[i]:
                    continue
                d = float(row[j])
                cur = best[owner[i]].get(kj)
                if cur is None or d < cur[0]:
                    best[owner[i]][kj] = (d, strs[i], strs[j])
        print(f"  {min(start + CDIST_CHUNK, len(strs))}/{len(strs)} readings", flush=True)
    rows = []
    n_with = 0
    for k, t in enumerate(terms):
        near = sorted(best[k].items(), key=lambda kv: (kv[1][0], terms[kv[0]]["surface"]))[:MAX_CONFUSABLES]
        n_with += bool(near)
        rows.append(
            {
                "surface": t["surface"],
                "split": t["split"],
                "confusables": [
                    {
                        "surface": terms[j]["surface"],
                        "split": terms[j]["split"],
                        "reading": rj,
                        "own_reading": ri,
                        "distance": round(d, 3),
                        "related": related(t["surface"], terms[j]["surface"]),
                    }
                    for j, (d, ri, rj) in near
                ],
            }
        )
    write_jsonl(CONFUSABLES_PATH, rows)
    print(f"wrote {len(rows)} rows ({n_with} with >=1 confusable) -> {CONFUSABLES_PATH}")


def coverage() -> None:
    """test-synth と dev-user の正解文に現れる用語を、今の用語集と新しい用語集で数える。"""
    terms = load_v2()
    v1_surfaces = {t["surface"] for t in read_jsonl(V1_PATH)}
    sets = {
        "test-synth": [r["target_text"] for r in read_jsonl(DATA_DIR / "test-synth.jsonl")],
        "dev-user": [r["target_text"] for r in read_jsonl(DATA_DIR.parent / "dev-user" / "manifest.jsonl")],
    }
    for name, texts in sets.items():
        found: Counter[str] = Counter()
        for text in texts:
            hits = [t for t in terms if t["surface"] in text and surface_pattern(t["surface"]).search(text)]
            # 「Deformable DETR」の中の「DETR」のように、長い語の一部として一致したものは数えない
            longer = [h["surface"] for h in hits]
            for h in hits:
                if not any(h["surface"] != o and h["surface"] in word_substrings(o) and o in text for o in longer):
                    found[h["surface"]] += 1
        new = {s: n for s, n in found.items() if s not in v1_surfaces}
        split = {t["surface"]: t["split"] for t in terms}
        latin_tokens = Counter(m for text in texts for m in re.findall(r"[A-Za-z][A-Za-z0-9.+#\-]*(?: [A-Z][A-Za-z0-9.+#\-]*)*", text))
        covered = {s for s in found}
        uncovered = {w: n for w, n in latin_tokens.items() if not any(w == s or w in s or s in w for s in covered)}
        print(f"== {name}: {len(texts)} texts")
        print(f"  v1 terms in targets: {sum(n for s, n in found.items() if s in v1_surfaces)} occurrences, {sum(1 for s in found if s in v1_surfaces)} distinct")
        print(f"  newly covered by v2: {sum(new.values())} occurrences, {len(new)} distinct "
              f"(train {sum(1 for s in new if split[s] == 'train')}, held-out {sum(1 for s in new if split[s] == 'held-out')})")
        print(f"  new terms: {sorted(new.items(), key=lambda kv: -kv[1])}")
        print(f"  latin tokens still not covered ({len(uncovered)} distinct): {sorted(uncovered.items(), key=lambda kv: -kv[1])[:60]}")
    review_coverage(terms, v1_surfaces)


def review_coverage(terms: list[dict], v1_surfaces: set[str]) -> None:
    """dev-userの自由発話（正解文は本人の確認待ちで空）について、確認用の下書き（review.md）で数える。

    - 本人用に足す候補の語（「追加する用語」の欄）が、今の用語集と新しい用語集にあるか。
    - 下書きの spoken_text（話した通りの文。用語はカタカナか英字）に、用語集の表記か読みが何回現れるか。
    """
    text = (DATA_DIR.parent / "dev-user" / "review.md").read_text()
    block = text.split("## 追加する用語", 1)[1].split("```text", 1)[1].split("```", 1)[0]
    wanted = [line.lstrip("# ").split(" = ")[0].strip() for line in block.splitlines() if " = " in line]
    v2 = {t["surface"]: t for t in terms}
    v2_lower = {s.lower(): s for s in v2}
    print(f"== dev-user review.md の追加候補 {len(wanted)}語")
    for w in wanted:
        hit = v2.get(w) or v2.get(v2_lower.get(w.lower(), ""))
        where = "v1" if hit and hit["surface"] in v1_surfaces else ("v2-new " + hit["split"] if hit else "なし")
        print(f"  {w}: {where}" + (f"（表記 {hit['surface']}、読み {hit['readings']}）" if hit else ""))
    spoken = []
    for sec in text.split("\n## dev-user-f")[1:]:
        m = re.search(r"spoken_text:\n```text\n(.*?)\n```", sec, re.S)
        if m:
            spoken.append(m.group(1))
    found_v1: Counter[str] = Counter()
    found_new: Counter[str] = Counter()
    for sp in spoken:
        hits = []
        for t in terms:
            # 下書きでは英字で書いた語もあるため、表記の一致も数える
            if len(t["surface"]) >= 2 and t["surface"] in sp and surface_pattern(t["surface"]).search(sp):
                hits.append(t["surface"])
            elif any(len(r) >= 3 and r in sp and reading_pattern(r).search(sp) for r in t["readings"]):
                hits.append(t["surface"])
        for h in hits:
            # 「num_workers」の中の「num」のように、同じ文で一致した長い語の一部は数えない
            if not any(h != o and h in word_substrings(o) for o in hits):
                (found_v1 if h in v1_surfaces else found_new)[h] += 1
    print(f"== dev-user 自由発話の下書き {len(spoken)}件の spoken_text に現れる用語（表記、または3文字以上の読み）")
    print(f"  v1: {sum(found_v1.values())}回 {len(found_v1)}語 {sorted(found_v1.items(), key=lambda kv: -kv[1])[:40]}")
    print(f"  v2で新しく足した語: {sum(found_new.values())}回 {len(found_new)}語 {sorted(found_new.items(), key=lambda kv: -kv[1])[:80]}")


if __name__ == "__main__":
    {"check": check, "confusables": confusables, "coverage": coverage}[sys.argv[1]]()
