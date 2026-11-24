#!/usr/bin/env python3
"""ASR担当の統合JSONLをtrain.pyとeval_transformers.py用のrunへ分ける。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_FIELDS = {
    "first-pass.jsonl": "haas_first_pass_hyp",
    "second-pass-plain.jsonl": "haas_second_pass_plain_hyp",
    "segment-merge.jsonl": "segment_merge_hyp",
    "qwen06-hypothesis.jsonl": "qwen06_first_pass_hyp",
}


def read_rows(path: Path) -> list[dict[str, Any]]:
    """入力JSONLを読み、行番号を示して不正な形式を拒否する。"""
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: JSONを読めません") from error
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """新しいJSONLを一時ファイルから確定し、既存出力を上書きしない。"""
    if path.exists():
        raise FileExistsError(f"出力が既にあります: {path}")
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x", encoding="utf-8") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def convert_sources(paths: list[Path]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """複数shardをID重複なく結合し、ASR本文とformatter用語を別runにする。"""
    by_id: dict[str, dict[str, Any]] = {}
    source_counts = {}
    for path in paths:
        rows = read_rows(path)
        source_counts[str(path)] = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for row in rows:
            sample_id = row.get("id")
            if not isinstance(sample_id, str) or not sample_id:
                raise ValueError(f"{path}: idが空または文字列ではありません")
            if sample_id in by_id:
                raise ValueError(f"shard間でidが重複しています: {sample_id}")
            for field in (*SOURCE_FIELDS.values(), "formatter_glossary"):
                if field not in row:
                    raise ValueError(f"{path}/{sample_id}: {field} がありません")
            for field in SOURCE_FIELDS.values():
                if not isinstance(row[field], str) or (
                    field != "segment_merge_hyp" and not row[field].strip()
                ):
                    raise ValueError(f"{path}/{sample_id}: {field} は空でない文字列が必要です")
            glossary = row["formatter_glossary"]
            if not isinstance(glossary, list) or len(glossary) > 20:
                raise ValueError(f"{path}/{sample_id}: formatter_glossaryは20件以下の配列が必要です")
            if not all(
                isinstance(entry, dict)
                and isinstance(entry.get("surface"), str)
                and isinstance(entry.get("readings", []), list)
                and all(isinstance(reading, str) for reading in entry.get("readings", []))
                for entry in glossary
            ):
                raise ValueError(f"{path}/{sample_id}: formatter_glossaryの用語形式が不正です")
            if len({entry["surface"] for entry in glossary}) != len(glossary):
                raise ValueError(f"{path}/{sample_id}: formatter_glossaryに重複語があります")
            by_id[sample_id] = row

    output = {
        filename: [
            {"id": sample_id, "hyp": row[field]}
            for sample_id, row in by_id.items()
        ]
        for filename, field in SOURCE_FIELDS.items()
    }
    output["formatter-glossary.jsonl"] = [
        {"id": sample_id, "glossary": row["formatter_glossary"]}
        for sample_id, row in by_id.items()
    ]
    return output, {"rows": len(by_id), "sources": source_counts}


def main() -> None:
    """指定shardを新規出力先へ分割保存し、入力件数とhashを記録する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise FileExistsError(f"出力dirが空ではありません: {args.out_dir}")
    outputs, metadata = convert_sources(args.source)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, rows in outputs.items():
        write_jsonl(args.out_dir / filename, rows)
    metadata_path = args.out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
