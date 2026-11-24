#!/usr/bin/env python3
"""SFT3全条件を同じ評価器で集約し、比較表を作る。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voiceime.eval.report import _evaluate_run, _load_manifest, _load_unseen_terms


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """行別の仮説を含めず、比較に使う集計値だけを返す。"""
    terms = result["terms"]
    unseen, seen = terms.get("unseen"), terms.get("seen")
    return {
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


def evaluate(path: Path, manifest_rows, durations, unseen_terms=None) -> dict[str, Any]:
    """main評価器でrunを読み、集計値だけに縮約する。"""
    results = _evaluate_run(path, manifest_rows, durations, unseen_terms=unseen_terms)
    if len(results) != 1:
        raise ValueError(f"{path}: 1つの評価stageを想定しましたが{len(results)}件です")
    return summarize(results[0])


def result_cell(result: dict[str, Any] | None) -> str:
    """CERと正答数を比較表向けの1セルへ整形する。"""
    if result is None:
        return "—"
    return f"{result['cer'] * 100:.2f}% / {result['term_correct']}/{result['term_total']}"


def main() -> None:
    """修正版manifestと共通評価データで旧・新条件を表にまとめる。"""
    work = Path.home() / "voiceime-work-fr3"
    current = work / "inputs/formatter-sft3-current"
    novel = work / "inputs/test-novel-20261122"
    old = work / "runs/formatter-sft3/mainselector21-reeval-mainselector21-corrected-20261122"
    new = work / "runs/formatter-sft3"
    dev_manifest = current / "manifest-devuser-scripted-fixed-no-audio-20261122.jsonl"
    val_manifest = work / "inputs/manifest-val-no-audio.jsonl"
    novel_manifest = novel / "test-novel.jsonl"
    unseen_path = work / "inputs/term-select-metal2/unseen-terms-devuser.txt"

    conditions = {
        "SFT2": {
            "devuser": current / "e2e-devuser.jsonl",
            "val": current / "e2e-val.jsonl",
            "test_novel": current / "e2e-testnovel-sft2.jsonl",
            "devuser_no_unseen": None,
        },
        "A": {
            "devuser": old / "A/current/devuser-s-50.jsonl",
            "val": old / "A/current/val-asr-1000.jsonl",
            "test_novel": old / "A/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "A/current/devuser-s-50-no-unseen.jsonl",
        },
        "B": {
            "devuser": old / "B/current/devuser-s-50.jsonl",
            "val": old / "B/current/val-asr-1000.jsonl",
            "test_novel": old / "B/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "B/current/devuser-s-50-no-unseen.jsonl",
        },
        "C": {
            "devuser": old / "C/current/devuser-s-50.jsonl",
            "val": old / "C/current/val-asr-1000.jsonl",
            "test_novel": old / "C/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "C/current/devuser-s-50-no-unseen.jsonl",
        },
        "B-2B": {
            "devuser": old / "B-2B/current/devuser-s-50.jsonl",
            "val": old / "B-2B/current/val-asr-1000.jsonl",
            "test_novel": old / "B-2B/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "B-2B/current/devuser-s-50-no-unseen.jsonl",
        },
        "B-clean": {
            "devuser": old / "B-clean/current/devuser-s-50.jsonl",
            "val": old / "B-clean/current/val-asr-1000.jsonl",
            "test_novel": old / "B-clean/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "B-clean/current/devuser-s-50-no-unseen.jsonl",
        },
        "B-drop0": {
            "devuser": old / "B-drop0/current/devuser-s-50.jsonl",
            "val": old / "B-drop0/current/val-asr-1000.jsonl",
            "test_novel": old / "B-drop0/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "B-drop0/current/devuser-s-50-no-unseen.jsonl",
        },
        "B-no-distractors": {
            "devuser": old / "B-no-distractors/current/devuser-s-50.jsonl",
            "val": old / "B-no-distractors/current/val-asr-1000.jsonl",
            "test_novel": old / "B-no-distractors/test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": old / "B-no-distractors/current/devuser-s-50-no-unseen.jsonl",
        },
    }
    new_paths = {
        "B-drop0-focus": "corrected-eval-b-drop0-focus-mainselector21-20261122",
        "B-drop0-seed1": "corrected-eval-b-drop0-seed1-mainselector21-20261122",
        "B-2B-drop0": "corrected-eval-b-2b-drop0-mainselector21-20261122",
    }
    for name, folder in new_paths.items():
        base = new / folder
        conditions[name] = {
            "devuser": base / "current/devuser-s-50.jsonl",
            "val": base / "current/val-asr-1000.jsonl",
            "test_novel": base / "test-novel/test-novel-include-novel.jsonl",
            "devuser_no_unseen": base / "current/devuser-s-50-no-unseen.jsonl",
        }

    dev_rows, dev_durations = _load_manifest(dev_manifest)
    val_rows, val_durations = _load_manifest(val_manifest)
    novel_rows, novel_durations = _load_manifest(novel_manifest)
    unseen_terms = _load_unseen_terms(unseen_path)
    all_results: dict[str, Any] = {
        "manifests": {
            "devuser": str(dev_manifest),
            "devuser_rows": len(dev_rows),
            "val": str(val_manifest),
            "val_rows": len(val_rows),
            "test_novel": str(novel_manifest),
            "test_novel_rows": len(novel_rows),
            "unseen_terms": str(unseen_path),
        },
        "conditions": {},
    }
    for name, runs in conditions.items():
        for key, path in runs.items():
            if path is not None and not path.is_file():
                raise FileNotFoundError(path)
        all_results["conditions"][name] = {
            "devuser": evaluate(runs["devuser"], dev_rows, dev_durations, unseen_terms),
            "devuser_no_unseen": (
                evaluate(runs["devuser_no_unseen"], dev_rows, dev_durations, unseen_terms)
                if runs["devuser_no_unseen"] is not None else None
            ),
            "val": evaluate(runs["val"], val_rows, val_durations),
            "test_novel": evaluate(runs["test_novel"], novel_rows, novel_durations),
        }

    out = new / "corrected-all-results-mainselector21-20261123"
    out.mkdir(parents=True, exist_ok=True)
    (out / "aggregate.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "| 条件 | 本人50件 CER / 用語 | 見えない用語除外 CER / 用語 | val CER / 用語 | test-novel CER / 正答 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, values in all_results["conditions"].items():
        lines.append(
            f"| {name} | {result_cell(values['devuser'])} | "
            f"{result_cell(values['devuser_no_unseen'])} | "
            f"{result_cell(values['val'])} | {result_cell(values['test_novel'])} |"
        )
    lines += [
        "",
        "SFT3各モデルはTransformers BF16で同じASR入力とmainの動的用語選択を使った。SFT2は保存済みMLX 4bit出力。",
        "本人50件は修正版manifestのうち、旧評価と同じIDを使った。本人の行別予測はfacultyに保存し、集計値だけを記録した。",
        "",
    ]
    (out / "table.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(out), "conditions": len(conditions)}, indent=2))


if __name__ == "__main__":
    main()
