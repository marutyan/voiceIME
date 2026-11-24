"""話し言葉と整形後の文の組（train / val / test-synth）を、教師LLMの出力から作る。

段階（手元で実行し、依頼のJSONLをColabの colab_client.py で処理する）：
1. requests：集合ごとに条件（用途、長さ、フィラーの量、用語など）を無作為に決め、依頼を書く。
2. build：教師LLMの出力を検査し、用語集の無関係な語を混ぜ、件数をそろえて書き出す。

使い方：
  uv run python datagen/text/sentences.py requests --split test --n 1300 --work <作業ディレクトリ>
  uv run python datagen/text/sentences.py build --work <作業ディレクトリ> --out-dir <出力先> [--pilot 200]
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from checks import Glossary, Reject, convert, is_no_change, render_spoken, repair_target, untag_katakana_words
from common import CATEGORIES, DATA_DIR, SEED, parse_items, read_jsonl, reading_pattern, write_jsonl
from sentence_prompts import (
    ENGLISH_PHRASES,
    JUDGE_SYSTEM,
    JUDGE_USER,
    RESTATEMENT_MARKERS,
    SYSTEM,
    TONES,
    TOPIC_HINTS,
    USECASES,
    USER_HEADER,
    render_item,
)

# 依頼1件にまとめる条件の数。システムプロンプトの読み込みを減らしつつ、1件の失敗で失う量を抑える。
ITEMS_PER_REQUEST = 8
# 書き出す集合での上限の割合。課題の目安（用語なし約15%、no_change約10%）に合わせる。
MAX_ZERO_TERMS_RATIO = 0.15
MAX_NO_CHANGE_RATIO = 0.10
# 判定の依頼1件にまとめる組の数。
JUDGE_BATCH = 10
# 各集合で最終的に残す件数（課題の指定）。
FINAL_COUNTS = {"train": 40000, "val": 2000, "test": 1000}
# test-synthのうちheld-outの用語を含める割合（課題の指定は約30%）。
TEST_HELD_OUT_RATIO = 0.30
# 出力の集合名。test は docs/PLAN.md の集合名 test-synth として書く。
SPLIT_NAMES = {"train": "train", "val": "val", "test": "test-synth"}
# 推論時の用語集に無関係な語が入る状況を学習させるため、各行に混ぜる無関係な用語の数の範囲。
MAX_DISTRACTORS = 10

# 条件の分布。課題の割合（用語なし約15%、no_change約10%、instruction_like約10%）に合わせる。
P_NO_CHANGE = 0.10
P_INSTRUCTION = 0.12  # no_change以外の中での割合。全体では約11%になる。
P_ZERO_TERMS = 0.08  # no_changeとinstruction_like以外の中での割合。no_changeと合わせて全体の約17%になる。
N_TERMS_WEIGHTS = {1: 0.45, 2: 0.33, 3: 0.15, 4: 0.07}
# testで用語を含む文のうちheld-outを入れる割合。用語を含む文は約83%なので、全体では約33%になる。
P_HELD_OUT_IN_TEST = 0.40
LENGTH_WEIGHTS = {"short": 0.3, "medium": 0.4, "long": 0.3}
FILLER_WEIGHTS = {"none": 0.2, "few": 0.3, "normal": 0.3, "many": 0.2}
P_RESTATEMENT, P_DISFLUENCY, P_ENUMERATION, P_NUMBERS, P_ENGLISH = 0.35, 0.30, 0.12, 0.25, 0.12
# 用語を選ぶとき、主な分野とは別の分野から1語混ぜる確率。
P_OTHER_CATEGORY = 0.1
# 依頼の形の発話に使う用途の比率。AIへの指示はすべて依頼の形として扱う。
INSTRUCTION_USECASES = {"ai-instruction": 0.7, "chat": 0.15, "email": 0.1, "smalltalk": 0.05}
FREE_USECASES = [u for u in USECASES if u != "ai-instruction"]
# 技術の話題でなくてもよい用途。用語を含まない文で、日常の話題（domain=general）を選んでよい用途。
GENERAL_USECASES = {"chat", "email", "smalltalk"}


class Deck:
    """用語を偏りなく使うため、一巡するまで同じ用語を引かない山札。"""

    def __init__(self, items: list[dict], rng: random.Random) -> None:
        self.items, self.rng, self.pile = list(items), rng, []

    def draw(self, exclude: set[str]) -> dict | None:
        """exclude に無い用語を1つ引く。引ける用語が無ければNoneを返す。"""
        if not self.items:
            return None
        for _ in range(len(self.items) + 1):
            if not self.pile:
                self.pile = list(self.items)
                self.rng.shuffle(self.pile)
            t = self.pile.pop()
            if t["surface"] not in exclude:
                return t
        return None


def pick(rng: random.Random, weights: dict) -> object:
    """重み付きの辞書から1つ選ぶ。"""
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def load_glossary() -> list[dict]:
    """書き出し済みの用語集（data/text/glossary.jsonl）を読む。"""
    return list(read_jsonl(DATA_DIR / "glossary.jsonl"))


def make_specs(split: str, n: int, rows: list[dict], rng: random.Random) -> list[dict]:
    """集合1つ分の条件をn件、無作為に作る。train / val はtrainの用語だけを使う。"""
    train_decks = {c: Deck([r for r in rows if r["split"] == "train" and r["category"] == c], rng) for c in CATEGORIES}
    held_decks = {c: Deck([r for r in rows if r["split"] == "held-out" and r["category"] == c], rng) for c in CATEGORIES}
    cat_weights = {c: len(train_decks[c].items) for c in CATEGORIES}
    specs = []
    for k in range(n):
        no_change = rng.random() < P_NO_CHANGE
        instruction = not no_change and rng.random() < P_INSTRUCTION
        zero_terms = no_change or (not instruction and rng.random() < P_ZERO_TERMS)
        usecase = pick(rng, INSTRUCTION_USECASES) if instruction else rng.choice(FREE_USECASES)
        if zero_terms and usecase in GENERAL_USECASES:
            domain = "general" if rng.random() < 0.6 else pick(rng, cat_weights)
        else:
            domain = pick(rng, cat_weights)
        length = pick(rng, LENGTH_WEIGHTS) if usecase != "commit-message" else pick(rng, {"short": 0.5, "medium": 0.4, "long": 0.1})
        enumeration = not no_change and rng.random() < P_ENUMERATION
        if enumeration and length == "short":
            length = "medium"

        terms: list[dict] = []
        if not zero_terms:
            n_terms = pick(rng, N_TERMS_WEIGHTS)
            use_held = split == "test" and rng.random() < P_HELD_OUT_IN_TEST
            used: set[str] = set()
            for j in range(n_terms):
                cat = domain if rng.random() >= P_OTHER_CATEGORY else pick(rng, cat_weights)
                held = use_held and (j == 0 or rng.random() < 0.5)
                deck = (held_decks if held else train_decks)[cat]
                t = deck.draw(used)
                if t is None:
                    continue
                used.add(t["surface"])
                terms.append({"surface": t["surface"], "reading": rng.choice(t["readings"])})

        specs.append(
            {
                "spec_id": f"{split}-{k:06d}",
                "split": split,
                "usecase": usecase,
                "domain": domain,
                "topic": rng.choice(TOPIC_HINTS[domain]),
                "tone": rng.choice(TONES[usecase]),
                "length": length,
                "no_change": no_change,
                "instruction_like": instruction,
                "filler_level": "none" if no_change else pick(rng, FILLER_WEIGHTS),
                "restatement": None if no_change or rng.random() >= P_RESTATEMENT else rng.choice(RESTATEMENT_MARKERS),
                "disfluency": not no_change and rng.random() < P_DISFLUENCY,
                "enumeration": enumeration,
                "numbers": rng.random() < P_NUMBERS,
                "english_phrase": rng.choice(ENGLISH_PHRASES) if not no_change and rng.random() < P_ENGLISH else None,
                "terms": terms,
            }
        )
    return specs


def requests(split: str, n: int, work: Path, offset: int) -> None:
    """条件を作り、条件の一覧と教師LLMへの依頼を書く。offsetは追加生成で条件の番号と乱数を変えるために使う。"""
    rows = load_glossary()
    # 集合ごと、追加生成ごとに乱数の系列を分ける（seed 0を起点に決定的にする）
    rng = random.Random(f"{SEED}-{split}-{offset}")
    specs = make_specs(split, n, rows, rng)
    for s in specs:
        k = int(s["spec_id"].rsplit("-", 1)[1]) + offset
        s["spec_id"] = f"{split}-{k:06d}"
    reqs = []
    for b in range(0, len(specs), ITEMS_PER_REQUEST):
        chunk = specs[b : b + ITEMS_PER_REQUEST]
        user = USER_HEADER.format(n=len(chunk)) + "\n".join(render_item(i + 1, s) for i, s in enumerate(chunk))
        reqs.append(
            {
                "id": "req-" + chunk[0]["spec_id"],
                "spec_ids": [s["spec_id"] for s in chunk],
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                # 通常の出力は約1,700トークン。繰り返しが止まらない出力に時間を使わないよう上限を抑える
                "max_tokens": 4000,
                "seed": SEED + int(chunk[0]["spec_id"].rsplit("-", 1)[1]) + {"train": 0, "val": 10**7, "test": 2 * 10**7}[split],
            }
        )
    tag = f"{split}-{offset:06d}"
    write_jsonl(work / f"specs-{tag}.jsonl", specs)
    write_jsonl(work / f"requests-{tag}.jsonl", reqs)
    print(f"wrote {len(specs)} specs, {len(reqs)} requests ({tag})")


def add_distractors(rec: dict, spec_id: str, pool: list[dict], terms_by_surface: dict[str, dict]) -> list[dict]:
    """文に出てくる用語に、文に出てこない用語を0〜10個混ぜた用語集を返す。

    混ぜる語は、読みが話し言葉に現れない語に限る（現れると、正解と用語集が食い違うため）。
    """
    rng = random.Random(f"{SEED}-distractor-{spec_id}")
    k = rng.randint(0, MAX_DISTRACTORS)
    chosen = list(rec["spoken_terms"])
    for _ in range(k * 5):
        if len(chosen) >= len(rec["spoken_terms"]) + k:
            break
        t = rng.choice(pool)
        if t["surface"] in chosen:
            continue
        if any(reading_pattern(r).search(rec["spoken_text_kana"]) for r in t["readings"]):
            continue
        chosen.append(t["surface"])
    rng.shuffle(chosen)
    return [{"surface": s, "readings": terms_by_surface[s]["readings"]} for s in chosen]


def collect(work: Path, splits: list[str], gl: Glossary) -> tuple[dict, dict, list]:
    """教師LLMの出力を自動で検査して行に変換し、重複を除いた集合ごとの一覧、理由ごとの件数、捨てた組を返す。"""
    specs = {s["spec_id"]: s for p in sorted(work.glob("specs-*.jsonl")) for s in read_jsonl(p)}
    outputs = {o["id"]: o for p in sorted(work.glob("outputs-*.jsonl")) for o in read_jsonl(p)}
    reqs = {r["id"]: r for p in sorted(work.glob("requests-*.jsonl")) for r in read_jsonl(p)}

    stats: dict[str, Counter[str]] = {s: Counter() for s in ("train", "val", "test")}
    accepted: dict[str, list[dict]] = {s: [] for s in ("train", "val", "test")}
    rejects: list[dict] = []
    for rid in sorted(reqs):
        req = reqs[rid]
        split = specs[req["spec_ids"][0]]["split"]
        if split not in splits:
            continue
        st = stats[split]
        if rid not in outputs:
            st["not_generated"] += len(req["spec_ids"])
            continue
        out = outputs[rid]
        by_i = {it.get("i"): it for it in parse_items(out["text"]) if "spoken" in it and "target" in it}
        for i, sid in enumerate(req["spec_ids"], start=1):
            st["total"] += 1
            spec = specs[sid]
            it = by_i.get(i)
            if it is None:
                # 出力が長さの上限で切れた、またはJSONが壊れていて読めなかった
                st["unparsable_or_missing_item"] += 1
                continue
            try:
                rec = convert(spec, it.get("spoken"), it.get("target"), gl, it.get("dropped", ""))
            except Reject as e:
                st[str(e)] += 1
                rejects.append(
                    {"spec_id": sid, "reason": str(e), "spoken": it.get("spoken"), "dropped": it.get("dropped"), "target": it.get("target")}
                )
                continue
            rec["spec"] = spec
            accepted[split].append(rec)

    # 同じ文が複数の集合へ入らないよう、test、val、trainの順に重複を除く
    seen: set[str] = set()
    for split in ("test", "val", "train"):
        kept = []
        for rec in accepted[split]:
            keys = {rec["target_text"], rec["spoken_text_kana"]}
            if keys & seen:
                stats[split]["duplicate"] += 1
                continue
            seen |= keys
            kept.append(rec)
        accepted[split] = sorted(kept, key=lambda r: r["spec"]["spec_id"])
    return accepted, stats, rejects


def capped_select(recs: list[dict], n: int, n_total: int) -> list[dict]:
    """条件の順に n 件を選ぶ。用語なしと無変更の文が課題の割合を超えないよう、超える分は後回しにする。

    n_total は割合の分母（集合全体の件数）。上限を守ると n 件に足りない場合だけ、後回しにした文で補う。
    """
    max_no_change, max_zero = round(n_total * MAX_NO_CHANGE_RATIO), round(n_total * MAX_ZERO_TERMS_RATIO)
    out, deferred = [], []
    n_nc = n_zero = 0
    for r in recs:
        if len(out) >= n:
            break
        is_nc, is_zero = "no_change" in r["tags"], not r["terms"]
        if (is_nc and n_nc >= max_no_change) or (is_zero and n_zero >= max_zero):
            deferred.append(r)
            continue
        out.append(r)
        n_nc += is_nc
        n_zero += is_zero
    out += deferred[: max(0, n - len(out))]
    return sorted(out, key=lambda r: r["spec"]["spec_id"])


def judge_requests(work: Path, splits: list[str]) -> None:
    """自動の検査を通った組について、教師LLMに規則を守っているかを判定させる依頼を書く。"""
    gl = Glossary.from_rows(load_glossary())
    accepted, _, _ = collect(work, splits, gl)
    # 判定済みの組は依頼し直さない（検査を直して新たに通った組だけを追加で判定する）
    judged = load_judgments(work)
    recs = [r for split in splits for r in accepted[split] if r["spec"]["spec_id"] not in judged]
    reqs = []
    for b in range(0, len(recs), JUDGE_BATCH):
        chunk = recs[b : b + JUDGE_BATCH]
        items = "\n".join(
            json.dumps({"i": i + 1, "spoken": r["spoken_marked"], "dropped": r["dropped"], "target": r["target_text"]}, ensure_ascii=False)
            for i, r in enumerate(chunk)
        )
        reqs.append(
            {
                "id": "judge-" + chunk[0]["spec"]["spec_id"],
                "spec_ids": [r["spec"]["spec_id"] for r in chunk],
                "messages": [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": JUDGE_USER.format(items=items)}],
                "temperature": 0.0,
                "max_tokens": 2000,
                "seed": SEED,
            }
        )
    tag = "-".join(splits) + f"-{len(list(work.glob('judge-requests-*.jsonl'))):02d}"
    n = write_jsonl(work / f"judge-requests-{tag}.jsonl", reqs)
    print(f"wrote {n} judge requests for {len(recs)} items")


def load_judgments(work: Path) -> dict[str, dict]:
    """判定の出力を読み、spec_idごとの判定（ok と理由）を返す。読めなかった組は含めない。"""
    reqs = {r["id"]: r for p in sorted(work.glob("judge-requests-*.jsonl")) for r in read_jsonl(p)}
    out: dict[str, dict] = {}
    for p in sorted(work.glob("judge-outputs-*.jsonl")):
        for o in read_jsonl(p):
            by_i = {it.get("i"): it for it in parse_items(o["text"]) if "ok" in it}
            for i, sid in enumerate(reqs[o["id"]]["spec_ids"], start=1):
                if i in by_i:
                    out[sid] = by_i[i]
    return out


def build(work: Path, out_dir: Path, pilot: int, splits: list[str], write: list[str]) -> None:
    """検査と判定を通った組を、集合ごとに件数をそろえて書き出す。

    splits の集合はすべて重複除去の対象にし、write に含む集合だけを書き出す（既に渡したファイルを保つため）。
    """
    rows = load_glossary()
    gl = Glossary.from_rows(rows)
    by_surface = {r["surface"]: r for r in rows}
    held_surfaces = {r["surface"] for r in rows if r["split"] == "held-out"}
    pools = {"train": [r for r in rows if r["split"] == "train"], "test": rows}
    pools["val"] = pools["train"]
    accepted, stats, rejects = collect(work, splits, gl)

    # 教師LLMの判定でngの組と、判定が得られなかった組を捨てる
    judgments = load_judgments(work)
    judge_rejects = []
    for split in splits:
        kept = []
        for rec in accepted[split]:
            j = judgments.get(rec["spec"]["spec_id"])
            if j is None:
                stats[split]["judge_missing"] += 1
            elif j.get("ok") is not True:
                stats[split]["judge_ng"] += 1
                judge_rejects.append({"spec_id": rec["spec"]["spec_id"], "reason": j.get("reason"), "spoken": rec["spoken_marked"],
                                      "dropped": rec["dropped"], "target": rec["target_text"]})
            else:
                kept.append(rec)
        accepted[split] = kept
    write_jsonl(work / "judge_rejects.jsonl", judge_rejects)

    for split in [s for s in splits if s in write]:
        recs = accepted[split]
        n_final = FINAL_COUNTS[split]
        if split == "test":
            n_held = round(n_final * TEST_HELD_OUT_RATIO)
            held = [r for r in recs if set(r["terms"]) & held_surfaces]
            other = capped_select([r for r in recs if not set(r["terms"]) & held_surfaces], n_final - n_held, n_final)
            # パイロット（先頭の pilot 件）にも約30%のheld-outが入るよう、両方から同じ比率で先頭に置く
            n_pilot_held = round(pilot * TEST_HELD_OUT_RATIO) if pilot else 0
            head = held[:n_pilot_held] + other[: pilot - n_pilot_held] if pilot else []
            tail = held[n_pilot_held:n_held] + other[pilot - n_pilot_held : FINAL_COUNTS["test"] - n_held]
            recs = head + tail
            if len(held) < n_held or len(other) < FINAL_COUNTS["test"] - n_held:
                print(f"WARNING: test-synthが足りない held={len(held)} other={len(other)}")
        else:
            if len(recs) < FINAL_COUNTS[split]:
                print(f"WARNING: {split}が足りない {len(recs)} < {FINAL_COUNTS[split]}")
            recs = capped_select(recs, n_final, n_final)
        stats[split]["surplus_not_used"] = len(accepted[split]) - len(recs)

        name = SPLIT_NAMES[split]
        out_rows = []
        for n, rec in enumerate(recs, start=1):
            spec = rec.pop("spec")
            rid = f"synth-{split}-{n:06d}"
            out_rows.append(
                {
                    "id": rid,
                    "split": name,
                    "spoken_text": rec["spoken_text"],
                    "spoken_text_kana": rec["spoken_text_kana"],
                    "spoken_text_mixed": rec["spoken_text_mixed"],
                    "target_text": rec["target_text"],
                    "terms": rec["terms"],
                    "glossary": add_distractors(rec, spec["spec_id"], pools[split], by_surface),
                    "source": "synthetic-tts",
                    "domain": spec["domain"],
                    "fillers": rec["fillers"],
                    "tags": rec["tags"],
                    "usecase": spec["usecase"],
                    "spoken_marked": rec["spoken_marked"],
                    "est_seconds": rec["est_seconds"],
                    "gen_id": spec["spec_id"],
                }
            )
        write_jsonl(out_dir / f"{name}.jsonl", out_rows)
        if split == "test" and pilot:
            write_jsonl(out_dir / "pilot.jsonl", out_rows[:pilot])
        print(f"== {name}: wrote {len(out_rows)}")
        for k, v in sorted(stats[split].items(), key=lambda kv: -kv[1]):
            print(f"  {k}: {v}")
    write_jsonl(work / "build_stats.jsonl", [{"split": s, **stats[s]} for s in splits])
    write_jsonl(work / "rejects.jsonl", rejects)


def apply_glossary_policy(path: Path) -> None:
    """書き出し済みの行に、用語集から除いた一般語の扱い（checks.untag_katakana_words）と空白の修復をかける。

    行を選び直さないので、id と読み上げ用の文（spoken_text_kana）は変わらない。用語集の方針を後から
    変えたときに、既に他の担当へ渡した test-synth と pilot の id を保つために使う。
    """
    surfaces = {r["surface"] for r in load_glossary()}
    rows = list(read_jsonl(path))
    n_changed = 0
    for row in rows:
        marked, _, target = untag_katakana_words(row["spoken_marked"], "", row["target_text"])
        target = repair_target(target)
        kana, mixed = render_spoken(marked)
        assert kana == row["spoken_text_kana"], row["id"]
        tags = [t for t in row["tags"] if t != "no_change"]
        if is_no_change(kana, target):
            tags.insert(0, "no_change")
        new = dict(
            row,
            spoken_marked=marked,
            spoken_text_mixed=mixed,
            target_text=target,
            terms=[t for t in row["terms"] if t in surfaces],
            glossary=[g for g in row["glossary"] if g["surface"] in surfaces],
            tags=tags,
        )
        n_changed += new != row
        row.clear()
        row.update(new)
    write_jsonl(path, rows)
    print(f"{path.name}: {len(rows)} rows, changed {n_changed}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["requests", "judge-requests", "build", "apply-policy"])
    parser.add_argument("--file", type=Path, action="append", help="apply-policy で書き換える行のファイル")
    parser.add_argument("--write", default=None, help="build で書き出す集合（既定は --splits と同じ）")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--split", choices=["train", "val", "test"])
    parser.add_argument("--n", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--pilot", type=int, default=0)
    parser.add_argument("--splits", default="train,val,test")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    if args.stage == "requests":
        requests(args.split, args.n, args.work, args.offset)
    elif args.stage == "judge-requests":
        judge_requests(args.work, args.splits.split(","))
    elif args.stage == "apply-policy":
        for f in args.file:
            apply_glossary_policy(f)
    else:
        splits = args.splits.split(",")
        build(args.work, args.out_dir, args.pilot, splits, args.write.split(",") if args.write else splits)


if __name__ == "__main__":
    main()
