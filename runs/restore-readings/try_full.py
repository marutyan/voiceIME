"""用語集全体（一覧に選ばれなかった語も含む）で、出力に残った読みを表記へ戻す規則R3の効果を数える。
読みが1つの表記だけに対応し、最小の長さ以上のものだけを使う。"""
import json, sys
from pathlib import Path
sys.path.insert(0, "runs/restore-readings")
from try_rules import load, score, MANIFEST, IN

def build(exclude, min_len):
    by_reading = {}
    for f in ("data/text/glossary.jsonl", "data/text/glossary-v2.jsonl"):
        for e in load(f):
            if e["surface"] in exclude:
                continue
            for r in e.get("readings", []):
                if len(r) >= min_len:
                    by_reading.setdefault(r, set()).add(e["surface"])
    # 同じ読みに複数の表記がある場合は、どれに戻すか決められないので使わない。
    return sorted(((r, next(iter(s))) for r, s in by_reading.items() if len(s) == 1), key=lambda x: -len(x[0]))

def restore(hyp, table):
    for r, s in table:
        if r in hyp and s not in hyp:
            hyp = hyp.replace(r, s)
    return hyp

EXC = {"val": sys.argv[1], "test-novel": "data/text/glossary-v2-excluded.txt"}
for model in ("D-0.8B-drop0", "D-2B-drop0.075"):
    for split in ("val", "test-novel"):
        exclude = set(open(EXC[split]).read().split("\n"))
        gold = {r["id"]: r for r in load(MANIFEST[split])}
        rows = load(IN / f"{model}-{split}.jsonl")
        b = score(rows, gold); print(f"{model} {split} base {b[0]}/{b[1]} CER {b[2]:.2f}")
        for min_len in (8, 7, 6, 5):
            table = build(exclude, min_len)
            new = [dict(r, hyp=restore(r["hyp"], table)) for r in rows]
            s = score(new, gold)
            print(f"  R3 min{min_len}: {s[0]}/{s[1]} CER {s[2]:.2f} changed {sum(a['hyp']!=b_['hyp'] for a,b_ in zip(rows,new))}")
