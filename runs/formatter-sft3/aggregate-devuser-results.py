#!/usr/bin/env python3
"""保存済みの本人用推論結果を、指定manifestで集計し直す。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voiceime.eval.report import _evaluate_run, _load_manifest, _load_unseen_terms


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """行別予測を含めず、比較に使う集計値だけを残す。"""
    terms = result["terms"]
    unseen, seen = terms.get("unseen"), terms.get("seen")
    return {
        "system": result["system"],
        "stage": result["stage"],
        "evaluated": result["utterances"]["evaluated"],
        "cer_errors": result["cer"]["edit_errors"],
        "cer_reference_characters": result["cer"]["reference_characters"],
        "cer": result["cer"]["rate"],
        "term_correct": terms["correct"],
        "term_total": terms["total"],
        "unseen_correct": unseen["correct"] if unseen else None,
        "unseen_total": unseen["total"] if unseen else None,
        "seen_correct": seen["correct"] if seen else None,
        "seen_total": seen["total"] if seen else None,
    }


def main() -> None:
    """旧条件の全用語・見えない用語除外出力を修正版manifestで評価する。"""
    work = Path.home() / "voiceime-work-fr3"
    current = work / "inputs/formatter-sft3-current"
    old_eval = work / "runs/formatter-sft3/main-selector-reeval-20261122"
    manifest = current / "manifest-devuser-scripted-fixed-no-audio-20261122.jsonl"
    unseen_path = work / "inputs/term-select-metal2/unseen-terms-devuser.txt"
    sources = {
        "SFT2": current / "e2e-devuser.jsonl",
        "A": old_eval / "A/current/devuser-s-50.jsonl",
        "B": old_eval / "B/current/devuser-s-50.jsonl",
        "C": old_eval / "C/current/devuser-s-50.jsonl",
        "B-2B": old_eval / "B-2B/current/devuser-s-50.jsonl",
        "B-clean": old_eval / "B-clean/current/devuser-s-50.jsonl",
        "B-drop0": old_eval / "B-drop0/current/devuser-s-50.jsonl",
        "B-no-distractors": old_eval / "B-no-distractors/current/devuser-s-50.jsonl",
    }
    no_unseen_sources = {
        f"{name}-no-unseen": old_eval / name / "current/devuser-s-50-no-unseen.jsonl"
        for name in ("A", "B", "C", "B-2B", "B-clean", "B-drop0", "B-no-distractors")
    }
    manifest_rows, durations = _load_manifest(manifest)
    unseen = _load_unseen_terms(unseen_path)
    results: dict[str, Any] = {
        "manifest": str(manifest),
        "manifest_rows": len(manifest_rows),
        "unseen_terms": str(unseen_path),
        "all_terms": {},
        "excluding_unseen_glossary": {},
    }

    for group, runs in (("all_terms", sources), ("excluding_unseen_glossary", no_unseen_sources)):
        for name, path in runs.items():
            if not path.is_file():
                raise FileNotFoundError(path)
            evaluated = _evaluate_run(path, manifest_rows, durations, unseen_terms=unseen)
            if len(evaluated) != 1:
                raise ValueError(f"{name}: expected one stage, got {len(evaluated)}")
            results[group][name] = summarize(evaluated[0])

    out = work / "runs/formatter-sft3/corrected-devuser-reeval-20261122"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "aggregate.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "| 条件 | 本人50件・全用語 CER | 用語正答 | 見えない用語 | それ以外 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in results["all_terms"].items():
        cer = f"{row['cer_errors']}/{row['cer_reference_characters']} ({row['cer'] * 100:.2f}%)"
        term = f"{row['term_correct']}/{row['term_total']}"
        unseen_value = f"{row['unseen_correct']}/{row['unseen_total']}"
        seen_value = f"{row['seen_correct']}/{row['seen_total']}"
        no_unseen = results["excluding_unseen_glossary"].get(f"{name}-no-unseen")
        if no_unseen:
            no_unseen_value = f"{no_unseen['cer'] * 100:.2f}% / {no_unseen['term_correct']}/{no_unseen['term_total']}"
        else:
            no_unseen_value = "—"
        lines.append(f"| {name} | {cer} | {term} | {unseen_value} | {seen_value} |")
    lines += ["", "見えない用語を一覧から除外した再推論は、保存済み出力があるSFT3条件のみ集計した。", ""]
    lines += [
        "| 条件 | 見えない用語除外・CER / 用語正答 |",
        "| --- | ---: |",
    ]
    for name, row in results["excluding_unseen_glossary"].items():
        lines.append(f"| {name.removesuffix('-no-unseen')} | {row['cer'] * 100:.2f}% / {row['term_correct']}/{row['term_total']} |")
    (out / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "table": str(out / "table.md"), "rows": results["manifest_rows"]}, indent=2))


if __name__ == "__main__":
    main()
