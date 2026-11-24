#!/usr/bin/env python3
"""Source: runs/formatter-sft3/main-glossary-frozen-reeval-retry1-20261122/test-novel-audit-summary.json
Output: figures/formatter-sft3/test-novel-glossary-selection-accuracy.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paperstyle as ps
from method_styles import METHOD_STYLES


ROOT = Path(__file__).resolve().parents[4]
DATA_PATH = Path(__file__).parent / "data" / "test-novel-audit-summary.json"
OUTPUT_PATH = ROOT / "figures" / "formatter-sft3" / "test-novel-glossary-selection-accuracy.png"
MODEL_ORDER = ("SFT2", "A", "B", "C", "B-2B")


def main() -> None:
    """固定一覧条件で、一覧内と一覧外の正表記率を比較する。"""
    ps.use("screen")
    summary = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    models = summary["models"]
    x_positions = np.arange(len(MODEL_ORDER))
    bar_width = 0.34
    fig, ax = plt.subplots(figsize=(12.0, 6.0), layout="constrained")

    for index, name in enumerate(MODEL_ORDER):
        stats = models[name]
        style = METHOD_STYLES[name]
        for offset, bucket, label, hatch in (
            (-bar_width / 2, "included", "一覧にある", ""),
            (bar_width / 2, "excluded", "一覧にない", "///"),
        ):
            correct = stats[f"{bucket}_correct"]
            total = stats[bucket]
            accuracy = 100 * correct / total if total else 0.0
            bar = ax.bar(
                x_positions[index] + offset,
                accuracy,
                bar_width * 0.92,
                color=style["color"] if bucket == "included" else "white",
                edgecolor=style["color"],
                linewidth=1.5,
                hatch=hatch,
                zorder=3,
            )[0]
            ax.annotate(
                f"{correct}/{total}",
                (bar.get_x() + bar.get_width() / 2, accuracy),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                color=style["color"],
            )

    ax.set_title("(a) 一覧内外での正表記率", loc="left", pad=12)
    ax.set_ylabel("正表記を出力した割合（%）")
    ax.set_xlabel("モデル")
    ax.set_xticks(x_positions, MODEL_ORDER)
    ax.set_ylim(0, 100)
    ax.set_yticks(np.arange(0, 101, 20))
    ax.grid(True, axis="y", zorder=0)
    ax.grid(False, axis="x")
    ax.legend(
        handles=[
            Patch(facecolor="#777777", edgecolor="#777777", label="一覧にある"),
            Patch(facecolor="white", edgecolor="#777777", hatch="///", label="一覧にない"),
        ],
        loc="upper left",
        ncol=2,
        title="正解用語の選択状態",
    )
    ax.text(
        0.99,
        0.98,
        "test-novel 500件・全条件でSFT2の一覧を固定",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
