#!/usr/bin/env python3
"""Source: data/aggregate.json and data/test-novel-audit-summary.json
Output: figures/formatter-sft3/mainselector21-val-vs-testnovel-listed-accuracy.png
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paperstyle as ps
from method_styles import METHOD_ORDER, METHOD_STYLES


WORK_DIR = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[4]
AGGREGATE_PATH = WORK_DIR / "data" / "aggregate.json"
AUDIT_PATH = WORK_DIR / "data" / "test-novel-audit-summary.json"
OUTPUT_PATH = ROOT / "figures" / "formatter-sft3" / "mainselector21-val-vs-testnovel-listed-accuracy.png"
LABEL_OFFSETS = {
    "B": (9, 12),
    "B-drop0": (-10, -35),
    "B-drop0-focus": (20, -55),
    "B-drop0-seed1": (18, 24),
    "B-2B-drop0": (-130, -45),
}


def read_json(path: Path) -> Dict[str, Any]:
    """集計元から図に使う数値を読む。"""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """一覧内正答率とval CERの両立を、B入力の5条件で比較する。"""
    ps.use("screen")
    aggregate = read_json(AGGREGATE_PATH)
    audit = read_json(AUDIT_PATH)
    metrics = aggregate["conditions"]
    models = audit["models"]
    coverage = {models[name]["included"] for name in METHOD_ORDER}
    if len(coverage) != 1:
        raise ValueError(f"B入力条件間で一覧内件数が異なります: {sorted(coverage)}")
    for name in METHOD_ORDER:
        if audit["input_match_counts"].get(f"{name}_expected_input") != 500:
            raise ValueError(f"{name}: test-novel inputの照合に失敗しました")
        if audit["selection_match_counts"].get(f"{name}_matches_B") != 500:
            raise ValueError(f"{name}: Bとの用語一覧が500件すべて一致しません")

    x_values = {name: metrics[name]["val"]["cer"] * 100 for name in METHOD_ORDER}
    y_values = {
        name: models[name]["included_accuracy"] * 100 for name in METHOD_ORDER
    }
    figure, axis = plt.subplots(figsize=(12.0, 6.2), layout="constrained")

    for name in METHOD_ORDER:
        style = METHOD_STYLES[name]
        scatter_style = {
            "s": 90,
            "color": style["color"],
            "marker": style["marker"],
            "zorder": 4,
        }
        if style["marker"] not in {"x", "+", "|", "_"}:
            scatter_style.update(edgecolor="white", linewidth=1.0)
        axis.scatter(x_values[name], y_values[name], **scatter_style)
        count = models[name]["included_correct"]
        total = models[name]["included"]
        axis.annotate(
            f"{name} ({count}/{total})",
            (x_values[name], y_values[name]),
            xytext=LABEL_OFFSETS[name],
            textcoords="offset points",
            ha="left" if LABEL_OFFSETS[name][0] >= 0 else "right",
            va="center",
            fontsize=10,
            color=style["color"],
            bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": style["color"], "lw": 0.8},
            arrowprops={"arrowstyle": "-", "color": style["color"], "lw": 0.8},
            zorder=5,
        )

    baseline_x = x_values["B"]
    baseline_y = y_values["B"]
    axis.axvline(baseline_x, color=ps.NEUTRAL, linestyle="--", linewidth=1.0, zorder=1)
    axis.axhline(baseline_y, color=ps.NEUTRAL, linestyle="--", linewidth=1.0, zorder=1)
    axis.text(
        0.99,
        0.02,
        f"B基準: val CER {baseline_x:.2f}%、一覧内正答率 {baseline_y:.1f}%\n"
        f"5条件共通の対象語 {next(iter(coverage))}/500件",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        color="#333333",
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": "#bbbbbb", "lw": 0.8},
    )
    x_min, x_max = min(x_values.values()), max(x_values.values())
    y_min, y_max = min(y_values.values()), max(y_values.values())
    axis.set_xlim(x_min - 0.12, x_max + 0.12)
    axis.set_ylim(y_min - 5.0, y_max + 5.0)
    axis.set_xlabel("val CER（%）・小さいほど良い")
    axis.set_ylabel("test-novel一覧内の正答率（%）・大きいほど良い")
    axis.grid(True, which="major")
    axis.text(
        0.02,
        0.98,
        "左上ほど両指標が良い。val用語正答数は比較表で確認。",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        color="#333333",
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT_PATH, dpi=300)
    plt.close(figure)


if __name__ == "__main__":
    main()
