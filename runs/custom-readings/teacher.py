"""種を固定して慣習読みを提案・再検証し、同音の衝突を記録する。"""
from __future__ import annotations

import argparse
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# 類似の発音は全角・カタカナに揃え、既存selectorと同様に長音記号を無視する。
def kana(value: str) -> str:
    """読みを発音の照合に使うキーへ変換する。"""
    return "".join(
        chr(ord(c) + 96) if "ぁ" <= c <= "ゖ" else c
        for c in unicodedata.normalize("NFKC", value) if c not in "ー・ 　-"
    )


def read(path: Path) -> list[dict]:
    """JSONLを順番どおり読む。"""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path: Path, rows: list[dict]) -> None:
    """中断時に作成途中のJSONLを利用しないようにする。"""
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    temporary.replace(path)


def request(identifier: str, message: str, items: list, max_tokens: int) -> dict:
    """教師へ送る本文と、出力番号を元の語へ戻す対応を保存する。"""
    return {"id": identifier, "items": items, "messages": [{"role": "user", "content": message}],
            "temperature": 0, "top_p": 1, "max_tokens": max_tokens, "seed": 0}


def answered(work: Path, step: str) -> list[tuple[list, list[str]]]:
    """要求IDで応答を突合し、完全な応答だけを返す。"""
    requests = read(work / f"{step}-requests.jsonl")
    responses = read(work / f"{step}-responses.jsonl")
    by_id = {row["id"]: row for row in responses}
    if len(responses) != len(by_id) or set(by_id) != {row["id"] for row in requests}:
        raise ValueError(f"{step}の要求と応答のIDが一致しません")
    return [
        (row["items"], by_id[row["id"]]["text"].splitlines())
        for row in requests if by_id[row["id"]]["finish_reason"] == "stop"
    ]


