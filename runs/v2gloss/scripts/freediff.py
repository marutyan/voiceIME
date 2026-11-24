"""free 50件で、v1と比べて第2版で新たに現れた英字の語と消えた英字の語を並べる一時的な集計。commitしない。"""
import json, re, sys
from collections import Counter
from pathlib import Path
R = Path("/Users/marutyan/PrivateDev/voiceIME/runs/v2gloss")
S = Path(__file__).parent
free = {json.loads(l)["id"] for l in open(S / "devuser-free.jsonl")}
stage, label = sys.argv[1], sys.argv[2]
fn = (lambda l: R / f"asr-{l}.jsonl") if stage == "asr" else (lambda l: R / f"e2e-{l}+sft2-qwen.jsonl")
def load(l):
    return {r["id"]: r["hyp"] for r in map(json.loads, open(fn(l))) if r["id"] in free}
a, b = load("v1-t16-s75"), load(label)
TOK = re.compile(r"[A-Za-z][A-Za-z0-9.+#_\-]*(?: [A-Z][A-Za-z0-9.+#_\-]*)*")
nchg = 0
for i in sorted(free):
    if a[i] == b[i]:
        continue
    nchg += 1
    ta, tb = Counter(TOK.findall(a[i])), Counter(TOK.findall(b[i]))
    new, gone = tb - ta, ta - tb
    print(f"### {i}  新:{list(new.elements())}  消:{list(gone.elements())}\n  v1: {a[i]}\n  v2: {b[i]}")
print(f"変わった件数: {nchg}/{len(free)}")
