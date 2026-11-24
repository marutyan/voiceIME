"""学習コードから全行を1回取り出し、omitted語とVAR拡張の条件を検証する。"""

import json
import multiprocessing
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
import train_fix
import train_support
from fix_omitted_terms import has_surface, in_list, reading_spans
from make_variants import AUG, FULL, RUNS, read_inputs, records

DATASETS = []


class Captured(Exception):
    """学習用Datasetを作った時点でTrainerの起動を止める。"""


def capture_concat(datasets):
    """元データと拡張データのDatasetを受け取る。"""
    DATASETS.extend(datasets)
    raise Captured


def capture_pair(_tokenizer, inputs, glossary, target, _max_length):
    """トークン化直前の値を監査へ返す。"""
    return inputs, glossary, target


def check_range(task):
    """固定seedで担当範囲を取り出し、fix1と同じ条件で数える。"""
    dataset_index, start, stop = task
    torch.manual_seed(1000 * dataset_index + start)
    dataset = DATASETS[dataset_index]
    counts = Counter(rows=0, omitted_rows=0, listed_but_target_reading=0,
                     merged_but_target_reading=0, target_surface_without_list_or_merge=0,
                     literal_surface_only=0)
    for index in range(start, stop):
        inputs, glossary, target = dataset[index]
        counts["rows"] += 1
        row = dataset.rows[index]
        if not row.get("omitted_terms"):
            continue
        entries = [{"surface": entry.surface} for entry in glossary]
        for term in row["omitted_terms"]:
            surface = term["surface"]
            listed = in_list(entries, surface)
            merged = has_surface(inputs.combined_text, surface)
            written = has_surface(target, surface)
            reading = bool(reading_spans(target, term["readings"]))
            counts["omitted_rows"] += 1
            counts["listed_but_target_reading"] += listed and not written and reading
            counts["merged_but_target_reading"] += merged and not written and reading
            counts["target_surface_without_list_or_merge"] += written and not (listed or merged)
            counts["literal_surface_only"] += surface in target and not written
    return dataset_index, counts


def check_augmentation(augmented):
    """全拡張行を元データと照合し、正解の変形や既存拡張の差分を検出する。"""
    original = {row["id"]: row for row in records(FULL / "train-fixed.jsonl")}
    train_run = FULL / "train-runs"
    inputs, lists = read_inputs(train_run, train_run / "formatter-glossary.jsonl")
    counts = Counter()
    ids = set()
    with augmented.open("rb") as current, AUG.open("rb") as previous:
        for line in previous:
            if line != current.readline():
                raise ValueError("既存の用語差し替え拡張が変わりました")
            row = json.loads(line)
            ids.add(row["id"])
            counts["existing_augmentation"] += 1
        for line in current:
            row = json.loads(line)
            sample_id = row["source_id"]
            source = original[sample_id]
            if (row["id"] in ids or source.get("omitted_terms") or row.get("omitted_terms")
                    or row["target_text"] != source["target_text"] or row["terms"] != source["terms"]):
                raise ValueError(f"{row['id']}: ID・omitted語または正解文に不一致")
            ids.add(row["id"])
            changed = sum(row[field] != inputs[field][sample_id] for field in RUNS)
            before = lists[sample_id]
            after = row["glossary"]
            before_terms = {e["surface"] for e in before}
            after_terms = {e["surface"] for e in after}
            if row["id"].startswith("var-positive-"):
                if before != after or not changed:
                    raise ValueError(f"{row['id']}: 正例の変更が入力だけに限られていません")
                counts["positive"] += 1
            elif row["id"].startswith("var-negative-"):
                if (changed or len(after) > 20 or len(after_terms - before_terms) != 1
                        or (after_terms - before_terms).intersection(row["terms"])
                        or (before_terms - after_terms).intersection(row["terms"])):
                    raise ValueError(f"{row['id']}: 負例の変更が不正です")
                counts["negative"] += 1
            else:
                raise ValueError(f"{row['id']}: 不明な拡張種別")
    if counts != {"existing_augmentation": 36778, "positive": 24000, "negative": 9600}:
        raise ValueError(f"拡張件数が想定と違います: {counts}")
    return counts


def main():
    """学習と同じ引数でDatasetを作り、CPUで取り出し監査を行う。"""
    output = Path(sys.argv[1])
    sys.argv = [train_fix.__file__, *sys.argv[2:]]
    args = train_fix.parse_args()
    train_fix.tokenize_pair = capture_pair
    train_support.tokenize_pair = capture_pair
    fake_model = SimpleNamespace(config=SimpleNamespace(), gradient_checkpointing_enable=lambda: None)
    with (
        patch.object(train_fix.AutoModelForCausalLM, "from_pretrained", return_value=fake_model),
        patch.object(torch.utils.data, "ConcatDataset", capture_concat),
    ):
        try:
            train_fix.main()
        except Captured:
            pass
    counts = [Counter(), Counter()]
    ranges = [(i, start, min(start + 2000, len(dataset))) for i, dataset in enumerate(DATASETS)
              for start in range(0, len(dataset), 2000)]
    with multiprocessing.get_context("fork").Pool(16) as pool:
        for i, part in pool.imap(check_range, ranges):
            counts[i].update(part)
    total = counts[0].copy()
    total.update(counts[1])
    result = {"train": counts[0], "augmentation": counts[1], "total": total,
              "augmentation_source_check": check_augmentation(Path(args.augmentation))}
    if any(total[k] for k in ("listed_but_target_reading", "merged_but_target_reading",
                              "target_surface_without_list_or_merge")):
        raise ValueError(f"omitted語の条件に違反します: {result}")
    with output.open("x") as sink:
        json.dump(result, sink, ensure_ascii=False, indent=2)
        sink.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
