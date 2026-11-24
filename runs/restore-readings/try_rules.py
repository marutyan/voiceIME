"""整形の出力に残った「用語の読み」を、一覧の表記へ戻す後処理の効果を、保存済みの出力で数える。

R1：segment-merge後の文に表記があり、出力に表記が無く読みがある語だけ戻す。
R2：一覧の語で、出力に表記が無く読み（最小の長さ以上）がある語を戻す。
"""
import json, sys
from pathlib import Path
from voiceime.eval.metrics import calculate_cer, calculate_term_accuracy

IN = Path("runs/restore-readings/in")
MANIFEST = {"val": "data/tts/val/manifest.jsonl",
            "test-novel": "runs/asr-tts/r3-audio-20261122/test-novel-source.jsonl"}

def load(path):
    return [json.loads(l) for l in open(path)]

def restore(hyp, entries, merged, rule, min_len):
    # 長い読みから先に置き換え、短い読みが長い読みの一部を壊さないようにする。
    cands = []
    for e in entries:
        if e["surface"] in hyp:
            continue
        if rule == "R1" and e["surface"] not in merged:
            continue
        for r in e.get("readings", []):
            if len(r) >= min_len and r in hyp:
                cands.append((len(r), r, e["surface"]))
    for _, r, s in sorted(cands, reverse=True):
        hyp = hyp.replace(r, s)
    return hyp

def score(rows, gold):
    hit = tot = 0
    for r in rows:
        g = gold[r["id"]]
        a = calculate_term_accuracy(g["terms"], g.get("glossary", []), r["hyp"]); hit += a["correct"]; tot += a["total"]
    c = calculate_cer([gold[r["id"]]["target_text"] for r in rows], [r["hyp"] for r in rows])
    return hit, tot, 100 * c["rate"]

if __name__ == "__main__":
  for model in ("D-0.8B-drop0", "D-2B-drop0.075"):
      for split in ("val", "test-novel"):
          gold = {r["id"]: r for r in load(MANIFEST[split])}
          gl = {r["id"]: r["glossary"] for r in load(IN / f"gloss-{split}.jsonl")}
          rows = load(IN / f"{model}-{split}.jsonl")
          base = score(rows, gold)
          print(f"{model} {split} base {base[0]}/{base[1]} CER {base[2]:.2f}")
          for rule, min_len in (("R1", 2), ("R2", 6), ("R2", 5), ("R2", 4), ("R2", 3), ("R2", 2)):
              new = [dict(r, hyp=restore(r["hyp"], gl[r["id"]], r["input_text"]["combined_text"] or "", rule, min_len)) for r in rows]
              changed = sum(a["hyp"] != b["hyp"] for a, b in zip(rows, new))
              s = score(new, gold)
              print(f"  {rule} min{min_len}: {s[0]}/{s[1]} CER {s[2]:.2f} changed {changed}")
