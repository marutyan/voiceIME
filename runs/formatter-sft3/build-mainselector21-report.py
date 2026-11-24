#!/usr/bin/env python3
"""評価集計、test-novelの用語一覧監査、batch 1遅延を最終表へまとめる。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
AGGREGATE_PATH = ROOT / "corrected-all-results-mainselector21-20261123" / "aggregate.json"
AUDIT_PATH = ROOT / "test-novel-audit-summary-mainselector21-all-corrected-20261123.json"
LATENCY_PATH = ROOT / "batch1-latency-mainselector21-20261123" / "summary.json"
OUTPUT_DIR = ROOT / "mainselector21-final-20261123"


def read_json(path: Path) -> dict[str, Any]:
    """実測の集計JSONを読み、欠落した成果物は明示的に止める。"""
    return json.loads(path.read_text(encoding="utf-8"))


def format_result(result: dict[str, Any] | None) -> str:
    """CERと用語正答数を表の1セルへ整える。"""
    if result is None:
        return "—"
    return f"{result['cer'] * 100:.2f}% / {result['term_correct']}/{result['term_total']}"


def main() -> None:
    """本人、val、test-novel、遅延を同じ条件順で一つの記録へまとめる。"""
    aggregate = read_json(AGGREGATE_PATH)
    audit = read_json(AUDIT_PATH)
    latency = read_json(LATENCY_PATH)
    conditions = aggregate["conditions"]
    models = audit["models"]

    output = {
        "sources": {
            "aggregate": str(AGGREGATE_PATH),
            "test_novel_audit": str(AUDIT_PATH),
            "latency": str(LATENCY_PATH),
        },
        "manifests": aggregate["manifests"],
        "input_match_counts": audit["input_match_counts"],
        "selection_match_counts": audit["selection_match_counts"],
        "test_novel_selector": {
            "pool": audit["glossary_pool"],
            "models": {
                name: {
                    "terms": stats["terms"],
                    "included": stats["included"],
                    "included_correct": stats["included_correct"],
                    "included_accuracy": stats["included_accuracy"],
                    "excluded": stats["excluded"],
                    "excluded_correct": stats["excluded_correct"],
                    "excluded_accuracy": stats["excluded_accuracy"],
                    "selected_order_matches_sft2": stats.get(
                        "selected_order_matches_sft2", stats.get("selected_order_matches_A")
                    ),
                }
                for name, stats in models.items()
            },
        },
        "conditions": conditions,
        "batch1_latency": latency,
    }

    lines = [
        "| 条件 | 本人50件 CER / 用語 | 見えない用語除外 CER / 用語 | val CER / 用語 | test-novel 全体 | 一覧内 | 一覧外 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, values in conditions.items():
        novel = values["test_novel"]
        selector = models[name]
        overall = f"{novel['term_correct']}/{novel['term_total']}"
        included = f"{selector['included_correct']}/{selector['included']}"
        excluded = f"{selector['excluded_correct']}/{selector['excluded']}"
        lines.append(
            f"| {name} | {format_result(values['devuser'])} | "
            f"{format_result(values['devuser_no_unseen'])} | {format_result(values['val'])} | "
            f"{overall} | {included} ({selector['included_accuracy']:.1%}) | "
            f"{excluded} ({selector['excluded_accuracy']:.1%}) |"
        )

    lines.extend(
        [
            "",
            "| model | 評価条件 | 件数 | batch 1整形時間 中央値 / p90 | 平均 |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for model_size, stats in latency.items():
        lines.append(
            f"| {model_size} | B入力、val、greedy | {stats['n']} | "
            f"{stats['median_format_latency_s']:.3f} / {stats['p90_format_latency_s']:.3f}秒 | "
            f"{stats['mean_format_latency_s']:.3f}秒 |"
        )

    lines.extend(
        [
            "",
            "SFT3はfacultyのTransformers BF16評価で、本人の読み上げは修正版manifestの50 IDを使用した。本人の行別予測はfacultyにのみ保存し、表には集計値だけを載せた。",
            "test-novelの一覧内外率は、各評価JSONLの選択用語とmanifestの正解語をIDごとに照合した。入力形式の監査は、全500 IDで通過した。",
            "SFT2は保存済みMLX 4bit結果であり、保存時の用語一覧と現行main selectorの一覧は同一ではない。SFT2とSFT3のtest-novel総正答数は選択一覧も異なる参考比較として読む。",
            "batch 1遅延はfaculty GPUの測定であり、Mac上の実遅延そのものではない。",
            "",
        ]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "aggregate.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "table.md").write_text("\n".join(lines), encoding="utf-8")
    (OUTPUT_DIR / "test-novel-audit-summary.json").write_text(
        AUDIT_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (OUTPUT_DIR / "batch1-latency-summary.json").write_text(
        LATENCY_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT_DIR), "conditions": len(conditions)}, indent=2))


if __name__ == "__main__":
    main()
