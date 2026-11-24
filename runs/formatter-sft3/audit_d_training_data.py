#!/usr/bin/env python3
"""D学習のASR対応、用語選択範囲、held-out分離を監査する。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


RUN_FILES = (
    "first-pass.jsonl",
    "second-pass-plain.jsonl",
    "segment-merge.jsonl",
    "qwen06-hypothesis.jsonl",
    "formatter-glossary.jsonl",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、object以外を拒否する。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(row)
    return rows


def unique_ids(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """ID順とID辞書を返し、空IDと重複を拒否する。"""
    rows = read_jsonl(path)
    ids = [row.get("id") for row in rows]
    if not all(isinstance(sample_id, str) and sample_id for sample_id in ids):
        raise ValueError(f"{path}: idは空でない文字列である必要があります")
    by_id = dict(zip(ids, rows, strict=True))
    if len(by_id) != len(rows):
        raise ValueError(f"{path}: idが重複しています")
    return ids, by_id


def sha256(path: Path) -> str:
    """再現性確認用にファイルのSHA-256を返す。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def term_set(path: Path) -> set[str]:
    """1行1語の除外・初見語ファイルを読む。"""
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def verify_runs(directory: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """1つのsplitにある全runのID集合と順序が同じことを検証する。"""
    reference_ids = None
    reference_rows = None
    for name in RUN_FILES:
        path = directory / name
        ids, rows = unique_ids(path)
        if reference_ids is None:
            reference_ids, reference_rows = ids, rows
        elif ids != reference_ids:
            raise ValueError(f"{directory}: {name}のIDまたは順序が一致しません")
    assert reference_ids is not None and reference_rows is not None
    for name in RUN_FILES[:-1]:
        for sample_id, row in unique_ids(directory / name)[1].items():
            allow_empty = name == "segment-merge.jsonl"
            if not isinstance(row.get("hyp"), str) or (not allow_empty and not row["hyp"].strip()):
                raise ValueError(f"{directory}/{name}/{sample_id}: ASR仮説が空または不正です")
    return reference_ids, reference_rows


def main() -> None:
    """train/valのcoverage、用語pool、除外語の非混入を確認して監査JSONを保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--train-runs", type=Path, required=True)
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--val-runs", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--novel-terms", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-train-support", type=int, default=21522)
    args = parser.parse_args()

    train_ids, train_rows = unique_ids(args.train)
    supported_ids, supported = verify_runs(args.train_runs)
    val_ids, _ = unique_ids(args.val)
    val_run_ids, val_runs = verify_runs(args.val_runs)
    if not set(supported_ids) <= set(train_ids):
        raise ValueError("train ASR runに学習データ外のIDがあります")
    if len(supported_ids) != args.expected_train_support:
        raise ValueError(
            f"trainの実ASR対応数が想定外です: {len(supported_ids)} != {args.expected_train_support}"
        )
    if not set(val_ids) <= set(val_run_ids):
        raise ValueError("checkpoint選択用valのASR runに無いIDがあります")

    glossary_rows = read_jsonl(args.glossary)
    surfaces = [row.get("surface") for row in glossary_rows]
    if not all(isinstance(surface, str) and surface for surface in surfaces):
        raise ValueError("training glossaryのsurfaceが不正です")
    if len(surfaces) != len(set(surfaces)):
        raise ValueError("training glossaryにsurface重複があります")
    pool = set(surfaces)
    forbidden = term_set(args.exclusions) | term_set(args.novel_terms)
    leaked_pool = pool & forbidden
    if leaked_pool:
        raise ValueError(f"除外語または初見語がtraining glossaryにあります: {sorted(leaked_pool)[:5]}")

    glossary_counts = {}
    for name, directory in (("train", args.train_runs), ("val", args.val_runs)):
        count = 0
        _, glossary_by_id = unique_ids(directory / "formatter-glossary.jsonl")
        for sample_id, row in glossary_by_id.items():
            entries = row.get("glossary")
            if not isinstance(entries, list) or len(entries) > 20:
                raise ValueError(f"{name}/{sample_id}: 用語一覧は20件以下の配列が必要です")
            for entry in entries:
                surface = entry.get("surface") if isinstance(entry, dict) else None
                if surface not in pool:
                    raise ValueError(f"{name}/{sample_id}: pool外の語があります: {surface}")
            count += len(entries)
        glossary_counts[name] = count

    metadata = {
        "train_rows": len(train_ids),
        "train_unique_ids": len(set(train_ids)),
        "train_real_multiasr_rows": len(supported_ids),
        "train_synthetic_multiasr_rows": len(train_ids) - len(supported_ids),
        "train_support_ids_within_dataset": True,
        "checkpoint_selection_val_rows": len(val_ids),
        "checkpoint_selection_val_rows_with_all_runs": len(val_ids),
        "full_val_run_rows": len(val_run_ids),
        "training_glossary_entries": len(pool),
        "excluded_or_novel_terms": len(forbidden),
        "no_excluded_or_novel_pool_leak": True,
        "selector_max_entries": 20,
        "selector_entries": glossary_counts,
        "synthetic_qwen_hypothesis": "absent; qwen section is omitted when no audio-derived hypothesis exists",
        "inputs": {
            str(path): sha256(path)
            for path in (
                args.train,
                args.train_runs / "first-pass.jsonl",
                args.train_runs / "second-pass-plain.jsonl",
                args.train_runs / "segment-merge.jsonl",
                args.train_runs / "qwen06-hypothesis.jsonl",
                args.train_runs / "formatter-glossary.jsonl",
                args.val,
                args.val_runs / "first-pass.jsonl",
                args.val_runs / "second-pass-plain.jsonl",
                args.val_runs / "segment-merge.jsonl",
                args.val_runs / "qwen06-hypothesis.jsonl",
                args.val_runs / "formatter-glossary.jsonl",
                args.glossary,
                args.exclusions,
                args.novel_terms,
            )
        },
    }
    if args.output.exists():
        raise FileExistsError(f"監査出力を上書きしません: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
