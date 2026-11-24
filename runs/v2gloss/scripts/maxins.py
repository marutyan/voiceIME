"""analyze.pyのヒント由来の誤挿入から、同じ発話の別の挿入語の一部である短い語（R、Pなど）を除いた件数を出す一時的な集計。commitしない。"""
import json, sys
from collections import defaultdict
sys.path.insert(0, __file__.rsplit('/',1)[0])
import analyze as A
man = {r["id"]: r for r in A.read(A.S / "devuser-scripted.jsonl")}
def maximal(pairs):
    by = defaultdict(set)
    for i, s in pairs: by[i].add(s)
    out = []
    for i, ss in by.items():
        for s in ss:
            if not any(s != t and s in t for t in ss): out.append((i, s))
    return sorted(out)
for label in A.LABELS + ["v1-t16-s75+fmtv2", "v2-t16-s75+fmtv1"]:
    base = label.split("+")[0]
    hints = [h for h in A.read(A.R / f"asr-{base}.hints.jsonl") if h["id"] in man]
    suffix = {"v1-t16-s75+fmtv2": "-fmtv2", "v2-t16-s75+fmtv1": "-fmtv1"}.get(label, "")
    e2e = {r["id"]: r for r in A.read(A.R / f"e2e-{base}+sft2-qwen{suffix}.jsonl")}
    asr, fmt = [], []
    for h in hints:
        ref = man[h["id"]]["target_text"]
        asr += [(h["id"], s) for s in set(A.excess(h.get("hints", []), h["final"], ref))]
        fmt += [(h["id"], s) for s in set(A.excess(e2e[h["id"]]["glossary"], e2e[h["id"]]["hyp"], ref))]
    ma, mf = maximal(asr), maximal(fmt)
    print(f"{label}: ASR {len(ma)} 整形 {len(mf)}")
    print("   ASR:", [f"{i[-4:]}:{s}" for i, s in ma]); print("   整形:", [f"{i[-4:]}:{s}" for i, s in mf])
