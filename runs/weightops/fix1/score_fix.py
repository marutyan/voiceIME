"""保存済みの評価出力を、読み復元なし・ありで採点し、初見語の取りこぼしの内訳を数える。GPUは使わない。

標準の一覧（r2と同じ）と、PMの容量評価の一覧（上限20/32/48、Haas 1回目＋Qwen 0.6Bで選択）の両方を扱う。
"""

import json
from collections import Counter
from pathlib import Path

from restore_main import restore_listed_readings
from voiceime.eval.metrics import calculate_cer, calculate_term_accuracy
from voiceime.formatter.glossary import entry_from_record

HOME = Path.home()
WORK = HOME / "voiceime-work-wops"
FR3 = HOME / "voiceime-work-fr3/inputs"
MANIFESTS = {
    "val": FR3 / "manifest-val-no-audio.jsonl",
    "test-novel": FR3 / "test-novel-20261122/test-novel.jsonl",
}
STANDARD_LISTS = {
    "val": FR3 / "d-multiasr-20261123/val-runs/formatter-glossary.jsonl",
    "test-novel": HOME / "voiceime-work-asr/r3-multiasr-20261122/outputs/formatter-glossary-qwen06-test-novel.jsonl",
}
CAPACITY_LISTS = FR3 / "glossary-capacity-20261123-corrected/glossaries"
STANDARD_RUNS = {
    "soup-a050": WORK / "runs/soup-a050/multiasr",
    "RSI-0.8B": WORK / "runs/rsi1/RSI-0.8B/multiasr",
    "RSI-2B": WORK / "runs/rsi1/RSI-2B/multiasr",
    "D-2B-drop0.075": Path("/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123/D-2B-drop0.075/multiasr"),
    "FIX-0.8B-scratch": WORK / "runs/fix1/FIX-0.8B-scratch/multiasr",
    "FIX-0.8B-cont": WORK / "runs/fix1/FIX-0.8B-cont/multiasr",
}
CAPACITY_MODELS = ("soup-a050", "RSI-0.8B", "FIX-0.8B-scratch", "FIX-0.8B-cont")
CAPACITY_VARIANTS = ("max20-haas-qwen", "max32-haas-qwen", "max48-haas-qwen")


def read_rows(path):
    """JSONLを順序どおりに読む。"""
    with open(path, encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def score(run_path, split, list_path):
    """1つの評価出力を採点する。行ごとに、評価時の一覧が指定の一覧と同じことを確かめる。"""
    gold = read_rows(MANIFESTS[split])
    lists = {r["id"]: [entry_from_record(e) for e in r["glossary"]] for r in read_rows(list_path)}
    rows = {r["id"]: r for r in read_rows(run_path)}
    if set(rows) != {g["id"] for g in gold}:
        raise ValueError(f"{run_path}: manifestとIDが一致しません")
    hyps = {"raw": [], "restored": []}
    counts = {"raw": Counter(), "restored": Counter()}
    for sample in gold:
        row = rows[sample["id"]]
        entries = lists[sample["id"]]
        if row["glossary"] != [e.surface for e in entries]:
            raise ValueError(f"{run_path} {sample['id']}: 評価時の一覧が指定の一覧と違います")
        listed = set(row["glossary"])
        merged = row["input_text"]["combined_text"] or ""
        for mode, hyp in (("raw", row["hyp"]), ("restored", restore_listed_readings(row["hyp"], entries))):
            hyps[mode].append(hyp)
            c = counts[mode]
            c["correct"] += calculate_term_accuracy(sample["terms"], sample.get("glossary", []), hyp)["correct"]
            c["terms"] += len(sample["terms"])
            for term, occurrences in Counter(sample["terms"]).items():
                missed = occurrences - min(hyp.count(term), occurrences)
                c["missed"] += missed
                # 一覧に表記がある、またはsegment-merge後の文に表記があるのに、出力に無かった数。
                c["missed_listed"] += missed if term in listed else 0
                c["missed_in_merge"] += missed if term in merged else 0
    references = [g["target_text"] for g in gold]
    return {mode: {"cer": calculate_cer(references, hyps[mode]), **dict(counts[mode])} for mode in hyps}


def main():
    """存在する評価出力をすべて採点し、JSONで書き出す。"""
    result = {"standard": {}, "capacity": {}}
    for model, directory in STANDARD_RUNS.items():
        for split in MANIFESTS:
            path = directory / f"{split}-segment-merge.jsonl"
            if path.exists():
                result["standard"].setdefault(model, {})[split] = score(path, split, STANDARD_LISTS[split])
    for model in CAPACITY_MODELS:
        for split in MANIFESTS:
            for variant in CAPACITY_VARIANTS:
                path = WORK / f"runs/capacity/{model}/inference/{split}-{variant}.jsonl"
                if path.exists():
                    result["capacity"].setdefault(model, {}).setdefault(split, {})[variant] = score(
                        path, split, CAPACITY_LISTS / split / f"{variant}.jsonl")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
