#!/usr/bin/env python3
"""既存Bの実ASR行へQwen仮説と同じselectorの用語一覧を結合する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """空行を無視し、各行がJSON objectであることを確かめる。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(record)
    return rows


def by_id(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """runのID順とID辞書を返し、空ID・重複IDを拒否する。"""
    rows = read_jsonl(path)
    ids = [row.get("id") for row in rows]
    if not all(isinstance(sample_id, str) and sample_id for sample_id in ids):
        raise ValueError(f"{path}: 空でない文字列IDが必要です")
    mapped = dict(zip(ids, rows, strict=True))
    if len(mapped) != len(rows):
        raise ValueError(f"{path}: IDが重複しています")
    return ids, mapped


def sha256(path: Path) -> str:
    """入力ファイルのSHA-256を返す。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """既存成果物を上書きせず、新しいJSONLを一時ファイルから確定する。"""
    if path.exists():
        raise FileExistsError(f"出力を上書きしません: {path}")
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x", encoding="utf-8") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main() -> None:
    """ASR入力とselector語一覧をIDで照合し、D用の旧ASR runを作る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-src", type=Path, required=True)
    parser.add_argument("--haas-first", type=Path, required=True)
    parser.add_argument("--haas-second", type=Path, required=True)
    parser.add_argument("--segment-merge", type=Path, required=True)
    parser.add_argument("--qwen", type=Path, required=True)
    parser.add_argument("--glossary-v1", type=Path, required=True)
    parser.add_argument("--glossary-v2", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    main_src = str(args.main_src.expanduser().resolve())
    if main_src not in sys.path:
        sys.path.insert(0, main_src)
    from voiceime.formatter.glossary import (
        GlossaryIndex,
        load_glossary,
        load_term_list,
        select_glossary,
    )

    first_ids, first = by_id(args.haas_first)
    second_ids, second = by_id(args.haas_second)
    qwen_ids, qwen = by_id(args.qwen)
    if second_ids != first_ids or qwen_ids != first_ids:
        raise ValueError("Haas 1回目、2回目、QwenのIDと順序が一致しません")
    _, merged = by_id(args.segment_merge)
    missing_merge = [sample_id for sample_id in first_ids if sample_id not in merged]
    if missing_merge:
        raise ValueError(f"segment-mergeに無いHaas実ASR行があります: {len(missing_merge)}件")

    exclusions = load_term_list(args.exclusions)
    pool = load_glossary(args.glossary_v1, args.glossary_v2, exclude_terms=exclusions)
    index = GlossaryIndex(pool)
    pool_surfaces = {entry.surface for entry in pool}
    output_rows = []
    for sample_id in first_ids:
        first_hyp = first[sample_id].get("hyp")
        second_hyp = second[sample_id].get("hyp")
        segment_hyp = merged[sample_id].get("hyp")
        qwen_hyp = qwen[sample_id].get("hyp")
        if (
            not isinstance(first_hyp, str) or not first_hyp.strip()
            or not isinstance(second_hyp, str) or not second_hyp.strip()
            or not isinstance(segment_hyp, str)
            or not isinstance(qwen_hyp, str) or not qwen_hyp.strip()
        ):
            raise ValueError(f"{sample_id}: ASR仮説が空または不正です")
        # ASR担当と同じ選択器へHaas 1回目とQwen仮説を渡す。
        selection_text = first_hyp + "\n" + qwen_hyp
        selected = select_glossary(selection_text, index, max_entries=20)
        if any(entry.surface not in pool_surfaces for entry in selected):
            raise ValueError(f"{sample_id}: selector用語が候補pool外です")
        output_rows.append(
            {
                "id": sample_id,
                "haas_first_pass_hyp": first_hyp,
                "haas_second_pass_plain_hyp": second_hyp,
                "segment_merge_hyp": segment_hyp,
                "qwen06_first_pass_hyp": qwen_hyp,
                "formatter_glossary": [
                    {"surface": entry.surface, "readings": list(entry.readings)}
                    for entry in selected
                ],
            }
        )

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"出力dirに既存成果物があります: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    combined_path = args.output_dir / "legacy-combined.jsonl"
    pool_path = args.output_dir / "training-glossary.jsonl"
    metadata_path = args.output_dir / "metadata.json"
    write_jsonl(combined_path, output_rows)
    write_jsonl(
        pool_path,
        [{"surface": entry.surface, "readings": list(entry.readings)} for entry in pool],
    )
    metadata = {
        "rows": len(output_rows),
        "ids_match_in_order": True,
        "selector_max_entries": 20,
        "selector_pool_entries": len(pool),
        "excluded_terms": len(exclusions),
        "selector_source_commit": "cab8b886084c42935227c904027dd790d0df17af",
        "inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in {
                "haas_first": args.haas_first,
                "haas_second": args.haas_second,
                "segment_merge": args.segment_merge,
                "qwen": args.qwen,
                "glossary_v1": args.glossary_v1,
                "glossary_v2": args.glossary_v2,
                "exclusions": args.exclusions,
            }.items()
        },
        "outputs": {"combined": str(combined_path), "training_glossary": str(pool_path)},
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