def prepare(work: Path, existing: dict, surfaces: list[str]) -> None:
    """種99語を固定seedで分け、例示側だけを教師の提案プロンプトへ入れる。"""
    seed = []
    for line in (work / "seed.tsv").read_text().splitlines():
        surface, readings = line.split("\t")
        seed.append((surface, readings.split(",")))
    rng = random.Random(0)
    rng.shuffle(seed)
    examples, held = seed[:len(seed)//2], seed[len(seed)//2:]
    (work / "seed-split.json").write_text(json.dumps(
        {"seed": 0, "examples": dict(examples), "held": dict(held)}, ensure_ascii=False, indent=2) + "\n")
    example_text = "\n".join(f"{s}: {','.join(r)}" for s, r in examples)
    prefix = (
        "日本のITエンジニアや研究者が会話で実際に使う慣習的な読みを挙げてください。"
        "頭字語を単語として読む形、通称、略して呼ぶ形が対象です。"
        "既存欄の読みの長音や促音の違い、機械的な一字読み、推測した読みは不要です。"
        "確信できる読みのみ最大3件、該当なしは行ごと省略し、全部なければ「なし」。"
        "出力は番号:カタカナ,カタカナの形式で1語1行。説明は不要です。\n"
        f"慣習的な読みの例\n{example_text}\n\n対象（番号 / 表記 / 既存読み）\n"
    )
    rows = []
    for offset in range(0, len(surfaces), 24):
        batch = surfaces[offset:offset+24]
        lines = [f"{n} / {s} / {','.join(existing[s])}" for n, s in enumerate(batch, 1)]
        rows.append(request(str(offset // 24), prefix + "\n".join(lines), batch, 768))
    write(work / "propose-requests.jsonl", rows)


def propose(work: Path) -> None:
    """形式の合う提案を、例示を含まない実使用判定への要求に変える。"""
    parsed = defaultdict(dict)
    for items, lines in answered(work, "propose"):
        for line in lines:
            match = re.fullmatch(r"\s*(\d+)\s*[:：]\s*(.+?)\s*", line)
            if not match or not 1 <= int(match[1]) <= len(items):
                continue
            for value in re.split("[,，、]", match[2])[:3]:
                value = unicodedata.normalize("NFKC", value.strip())
                if re.fullmatch("[ァ-ヺー・ ]+", value) and kana(value):
                    readings = parsed[items[int(match[1])-1]]
                    if len(readings) < 3:
                        readings.setdefault(kana(value), value)
    pairs = sorted((surface, reading) for surface, values in parsed.items() for reading in values.values())
    prefix = (
        "各行のIT・研究用語について、日本のエンジニア・研究者が会話でその読みを"
        "実際に使うと知っているかを独立に判断してください。読みとして作れるだけなら「不明」。"
        "誤りは「いいえ」。確信して実用例を知る場合のみ「はい」。"
        "各行を 番号:はい または 番号:いいえ または 番号:不明 で答えてください。説明不要。\n"
    )
    requests = []
    for offset in range(0, len(pairs), 32):
        batch = pairs[offset:offset+32]
        body = "\n".join(f"{i} / {surface} / {reading}" for i, (surface, reading) in enumerate(batch, 1))
        requests.append(request(str(offset//32), prefix + body, batch, 512))
    write(work / "verify-requests.jsonl", requests)


def finish(work: Path, existing: dict, prior: dict) -> None:
    """はいと判定された読みを採り、既存読み・前回の追加読み・衝突を照合する。"""
    verified = defaultdict(dict)
    votes = Counter()
    for items, lines in answered(work, "verify"):
        group = defaultdict(set)
        for line in lines:
            match = re.fullmatch(r"\s*(\d+)\s*[:：]\s*(はい|いいえ|不明)\s*[。.]?\s*", line)
            if match and 1 <= int(match[1]) <= len(items):
                group[int(match[1])-1].add(match[2])
        for position, (surface, reading) in enumerate(items):
            decisions = group[position]
            vote = next(iter(decisions)) if len(decisions) == 1 else "形式不明"
            votes[vote] += 1
            if vote == "はい":
                verified[surface].setdefault(kana(reading), reading)

    split = json.loads((work / "seed-split.json").read_text())
    surface_key = defaultdict(list)
    for surface in existing:
        surface_key[surface.casefold()].append(surface)
    held = []
    for surface, readings in split["held"].items():
        matches = [surface] if surface in existing else surface_key[surface.casefold()]
        if len(matches) != 1:
            held.append({"surface": surface, "status": "辞書表記なし・曖昧", "expected": readings})
            continue
        key = matches[0]
        found = [r for r in readings if kana(r) in verified[key]]
        held.append({"surface": surface, "dictionary_surface": key, "expected": readings,
                     "verified": found, "already_known": [
                         r for r in readings if kana(r) in {kana(x) for x in (*existing[key], *prior.get(key, ()))}]})
    write(work / "seed-held-results.jsonl", held)
    # 利用者が指定した2語は教師の種再現率を測り終えてから直接登録する。
    overrides = {"IJCAI": "イジカイ", "ICLR": "アイクリア"}
    for surface, reading in overrides.items():
        if surface not in existing:
            raise ValueError(f"指定語が元の用語集にありません: {surface}")
        verified[surface].setdefault(kana(reading), reading)
    taken = {}
    owners = defaultdict(set)
    for surface, readings in existing.items():
        for r in (*readings, *prior.get(surface, ())):
            owners[kana(r)].add(surface)
    for surface, variants in verified.items():
        known = {kana(r) for r in (*existing[surface], *prior.get(surface, ()))}
        additions = {key: value for key, value in variants.items() if key not in known}
        if additions:
            taken[surface] = additions
        for key in additions:
            owners[key].add(surface)
    rows = []
    for surface, additions in sorted(taken.items()):
        row = {"surface": surface, "readings": list(additions.values())}
        collisions = {reading: sorted(owners[key] - {surface})
                      for key, reading in additions.items() if owners[key] - {surface}}
        if collisions:
            row["homophones"] = collisions
        rows.append(row)
    write(work / "glossary-custom-readings.jsonl", rows)
    sample = random.Random(0).sample(rows, min(50, len(rows)))
    write(work / "spot-check-50.jsonl", sample)
    expected = sum(len(r["expected"]) for r in held)
    observed = sum(len(r.get("verified", ())) for r in held)
    novel_expected = sum(len(set(r["expected"]) - set(r.get("already_known", ()))) for r in held)
    novel_observed = sum(len(set(r.get("verified", ())) - set(r.get("already_known", ()))) for r in held)
    summary = {"target_surfaces": len(existing), "rows": len(rows),
               "readings": sum(len(r["readings"]) for r in rows),
               "homophone_readings": sum(len(r.get("homophones", {})) for r in rows),
               "verification": dict(votes), "held_surfaces": len(held),
               "held_hits": sum(bool(r.get("verified")) for r in held),
               "held_expected_readings": expected, "held_verified_readings": observed,
               "held_previously_unknown_expected": novel_expected,
               "held_previously_unknown_verified": novel_observed,
               "overrides_after_scoring": overrides}
    (work / "teacher-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    with (work / "PROGRESS.md").open("a") as progress:
        progress.write(f"- 段階1完了 {len(rows)}語・{summary['readings']}読み、種の読み {observed}/{expected}、同音 {summary['homophone_readings']}読み。\n")


def main() -> None:
    """facultyの固定辞書で提案・再検証・出力を順に実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "propose", "finish"))
    args = parser.parse_args()
    work = Path.home() / "voiceime-work-custom"
    dictionary = Path.home() / "voiceime-work-asr/data/glossary"
    existing = defaultdict(dict)
    for path in (dictionary / "glossary.jsonl", dictionary / "glossary-v2.jsonl"):
        for row in read(path):
            existing[row["surface"]].update(dict.fromkeys(row["readings"]))
    prior = {row["surface"]: row["readings"] for row in read(
        Path.home() / "voiceime-work-altread/20261124/combined.jsonl")}
    surfaces = sorted(s for s in existing if re.search("[A-Za-z]", unicodedata.normalize("NFKC", s)))
    if args.step == "prepare":
        prepare(work, existing, surfaces)
    elif args.step == "propose":
        propose(work)
    else:
        finish(work, existing, prior)


if __name__ == "__main__":
    main()
