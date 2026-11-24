"""学習用Datasetの全行を1回ずつ取り出し、一覧に無いomitted語の正解表記を数える。"""

import json
import multiprocessing
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
import train_rsi
import train_support
from fix_omitted_terms import has_surface, surface_key
from voiceime.formatter.style import apply_output_style

DATASETS = []


class Captured(Exception):
    """学習用Datasetを受け取ったところで学習処理を打ち切る。"""


def capture_concat(datasets):
    """元データと拡張データを受け取り、Trainerの初期化前に止める。"""
    DATASETS.extend(datasets)
    raise Captured


def capture_pair(_tokenizer, inputs, glossary, target, _max_length):
    """実際のDatasetがトークン化へ渡す一覧と、整形後の正解文を返す。"""
    return inputs.combined_text, glossary, apply_output_style(target)


def check_range(task):
    """担当範囲を一度取り出し、omitted語と一覧・結合文の関係を集計する。"""
    dataset_index, start, stop = task
    torch.manual_seed(1000 * dataset_index + start)
    dataset = DATASETS[dataset_index]
    counts = Counter(rows=0, omitted_rows=0, target_without_surface=0,
                     target_surface_without_list=0, target_surface_without_list_or_merge=0,
                     changed_relative_to_fix1_sample=0)
    for index in range(start, stop):
        combined, glossary, target = dataset[index]
        counts["rows"] += 1
        row = dataset.rows[index]
        if not row.get("omitted_terms"):
            continue
        term, = row["omitted_terms"]
        surface = term["surface"]
        counts["omitted_rows"] += 1
        if surface not in target:
            counts["target_without_surface"] += 1
            continue
        listed = any(surface_key(entry.surface) == surface_key(surface) for entry in glossary)
        cue = listed or has_surface(combined, surface)
        counts["target_surface_without_list"] += not listed
        counts["target_surface_without_list_or_merge"] += not cue
        reason = row["omitted_fix"]
        counts["changed_relative_to_fix1_sample"] += (
            reason == "rule3-no-cue" or (reason == "rule4-rewrite-if-cue" and not cue)
        )
    return dataset_index, counts


def main():
    """共通の学習引数でDatasetを作り、GPUと重みを使わず全行を監査する。"""
    output = Path(sys.argv[1])
    sys.argv = [train_rsi.__file__, *sys.argv[2:]]
    placeholder = SimpleNamespace(config=SimpleNamespace(), gradient_checkpointing_enable=lambda: None)
    with (
        patch.object(train_rsi.AutoModelForCausalLM, "from_pretrained", return_value=placeholder),
        patch.object(torch.utils.data, "ConcatDataset", capture_concat),
    ):
        try:
            train_rsi.main()
        except Captured:
            pass

    tasks = []
    for dataset_index, dataset in enumerate(DATASETS):
        size = len(dataset)
        tasks.extend((dataset_index, start, min(start + 2000, size)) for start in range(0, size, 2000))
    counts = [Counter(), Counter()]
    with multiprocessing.get_context("fork").Pool(16) as pool:
        for dataset_index, part in pool.imap(check_range, tasks):
            counts[dataset_index].update(part)
    result = dict(zip(("train", "augmentation"), counts, strict=True))
    result["total"] = counts[0] + counts[1]
    for group in result.values():
        group["target_surface_without_list_rate"] = group["target_surface_without_list"] / group["omitted_rows"]
    if result["total"]["target_without_surface"]:
        raise ValueError(f"正解文に表記がない行があります: {result}")
    with output.open("x") as sink:
        json.dump(result, sink, ensure_ascii=False, indent=2)
        sink.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    train_rsi.tokenize_pair = capture_pair
    train_support.tokenize_pair = capture_pair
    main()
