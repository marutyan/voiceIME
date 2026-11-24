"""既存の合成音声ASRから、追加読みあり・なしの候補包含率と誤選択数を測る。"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from voiceime.formatter import glossary

# 既存の候補選択はそのまま使い、要求された2つの一覧上限で集計する。
CAPS = (20, 32)
# 現在のエンジンの補助ASRをvalでの選択基準にする。旧実験の補助ASRとHaas単独も併記する。
INPUTS = ("haas", "qwen06", "qwen17")
# 追加誤選択10件を、正解語1件の増加と同じ重みで扱う。上限20・32を同じ重みで評価する。
FALSE_SELECTION_COST_DENOMINATOR = 10


def fingerprint(path: Path) -> str:
    """候補読み・用語集・評価コード・入力の版を固定する。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluation_inputs(split: str) -> tuple[dict[str, Path], int, int]:
    """facultyの旧実験と同じmanifest・辞書・除外リストを指す。"""
    home = Path.home()
    asr = home / "voiceime-work-asr"
    outputs = asr / "r3-multiasr-20261122/outputs"
    if split == "val":
        manifest = home / "voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/data/tts/val/manifest.jsonl"
        exclusions = "exclude-v2-plus-heldout.txt"
        row_count, term_count = 1000, 1427
    else:
        manifest = home / "voiceime-work-tts/outputs/r3-test-novel-20261122/manifest.jsonl"
        exclusions = "exclude-v2-83.txt"
        row_count, term_count = 500, 500
    return {
        "manifest": manifest,
        "exclude": asr / "r3-twopass-20261122/terms" / exclusions,
        "glossary_v1": asr / "data/glossary/glossary.jsonl",
        "glossary_v2": asr / "data/glossary/glossary-v2.jsonl",
        "haas": outputs / f"haas-plus-qwen06-{split}-plain.jsonl",
        "qwen06": outputs / f"multiasr-{split}-qwen06-firstpass.jsonl",
        "qwen17": outputs / f"multiasr-{split}-qwen17-firstpass.jsonl",
    }, row_count, term_count


def read_inputs(paths: dict[str, Path], row_count: int, term_count: int) -> tuple[list[dict], dict]:
    """ASR結果がmanifestの全件と同じ順であることを確認し、欠落や重複を除外で隠さない。"""
    records = glossary._read_jsonl(paths["manifest"])
    ids = [row["id"] for row in records]
    if len(ids) != row_count or len(set(ids)) != row_count:
        raise ValueError("manifestのID重複または行数の不一致")
    if any(not isinstance(row["terms"], list) or not all(isinstance(t, str) for t in row["terms"])
           for row in records):
        raise ValueError("manifestのtermsは表記の配列が必要")
    if sum(len(row["terms"]) for row in records) != term_count:
        raise ValueError("正解語インスタンス数が旧実験と一致しません")
    hypotheses = {}
    for model in INPUTS:
        rows = glossary._read_jsonl(paths[model])
        if [row["id"] for row in rows] != ids or any(
            row["stage"] != "asr" or not isinstance(row["hyp"], str) for row in rows
        ):
            raise ValueError(f"ASR出力のID・順序・形式が不正: {paths[model]}")
        hypotheses[model] = [row["hyp"] for row in rows]
    return records, hypotheses


def measure(index: glossary.GlossaryIndex, records: list[dict], texts: list[str],
            term_count: int, baseline: dict[int, list[set[str]]] | None) -> tuple[dict, dict]:
    """用語インスタンスで再現率を、発話ごとの集合差で誤選択を集計する。"""
    selected_by_cap: dict[int, list[set[str]]] = {cap: [] for cap in CAPS}
    counts: dict[int, Counter[str]] = {cap: Counter() for cap in CAPS}
    elapsed_ms = []
    for row_index, (row, text) in enumerate(zip(records, texts, strict=True)):
        start = time.perf_counter()
        ranked = [entry.surface for entry in glossary.select_glossary(text, index, max_entries=max(CAPS))]
        elapsed_ms.append(1000 * (time.perf_counter() - start))
        gold_instances = row["terms"]
        gold_set = set(gold_instances)
        for cap in CAPS:
            selected = set(ranked[:cap])
            selected_by_cap[cap].append(selected)
            tally = counts[cap]
            gold_hits = sum(term in selected for term in gold_instances)
            tally["selected"] += len(selected)
            tally["gold_hits"] += gold_hits
            tally["rows_with_gold_hit"] += bool(gold_hits)
            tally["false_selections"] += len(selected - gold_set)
            if baseline is not None:
                original = baseline[cap][row_index]
                added, dropped = selected - original, original - selected
                tally["gold_gained"] += sum(term in added for term in gold_instances)
                tally["gold_lost"] += sum(term in dropped for term in gold_instances)
                tally["false_selections_added"] += len(added - gold_set)
                tally["false_selections_dropped"] += len(dropped - gold_set)
    result = {}
    for cap, tally in counts.items():
        result[str(cap)] = {
            **tally,
            "gold_total": term_count,
            "recall": tally["gold_hits"] / term_count,
            "false_selections_per_row": tally["false_selections"] / len(records),
            "selection_median_ms_at_max_cap": statistics.median(elapsed_ms),
        }
    return result, selected_by_cap


