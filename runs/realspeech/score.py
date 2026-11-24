#!/usr/bin/env python3
"""固定用語一覧を照合し、読みの復元あり・なしで整形結果を集計する。"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from prepare import FR3, NOVEL, PUB_EVAL, ROOT, read_rows, write_stats
from voiceime.eval.metrics import calculate_cer, calculate_filler_metrics, calculate_term_accuracy
from voiceime.formatter.glossary import entry_from_record, load_glossary
from voiceime.formatter.restore import restore_listed_readings

NOVEL_DIR = NOVEL.parent
D_INPUT = FR3 / "inputs/d-multiasr-20261123"
MULTIASR = Path.home() / "voiceime-work-asr/r3-multiasr-20261122/outputs"
WORK_WOPS = Path.home() / "voiceime-work-wops"
SPLITS = {
    "val": (
        FR3 / "inputs/manifest-val-no-audio.jsonl",
        D_INPUT / "val-runs/formatter-glossary.jsonl", 1000, 1427,
    ),
    "test-novel": (NOVEL, MULTIASR / "formatter-glossary-qwen06-test-novel.jsonl", 500, 500),
    "pub-eval": (PUB_EVAL, ROOT / "pub-eval-inputs/formatter-glossary.jsonl", 300, 381),
}


def score_split(manifest, outputs, glossary, split, novel_exposed):
    """同じ応答を後処理前後で比較し、用語と文字誤りの内訳を返す。"""
    assert [row["id"] for row in manifest] == [row["id"] for row in outputs]
    references = [row["target_text"] for row in manifest]
    predictions = [row["hyp"] for row in outputs]
    restored = [
        restore_listed_readings(row["hyp"], glossary[row["id"]])
        for row in outputs
    ]
    result = {}
    for mode, texts in (("raw", predictions), ("restore", restored)):
        terms = Counter()
        for ref, text in zip(manifest, texts, strict=True):
            listed = {entry.surface for entry in glossary[ref["id"]]}
            for name, expected in (
                ("all", ref["terms"]),
                ("listed", [term for term in ref["terms"] if term in listed]),
                ("unlisted", [term for term in ref["terms"] if term not in listed]),
                ("novel_without_surface_exposure", [term for term in ref["terms"] if term not in novel_exposed]),
            ):
                if name == "novel_without_surface_exposure" and split != "test-novel":
                    continue
                stats = calculate_term_accuracy(expected, ref["glossary"], text)
                terms[f"{name}_exact"] += stats["correct"]
                terms[f"{name}_loose"] += stats["loose_correct"]
                terms[f"{name}_total"] += stats["total"]
        result[mode] = {"cer": calculate_cer(references, texts), "terms": dict(terms)}
        if split != "pub-eval":
            result[mode]["fillers"] = calculate_filler_metrics(
                references, texts, [row["fillers"] for row in manifest]
            )
    result["rows_changed_by_restore"] = sum(
        before != after for before, after in zip(predictions, restored, strict=True)
    )
    result["rows"] = len(manifest)
    return result


def main():
    """モデルごとの実測値と、評価を再現する入力のハッシュを保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=["RSI-0.8B", "REAL-0.8B"])
    parser.add_argument("--existing-rsi", action="store_true")
    args = parser.parse_args()
    full = {entry.surface: entry for entry in load_glossary(
        NOVEL_DIR / "glossary-v1.jsonl", NOVEL_DIR / "glossary-v2.jsonl"
    )}
    # test-novelの追加集計は、実音声行に現れた表記を除いた共通分母で行う。
    exposure = set()
    path = ROOT / "stats/REAL-0.8B.json"
    if path.is_file():
        info = json.loads(path.read_text())
        exposure.update(info["test_novel_surfaces_in_real_targets"])
        exposure.update(info["test_novel_surfaces_in_real_asr"])
    result = {}
    for split, (manifest_path, glossary_path, count, term_count) in SPLITS.items():
        if args.existing_rsi and split == "pub-eval":
            continue
        if args.model == "RSI-0.8B" and split != "pub-eval":
            prediction_path = WORK_WOPS / "runs/rsi1/RSI-0.8B/multiasr" / f"{split}-segment-merge.jsonl"
            metadata = json.loads(prediction_path.with_suffix(".summary.json").read_text())
            assert Path(metadata["model"]) == WORK_WOPS / "outputs/RSI-0.8B/best"
        else:
            prediction_path = ROOT / "eval" / args.model / f"{split}.jsonl"
        manifest = read_rows(manifest_path)
        if split == "pub-eval":
            # 前回のpub-evalと同様に、カタカナ字幕の用語33回も用語分母に含める。
            for row in manifest:
                row["terms"] = row["terms"] + row["terms_katakana_in_caption"]
        output = read_rows(prediction_path)
        assert len(manifest) == len(output) == count
        if term_count is not None:
            assert sum(len(row["terms"]) for row in manifest) == term_count
        structured = {
            row["id"]: [
                full[entry] if isinstance(entry, str) else entry_from_record(entry)
                for entry in row["glossary"]
            ]
            for row in read_rows(glossary_path)
        }
        assert all(row["glossary"] == [entry.surface for entry in structured[row["id"]]] for row in output)
        result[split] = score_split(manifest, output, structured, split, exposure)
        result[split]["files"] = {
            name: {"path": str(path), "sha256": hashlib.file_digest(path.open("rb"), "sha256").hexdigest()}
            for name, path in (
                ("manifest", manifest_path), ("selector", glossary_path), ("predictions", prediction_path)
            )
        }
    write_stats(f"{args.model}-{'existing' if args.existing_rsi else 'eval'}", result)


if __name__ == "__main__":
    main()
