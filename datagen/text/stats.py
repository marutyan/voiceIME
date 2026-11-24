"""書き出したデータの件数と割合を集計し、READMEと報告に載せる数値を出す。

あわせて、検査の条件のうち書き出し後にも成り立つべきもの（held-outの漏れ、表記、読み、英字）を
全行についてもう一度確かめ、違反があれば件数を表示する。

使い方：uv run python datagen/text/stats.py [--dir <出力先>]
"""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from common import DATA_DIR, has_latin, read_jsonl, surface_pattern


def summarize(path: Path, held: set[str], train_only: bool, glossary: dict[str, dict]) -> None:
    """1つの集合の件数、割合、再検査の違反を表示する。"""
    rows = list(read_jsonl(path))
    n = len(rows)
    tags = Counter(t for r in rows for t in r["tags"])
    usecase = Counter(r["usecase"] for r in rows)
    domain = Counter(r["domain"] for r in rows)
    zero = sum(1 for r in rows if not r["terms"])
    with_held = sum(1 for r in rows if set(r["terms"]) & held)
    secs = [r["est_seconds"] for r in rows]
    fillers = [r["fillers"] for r in rows]
    n_dist = [len({g["surface"] for g in r["glossary"]} - set(r["terms"])) for r in rows]
    print(f"== {path.name}: {n} rows")
    print(f"  用語なし: {zero} ({zero / n:.1%})  held-outを含む: {with_held} ({with_held / n:.1%})")
    print(f"  tags: " + ", ".join(f"{k}={v} ({v / n:.1%})" for k, v in tags.most_common()))
    print(f"  usecase: " + ", ".join(f"{k}={v}" for k, v in usecase.most_common()))
    print(f"  domain: " + ", ".join(f"{k}={v}" for k, v in domain.most_common()))
    print(f"  推定秒数: min={min(secs)} median={statistics.median(secs)} max={max(secs)}")
    print(f"  フィラー: 0個={sum(f == 0 for f in fillers)} 平均={statistics.mean(fillers):.2f} 最大={max(fillers)}")
    print(f"  用語の数（平均）: {statistics.mean(len(r['terms']) for r in rows):.2f}  無関係な語の数（平均）: {statistics.mean(n_dist):.2f}")

    bad: Counter[str] = Counter()
    for r in rows:
        if r["spoken_text"] != r["spoken_text_kana"]:
            bad["spoken_text_differs_from_kana"] += 1
        if has_latin(r["spoken_text_kana"]):
            bad["latin_in_kana"] += 1
        gsurf = {g["surface"] for g in r["glossary"]}
        for t in r["terms"]:
            if not surface_pattern(t).search(r["target_text"]):
                bad["term_not_in_target"] += 1
            if not any(rd in r["spoken_text_kana"] for rd in glossary[t]["readings"]):
                bad["term_reading_not_in_kana"] += 1
            if t not in gsurf:
                bad["term_not_in_row_glossary"] += 1
        if r["spoken_marked"].count("{") != r["fillers"]:
            bad["filler_count_mismatch"] += 1
        if train_only:
            text = r["target_text"] + "\n" + r["spoken_text_mixed"]
            if any(surface_pattern(h).search(text) for h in held) or gsurf & held:
                bad["held_out_in_train_or_val"] += 1
    print(f"  再検査の違反: {dict(bad) if bad else 'なし'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    gl = list(read_jsonl(DATA_DIR / "glossary.jsonl"))
    glossary = {g["surface"]: g for g in gl}
    held = {g["surface"] for g in gl if g["split"] == "held-out"}
    print(f"glossary: {len(gl)} terms, held-out {len(held)}")
    for name, train_only in (("train", True), ("val", True), ("test-synth", False), ("pilot", False)):
        p = args.dir / f"{name}.jsonl"
        if p.exists():
            summarize(p, held, train_only, glossary)


if __name__ == "__main__":
    main()