def evaluate(split: str, alternatives: dict[str, Path], paths: dict[str, Path],
             row_count: int, term_count: int) -> dict:
    """同じ候補集合・ASR文に対して、追加読みのファイルだけを変える。"""
    records, hypotheses = read_inputs(paths, row_count, term_count)
    exclusions = glossary.load_term_list(paths["exclude"])
    base_paths = (paths["glossary_v1"], paths["glossary_v2"])
    indexes = {
        name: glossary.GlossaryIndex(glossary.load_glossary(
            *base_paths, exclude_terms=exclusions, alt_readings_path=alt_path
        ))
        for name, alt_path in {"baseline": None, **alternatives}.items()
    }
    known = {entry.surface for entry in indexes["baseline"].entries}
    result: dict[str, Any] = {
        "split": split,
        "rows": row_count,
        "entries": len(known),
        "gold_not_in_glossary": sum(term not in known for row in records for term in row["terms"]),
        "inputs": {name: {"path": str(path), "sha256": fingerprint(path)} for name, path in paths.items()},
        "conditions": {},
    }
    for model in INPUTS:
        texts = hypotheses["haas"]
        if model != "haas":
            texts = [haas + "\n" + aux for haas, aux in zip(texts, hypotheses[model], strict=True)]
        baseline = None
        conditions = {}
        for name, index in indexes.items():
            conditions[name], selected = measure(index, records, texts, term_count, baseline)
            if name == "baseline":
                baseline = selected
        result["conditions"][model] = conditions
    return result


def choose_variant(result: dict, alternatives: dict[str, Path]) -> tuple[str, dict[str, int]]:
    """valのHaas＋Qwen 0.6Bで正解の増減と誤選択を合わせた得点が高い方を選ぶ。"""
    current = result["conditions"]["qwen06"]
    scores = {}
    for name in alternatives:
        scores[name] = sum(
            FALSE_SELECTION_COST_DENOMINATOR *
            (current[name][str(cap)]["gold_hits"] - current["baseline"][str(cap)]["gold_hits"])
            - (current[name][str(cap)]["false_selections"] - current["baseline"][str(cap)]["false_selections"])
            for cap in CAPS
        )
    # 同点では、教師生成に依存しない規則のみを先に扱う。
    return max(scores, key=scores.__getitem__), scores


def main() -> None:
    """valで追加方法を固定し、test-novelでは固定した1種類だけを基準と比較する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, choices=("val", "test-novel"))
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--combined", required=True, type=Path)
    parser.add_argument("--val-report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("集計の出力先が既に存在します")
    paths, row_count, term_count = evaluation_inputs(args.split)
    alternatives = {"rules": args.rules, "combined": args.combined}
    frozen = {
        "selector": fingerprint(Path(glossary.__file__)),
        "evaluation": fingerprint(Path(__file__)),
        "glossary_v1": fingerprint(paths["glossary_v1"]),
        "glossary_v2": fingerprint(paths["glossary_v2"]),
        **{name: fingerprint(path) for name, path in alternatives.items()},
    }
    if args.split == "test-novel":
        if args.val_report is None:
            parser.error("test-novelの前にval-reportで条件を固定してください")
        val = json.loads(args.val_report.read_text(encoding="utf-8"))
        if val["split"] != "val" or val["frozen_sha256"] != frozen:
            parser.error("valで固定した方式・辞書・追加読み・コードと一致しません")
        chosen = val["chosen"]
        result = evaluate(args.split, {chosen: alternatives[chosen]}, paths, row_count, term_count)
        result["val_report_sha256"] = fingerprint(args.val_report)
    else:
        result = evaluate(args.split, alternatives, paths, row_count, term_count)
        chosen, scores = choose_variant(result, alternatives)
        result["val_selection_scores"] = scores
    result["chosen"] = chosen
    result["frozen_sha256"] = frozen
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
