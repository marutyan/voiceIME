#!/usr/bin/env python3
"""元データ runs/error-attribution/{val,test-novel}.json。出力 figures/error-attribution/stage-breakdown.png。"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

# 既存の実験図と同じ画面用スタイルを使う。
RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(ROOT / "figures/.work"))
import paperstyle as ps  # noqa: E402


def main():
    """同じ出力を再採点した未正答数を、評価条件ごとに積み上げて比べる。"""
    style = ps.use("screen")
    conditions = (
        ("test-novel", "20"),
        ("test-novel", "32"),
        ("val", "20"),
    )
    datasets = {
        split: json.loads((RUN / f"{split}.json").read_text(encoding="utf-8"))
        for split in ("val", "test-novel")
    }
    data = [datasets[split]["conditions"][cap]["classes"] for split, cap in conditions]
    labels = [f"{split}  上限{cap}" for split, cap in conditions]
    stages = (
        ("A", "A  整形LLM", ps.OKABE_ITO[0], "white"),
        ("B", "B  候補選択", ps.OKABE_ITO[2], "black"),
        ("C", "C  ASRの表記・読み", ps.OKABE_ITO[4], "black"),
        ("D", "D  その他", ps.NEUTRAL, "white"),
    )

    figure, axis = plt.subplots(figsize=(style["full"], 4.0), layout="constrained")
    totals = [0] * len(data)
    for key, label, color, text_color in stages:
        counts = [row.get(key, 0) for row in data]
        bars = axis.barh(
            labels, counts, left=totals, height=0.55, color=color, label=label
        )
        axis.bar_label(
            bars,
            labels=[str(n) if n else "" for n in counts],
            label_type="center",
            color=text_color,
        )
        totals = [left + count for left, count in zip(totals, counts, strict=True)]
    for label, total in zip(labels, totals, strict=True):
        axis.annotate(
            f"計 {total}",
            (total, label),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
        )
    axis.set_xlim(0, max(totals) * 1.12)
    axis.set_xlabel("未正答の用語出現数")
    axis.invert_yaxis()
    axis.grid(False, axis="y")
    axis.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncols=len(stages))
    output = ROOT / "figures/error-attribution/stage-breakdown.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output)
    plt.close(figure)


if __name__ == "__main__":
    main()
