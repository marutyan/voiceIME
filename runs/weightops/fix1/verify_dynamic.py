"""学習コードが実際に作る入力・一覧・正解文を全行1回ずつ取り出し、omitted語の食い違いが0件かを確かめる。

学習中にselectorが一覧を作る行と、無作為に混ぜる語は事前の一覧から確かめられないため、
train_fix.pyのデータセットをそのまま使い、トークン化の直前の値を集める。GPUは使わない。
"""

import json
import multiprocessing
import sys
from collections import Counter

import torch

import train_fix
import train_support
from fix_omitted_terms import has_surface, in_list, reading_spans

DATASETS = []


class Captured(Exception):
    """学習用データセットを作った時点で学習の準備を止めるための例外。"""


def capture_concat(datasets):
    """元行と拡張行のデータセットを受け取り、学習を始めずに止める。"""
    DATASETS.extend(datasets)
    raise Captured


def capture_pair(_tokenizer, inputs, glossary, target, _max_length):
    """トークン化の代わりに、整形器へ渡す3入力・一覧・正解文を返す。"""
    texts = [inputs] if isinstance(inputs, str) else [
        inputs.first_pass, inputs.second_pass, inputs.combined_text, inputs.qwen_hypothesis]
    entries = [{"surface": e.surface, "readings": list(e.readings)} for e in glossary]
    combined = inputs if isinstance(inputs, str) else inputs.combined_text
    return {"texts": [t for t in texts if t], "combined": combined, "glossary": entries, "target": target}


def check_range(task):
    """担当範囲の行を取り出し、omitted語ごとに一覧・入力・正解文の関係を数える。"""
    dataset_index, start, stop = task
    torch.manual_seed(1000 * dataset_index + start)
    dataset = DATASETS[dataset_index]
    rows = dataset.rows
    counts = Counter()
    examples = []
    for index in range(start, stop):
        row = rows[index]
        omitted = [t for t in row.get("omitted_terms", [])]
        if not omitted:
            continue
        sample = dataset[index]
        counts["omitted_rows"] += 1
        for term in omitted:
            surface = term["surface"]
            listed = in_list(sample["glossary"], surface)
            target_has_surface = has_surface(sample["target"], surface)
            target_has_reading = bool(reading_spans(sample["target"], term["readings"]))
            counts[f"listed={listed},target_surface={target_has_surface}"] += 1
            if listed and not target_has_surface and target_has_reading:
                counts["violation_list_surface_target_reading"] += 1
                if len(examples) < 10:
                    examples.append({"id": row["id"], "surface": surface, "target": sample["target"]})
            # 規則2の手掛かり（一覧かsegment-merge後の文）が無いのに表記を書く例も数える。
            cue = listed or has_surface(sample["combined"], surface)
            if target_has_surface and not cue:
                counts["target_surface_without_list_or_merge"] += 1
            if not target_has_surface and target_has_reading and any(
                    has_surface(text, surface) for text in sample["texts"]):
                counts["katakana_target_but_surface_in_asr_inputs"] += 1
    return counts, examples


def main():
    """学習と同じ引数でデータセットを作り、全行を並列に調べて結果を書く。"""
    output = sys.argv[1]
    sys.argv = ["train_fix.py", *sys.argv[2:]]
    train_fix.tokenize_pair = capture_pair
    train_support.tokenize_pair = capture_pair
    torch.utils.data.ConcatDataset = capture_concat
    try:
        train_fix.main()
    except Captured:
        pass
    tasks = []
    for dataset_index, dataset in enumerate(DATASETS):
        size = len(dataset.rows)
        tasks += [(dataset_index, start, min(start + 2000, size)) for start in range(0, size, 2000)]
    counts = [Counter(), Counter()]
    examples = []
    with multiprocessing.get_context("fork").Pool(48) as pool:
        for (dataset_index, _, _), (part, found) in zip(tasks, pool.map(check_range, tasks), strict=True):
            counts[dataset_index] += part
            examples += found
    result = {"original": dict(counts[0]), "augmentation": dict(counts[1]), "violation_examples": examples[:10]}
    with open(output, "w", encoding="utf-8") as sink:
        json.dump(result, sink, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
