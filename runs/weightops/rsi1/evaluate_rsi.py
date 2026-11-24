"""条件Dの保存済み出力を、元の指標とmainの読み復元の両方で集計する。"""

import hashlib
import json
from collections import Counter
from pathlib import Path

import restore_main
from restore_main import restore_listed_readings
from voiceime.eval.metrics import calculate_cer, calculate_term_accuracy
from voiceime.formatter.glossary import entry_from_record

RESTORE_SHA256 = "0720286bea3a569a922a2c4452e26d32645adf0fd9691390763721d9ebd67a18"
BASELINE_NAMES = ("soup-a050", "D-2B-drop0.075")
RI_NAMES = ("RSI-0.8B", "RSI-2B")
FIELDS = ("input_text", "glossary", "prompt_token_count")


def read_rows(path):
    """保存済みの行を読み込み、元ファイルの順序を保つ。"""
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def audit_input(row, source, reference, entries):
    """同一のASRと、同じ読み付き一覧が使われたことを確認する。"""
    if row["id"] != source["id"] or row["id"] != reference["id"]:
        raise ValueError("manifest、条件Dと比較runのIDが一致しません")
    if any(row[field] != reference[field] for field in FIELDS):
        raise ValueError(f"{row['id']}: 条件Dと比較runの入力が一致しません")
    if row["glossary"] != [entry.surface for entry in entries]:
        raise ValueError(f"{row['id']}: 読み復元用の一覧と評価時の一覧が一致しません")


def model_result(rows, gold, glossaries, reference):
    """同じ行ごとの入力を使って、復元前後のCERと用語を集計する。"""
    originals, restored = [], []
    term_counts = {"raw": Counter(), "restored": Counter()}
    for row, sample, baseline in zip(rows, gold, reference, strict=True):
        entries = glossaries[sample["id"]]
        audit_input(row, sample, baseline, entries)
        originals.append(row["hyp"])
        restored.append(restore_listed_readings(row["hyp"], entries))
        listed = set(row["glossary"])
        expected = Counter(sample["terms"])
        for mode, hypothesis in (("raw", originals[-1]), ("restored", restored[-1])):
            counts = term_counts[mode]
            for term, occurrences in expected.items():
                group = "listed" if term in listed else "unlisted"
                counts[group] += occurrences
                counts[f"{group}_correct"] += min(hypothesis.count(term), occurrences)
            correct = calculate_term_accuracy(sample["terms"], sample.get("glossary", []), hypothesis)["correct"]
            counts["correct"] += correct
            counts["terms"] += len(sample["terms"])
    references = [row["target_text"] for row in gold]
    summary = {}
    for mode, output in (("raw", originals), ("restored", restored)):
        counts = term_counts[mode]
        if counts["correct"] != counts["listed_correct"] + counts["unlisted_correct"]:
            raise ValueError("用語の内外集計と既存の用語指標が一致しません")
        summary[mode] = {"cer": calculate_cer(references, output), **dict(counts)}
    summary["rows_changed_by_restore"] = sum(a != b for a, b in zip(originals, restored, strict=True))
    return summary, {"raw": originals, "restored": restored}


def examples(old, new, gold, rows, glossaries):
    """同じ後処理条件で、取得・失敗へ変わった例をID順で最大10件ずつ採る。"""
    examples = {}
    for mode in ("raw", "restored"):
        outcomes = Counter()
        directions = {"gained": [], "lost": []}
        matched = zip(gold, rows, old[mode], new[mode], strict=True)
        for g, row, before, after in matched:
            term, = g["terms"]
            changes = (term in before, term in after)
            key = {
                (False, True): "gained", (True, False): "lost",
                (True, True): "both_correct", (False, False): "both_wrong",
            }[changes]
            outcomes[key] += 1
            if key not in directions or len(directions[key]) == 10:
                continue
            entries = glossaries[g["id"]]
            relevant = [entry for entry in entries if entry.surface == term
                        or (entry.surface in before) != (entry.surface in after)]
            directions[key].append({
                "id": g["id"], "term": term, "inputs": row["input_text"],
                "listed": term in row["glossary"],
                "glossary": [{"surface": e.surface, "readings": e.readings} for e in relevant],
                "baseline": before, "rsi": after, "target": g["target_text"],
            })
        examples[mode] = {"counts": dict(outcomes), **directions}
    return examples


def evaluate():
    """GPUを使わず、逐次保存済みの2 split、最大4モデルに対して再集計する。"""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baselines-only", action="store_true")
    args = parser.parse_args()
    restore_path = Path(restore_main.__file__)
    if hashlib.sha256(restore_path.read_bytes()).hexdigest() != RESTORE_SHA256:
        raise ValueError("mainの読み復元コードと一致しません")
    home = Path.home()
    work = home / "voiceime-work-wops"
    legacy = home / "voiceime-work-fr3/inputs"
    manifest_paths = {
        "val": legacy / "manifest-val-no-audio.jsonl",
        "test-novel": legacy / "test-novel-20261122/test-novel.jsonl",
    }
    glossary_paths = {
        "val": legacy / "d-multiasr-20261123/val-runs/formatter-glossary.jsonl",
        "test-novel": home / "voiceime-work-asr/r3-multiasr-20261122/outputs/formatter-glossary-qwen06-test-novel.jsonl",
    }
    models = {
        "soup-a050": work / "runs/soup-a050/multiasr",
        "D-2B-drop0.075": Path("/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123/D-2B-drop0.075/multiasr"),
    }
    if not args.baselines_only:
        models.update({name: work / f"runs/rsi1/{name}/multiasr" for name in RI_NAMES})
    result = {"restore_code_sha256": RESTORE_SHA256, "models": {}, "test_novel_examples": {}}
    for split, manifest in manifest_paths.items():
        gold = read_rows(manifest)
        assert all(row["source"] in {"synthetic-tts", "synthetic-tts-ja", "synthetic-tts-multi"} for row in gold)
        glossaries = {r["id"]: [entry_from_record(entry) for entry in r["glossary"]]
                      for r in read_rows(glossary_paths[split])}
        name = f"{split}-segment-merge.jsonl"
        reference = read_rows(models["soup-a050"] / name)
        result["models"][split] = {}
        predictions = {}
        for model, directory in models.items():
            summary, output = model_result(read_rows(directory / name), gold, glossaries, reference)
            result["models"][split][model] = summary
            predictions[model] = output
        if split == "test-novel" and not args.baselines_only:
            for baseline, model in zip(BASELINE_NAMES, RI_NAMES, strict=True):
                result["test_novel_examples"][model] = examples(
                    predictions[baseline], predictions[model], gold, reference, glossaries,
                )
    if not args.baselines_only:
        result["training"] = {
            name: json.loads((work / "outputs" / name / "train_summary.json").read_text())
            for name in RI_NAMES
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    evaluate()
