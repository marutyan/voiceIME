"""用語ごとの正誤の差（v1-t16-s75と他の条件）を数える一時的な集計。commitしない。"""
import json, sys, re
from collections import Counter
from pathlib import Path
R = Path("/Users/marutyan/PrivateDev/voiceIME/runs/v2gloss")
S = Path(__file__).parent
man = {json.loads(l)["id"]: json.loads(l) for l in open(S / "devuser-scripted.jsonl")}
def load(p):
    return {r["id"]: r for r in map(json.loads, open(p)) if r["id"] in man}
def ok(rows):
    out = {}
    for i, m in man.items():
        for t, n in Counter(m["terms"]).items():
            out[(i, t)] = (min(n, rows[i]["hyp"].count(t)), n)
    return out
stage = sys.argv[1]  # asr / e2e
base_l = "v1-t16-s75"
fn = (lambda l: R / f"asr-{l}.jsonl") if stage == "asr" else (lambda l: R / f"e2e-{l}+sft2-qwen.jsonl")
base_rows = load(fn(base_l)); base = ok(base_rows)
for l in sys.argv[2:]:
    rows = load(fn(l)); cur = ok(rows)
    gained = [k for k in base if cur[k][0] > base[k][0]]
    lost = [k for k in base if cur[k][0] < base[k][0]]
    print(f"## {stage} {l} vs {base_l}: +{len(gained)} -{len(lost)}")
    for tag, ks in (("得た", gained), ("失った", lost)):
        for i, t in ks:
            print(f"- {tag} {i} {t}\n    v1: {base_rows[i]['hyp']}\n    v2: {rows[i]['hyp']}")
