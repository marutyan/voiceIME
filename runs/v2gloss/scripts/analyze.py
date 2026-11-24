"""用語集の第2版の評価の補助集計（commitしない一時的な計算）。

公式の指標は`voiceime.eval.report`で出す。ここでは公式の指標に無い次の値だけを数える。
- ヒントの正解含有：scripted 50件の正解の用語（`terms`）の出現のうち、two-passでASRへ渡したヒントに表記が入っていた割合。
- ヒント由来の誤挿入：ASRへ渡したヒント（整形はLLMへ渡した用語）の表記のうち、出力に現れた回数が正解文（target_text）に現れた回数を超えた分。
  公式の「話していない用語の挿入」はその発話の`glossary`（4語前後）の語しか数えないため、用語集の第2版から入る語を数えられない。
- 選択時間、ヒントの件数、遅延の中央値。
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path("/Users/marutyan/PrivateDev/voiceIME")
R = ROOT / "runs/v2gloss"
S = Path(__file__).parent
LABELS = ["v1-t16-s75", "v2-t16-s75", "v2-t8-s75", "v2-t16-s90", "v2-t8-s90", "v2-t16-s100"]


def read(path: Path) -> list[dict]:
    """JSONLを読む。"""
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def excess(surfaces, hyp: str, ref: str) -> list[str]:
    """表記ごとに、出力の出現回数が正解文の出現回数を超えた分を並べる。"""
    out = []
    for s in dict.fromkeys(surfaces):
        n = hyp.count(s) - ref.count(s)
        out += [s] * max(n, 0)
    return out


def main() -> None:
    """全ラベルの補助集計を表にして標準出力へ書く。"""
    manifest = {r["id"]: r for r in read(S / "devuser-scripted.jsonl")}
    print("| 系 | ヒント件数 平均 | 選択時間 中央値 | ヒントの正解含有 | ASRのヒント由来の誤挿入 | 整形のヒント由来の誤挿入 | ASR遅延 中央値/p90 | 整形時間 中央値 | 合計遅延 中央値/p90 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    details = {}
    for label in LABELS:
        hints = [h for h in read(R / f"asr-{label}.hints.jsonl") if h["id"] in manifest]
        asr = {r["id"]: r for r in read(R / f"asr-{label}.jsonl") if r["id"] in manifest}
        e2e_path = R / f"e2e-{label}+sft2-qwen.jsonl"
        e2e = {r["id"]: r for r in read(e2e_path) if r["id"] in manifest} if e2e_path.exists() else {}
        n_gold = n_in = 0
        asr_ins, fmt_ins = [], []
        for h in hints:
            row = manifest[h["id"]]
            hs = h.get("hints", [])
            for t in row["terms"]:
                n_gold += 1
                n_in += t in hs
            asr_ins += [(h["id"], s) for s in excess(hs, h["final"], row["target_text"])]
            if h["id"] in e2e:
                g = e2e[h["id"]]["glossary"]
                fmt_ins += [(h["id"], s) for s in excess(g, e2e[h["id"]]["hyp"], row["target_text"])]
        sel = [h.get("select_s", 0.0) for h in hints]
        lat = sorted(r["latency_s"] for r in asr.values())
        p90 = lambda xs: sorted(xs)[int(round(0.9 * (len(xs) - 1)))]
        fl = [r["format_latency_s"] for r in e2e.values()]
        tl = [r["latency_s"] for r in e2e.values()]
        print(
            f"| {label} | {statistics.mean(len(h.get('hints', [])) for h in hints):.1f} | {statistics.median(sel):.3f} | "
            f"{n_in}/{n_gold} ({n_in / n_gold:.1%}) | {len(asr_ins)} | {len(fmt_ins) if e2e else '-'} | "
            f"{statistics.median(lat):.3f}/{p90(lat):.3f} | {statistics.median(fl):.3f} | {statistics.median(tl):.3f}/{p90(tl):.3f} |"
            if e2e else f"| {label} | ... | ... |"
        )
        details[label] = {"asr_ins": asr_ins, "fmt_ins": fmt_ins}
    print()
    for label, d in details.items():
        print(f"## {label}")
        print("ASR:", d["asr_ins"])
        print("整形:", d["fmt_ins"])


if __name__ == "__main__":
    main()
