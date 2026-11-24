"""保存済みの整形出力を、読みの復元（一覧の語、6文字以上）なし・ありで採点する。引数はモデル名。"""
import sys
sys.path.insert(0, "runs/restore-readings")
from try_rules import load, score, restore, MANIFEST, IN

for model in sys.argv[1:]:
    for split in ("val", "test-novel"):
        gold = {r["id"]: r for r in load(MANIFEST[split])}
        gl = {r["id"]: r["glossary"] for r in load(IN / f"gloss-{split}.jsonl")}
        rows = load(IN / f"{model}-{split}.jsonl")
        new = [dict(r, hyp=restore(r["hyp"], gl[r["id"]], "", "R2", 6)) for r in rows]
        b, s = score(rows, gold), score(new, gold)
        print(f"{model:16s} {split:10s} 素 {b[0]}/{b[1]} CER {b[2]:.2f}% | 復元あり {s[0]}/{s[1]} CER {s[2]:.2f}%")
