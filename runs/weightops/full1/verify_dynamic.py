"""学習用Datasetを全行1回取り出し、omitted語と一覧のdropを監査する。"""

import json
import multiprocessing
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
import train_fix
import train_full_drop
import train_support
from drop_seen import drop_seen_terms
from fix_omitted_terms import has_surface, in_list, reading_spans

DATASETS = []
DROP_TRACE = None


class Captured(Exception):
    """データセットを受け取った時点で終了し、学習を始めない。"""


def capture_concat(datasets):
    """元行と拡張行のDatasetを捕まえる。"""
    DATASETS.extend(datasets)
    raise Captured


def capture_pair(_tokenizer, inputs, glossary, target, _max_length):
    """トークン化直前の入力、一覧、正解文をそのまま返す。"""
    return inputs, glossary, target


def trace_drop(glossary, terms, target, eligible, probability, rng):
    """学習と同じdropを実行し、候補と実際に抜いた語を記録する。"""
    global DROP_TRACE
    after = drop_seen_terms(glossary, terms, target, eligible, probability, rng)
    before_surfaces = {entry.surface for entry in glossary}
    candidates = before_surfaces.intersection(terms, eligible)
    candidates = {term for term in candidates if term in target}
    removed = before_surfaces - {entry.surface for entry in after}
    if removed - candidates:
        raise ValueError("対象外の語が一覧から抜けました")
    DROP_TRACE = glossary, candidates, removed
    return after


def check_omitted(row, inputs, glossary, target, counts):
    """fix1と同じ一致条件で、取り出した一覧・結合文・正解文を照合する。"""
    if not row.get("omitted_terms"):
        return
    term, = row["omitted_terms"]
    surface = term["surface"]
    entries = [{"surface": entry.surface} for entry in glossary]
    listed = in_list(entries, surface)
    merged = has_surface(inputs.combined_text, surface)
    written = has_surface(target, surface)
    reading = bool(reading_spans(target, term["readings"]))
    counts["omitted_rows"] += 1
    counts[f"listed={listed},target_surface={written}"] += 1
    counts["listed_but_target_reading"] += listed and not written and reading
    counts["merged_but_target_reading"] += merged and not written and reading
    counts["target_surface_without_list_or_merge"] += written and not (listed or merged)
    # 短い表記が英数字の続く位置に現れ、語境界付き照合では拾えない行も別に数える。
    counts["literal_surface_only"] += surface in target and not written


def check_range(task):
    """固定seedで範囲を走査し、drop前後と元のDatasetの一致を確かめる。"""
    dataset_index, start, stop = task
    torch.manual_seed(1000 * dataset_index + start)
    dataset = DATASETS[dataset_index]
    counts = Counter(rows=0, eligible_rows=0, eligible_terms=0, dropped_rows=0, dropped_terms=0,
                     dropped_on_real_asr_rows=0, dropped_without_merge_terms=0,
                     omitted_rows=0, listed_but_target_reading=0, merged_but_target_reading=0,
                     target_surface_without_list_or_merge=0, literal_surface_only=0)
    for index in range(start, stop):
        check_baseline = dataset_index == 0 and index == start
        if check_baseline:
            initial_rng = torch.random.get_rng_state()
        inputs, glossary, target = dataset[index]
        row = dataset.rows[index]
        counts["rows"] += 1
        if dataset_index == 0:
            before, candidates, removed = DROP_TRACE
            counts["eligible_rows"] += bool(candidates)
            counts["eligible_terms"] += len(candidates)
            counts["dropped_rows"] += bool(removed)
            counts["dropped_terms"] += len(removed)
            counts["dropped_on_real_asr_rows"] += bool(removed) and dataset.nohint_hyps[index] is not None
            counts["dropped_without_merge_terms"] += sum(
                not has_surface(inputs.combined_text, term) for term in removed
            )
            if check_baseline:
                next_rng = torch.random.get_rng_state()
                torch.random.set_rng_state(initial_rng)
                baseline = train_fix.FormatterDataset.__getitem__(dataset, index)
                torch.random.set_rng_state(next_rng)
                if baseline != (inputs, before, target):
                    raise ValueError(f"{row['id']}: drop前の出力がfix1のDatasetと違います")
                counts["baseline_comparisons"] += 1

            if row.get("omitted_terms") and any(
                in_list([{"surface": entry.surface} for entry in before], term["surface"])
                != in_list([{"surface": entry.surface} for entry in glossary], term["surface"])
                for term in row["omitted_terms"]
            ):
                raise ValueError(f"{row['id']}: dropでomitted語の一覧が変わりました")
        check_omitted(row, inputs, glossary, target, counts)
    return dataset_index, counts


def main():
    """学習と同じデータ引数で作ったDatasetをCPUで監査する。"""
    output = Path(sys.argv[1])
    sys.argv = [train_full_drop.__file__, *sys.argv[2:]]
    train_full_drop.tokenize_pair = capture_pair
    train_fix.tokenize_pair = capture_pair
    train_support.tokenize_pair = capture_pair
    train_full_drop.drop_seen_terms = trace_drop
    placeholder = SimpleNamespace(config=SimpleNamespace(), gradient_checkpointing_enable=lambda: None)
    with (
        patch.object(train_full_drop.AutoModelForCausalLM, "from_pretrained", return_value=placeholder),
        patch.object(torch.utils.data, "ConcatDataset", capture_concat),
    ):
        try:
            train_full_drop.main()
        except Captured:
            pass
    tasks = [(i, start, min(start + 2000, len(dataset)))
             for i, dataset in enumerate(DATASETS) for start in range(0, len(dataset), 2000)]
    counts = [Counter(), Counter()]
    with multiprocessing.get_context("fork").Pool(16) as pool:
        for i, part in pool.imap(check_range, tasks):
            counts[i].update(part)
    total = counts[0].copy()
    total.update(counts[1])
    result = {"train": counts[0], "augmentation": counts[1], "total": total}
    result["rates"] = {
        "dropped_per_original_row": counts[0]["dropped_rows"] / counts[0]["rows"],
        "dropped_per_all_rows": total["dropped_rows"] / total["rows"],
        "dropped_per_eligible_row": total["dropped_rows"] / total["eligible_rows"],
        "dropped_per_eligible_term": total["dropped_terms"] / total["eligible_terms"],
    }
    if any(total[k] for k in ("listed_but_target_reading", "target_surface_without_list_or_merge")):
        raise ValueError(f"omitted語の条件に違反します: {result}")
    with output.open("x") as sink:
        json.dump(result, sink, ensure_ascii=False, indent=2)
        sink.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
