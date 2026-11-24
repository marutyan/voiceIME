#!/usr/bin/env python3
"""mainの用語選択器で、上限数とWhisper補助仮説を変えた一覧を作る。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、各行がobjectであることを確認する。"""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: JSON object以外の行があります")
    return rows


def index_rows(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """ASRとmanifestのID順を保ち、重複IDを拒否する。"""
    rows = read_jsonl(path)
    ids = [row.get("id") for row in rows]
    if not all(isinstance(sample_id, str) and sample_id for sample_id in ids):
        raise ValueError(f"{path}: 空でない文字列IDが必要です")
    indexed = dict(zip(ids, rows, strict=True))
    if len(indexed) != len(rows):
        raise ValueError(f"{path}: IDが重複しています")
    return ids, indexed


def sha256(path: Path) -> str:
    """入力ファイルのSHA-256を返す。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_selector(path: Path):
    """指定されたmainのglossary.pyを他の作業ツリーから独立して読み込む。"""
    spec = importlib.util.spec_from_file_location("voiceime_main_glossary", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"selector moduleを読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """既存の実験成果物を上書きせず、新しいJSONLを確定する。"""
    if path.exists():
        raise FileExistsError(f"出力を上書きしません: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x", encoding="utf-8") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def build_split(
    name: str,
    manifest_path: Path,
    first_path: Path,
    qwen_path: Path,
    whisper_path: Path,
    exclusion_path: Path | None,
    existing_glossary_path: Path,
    glossary_paths: list[Path],
    selector: Any,
    output_dir: Path,
) -> dict[str, Any]:
    """一つのsplitから6条件の用語一覧を作り、候補への包含率を記録する。"""
    manifest_ids, manifest = index_rows(manifest_path)
    first_ids, first = index_rows(first_path)
    qwen_ids, qwen = index_rows(qwen_path)
    whisper_ids, whisper = index_rows(whisper_path)
    existing_ids, existing = index_rows(existing_glossary_path)
    for label, ids in (
        ("1回目", first_ids), ("Qwen", qwen_ids), ("Whisper", whisper_ids),
        ("既存一覧", existing_ids),
    ):
        if ids != manifest_ids:
            raise ValueError(f"{name}: {label}のIDまたは順序がmanifestと一致しません")

    excluded = selector.load_term_list(exclusion_path) if exclusion_path else set()
    pool = selector.load_glossary(*glossary_paths, exclude_terms=excluded)
    pool_surfaces = {entry.surface for entry in pool}
    index = selector.GlossaryIndex(pool)
    term_counts: Counter[str] = Counter()
    for sample_id in manifest_ids:
        terms = manifest[sample_id].get("terms", [])
        if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
            raise ValueError(f"{name}/{sample_id}: termsは文字列の配列が必要です")
        term_counts.update(terms)
    denominator = sum(term_counts.values())

    existing_surfaces = {
        sample_id: [entry["surface"] if isinstance(entry, dict) else entry
                    for entry in existing[sample_id].get("glossary", [])]
        for sample_id in manifest_ids
    }
    variants: dict[str, Any] = {}
    for max_entries in (20, 32, 48):
        for add_whisper in (False, True):
            variant = f"max{max_entries}-haas-qwen" + ("-whisper" if add_whisper else "")
            output_rows = []
            included = 0
            for sample_id in manifest_ids:
                parts = [first[sample_id]["hyp"], qwen[sample_id]["hyp"]]
                if add_whisper:
                    parts.append(whisper[sample_id]["hyp"])
                selected = selector.select_glossary(
                    "\n".join(parts), index, max_entries, selector.DEFAULT_MIN_SCORE
                )
                surfaces = [entry.surface for entry in selected]
                if len(surfaces) > max_entries or len(set(surfaces)) != len(surfaces):
                    raise ValueError(f"{name}/{sample_id}/{variant}: 一覧上限か重複の検査に失敗")
                if any(surface not in pool_surfaces for surface in surfaces):
                    raise ValueError(f"{name}/{sample_id}/{variant}: 候補pool外の語があります")
                included += sum(count for term, count in Counter(manifest[sample_id]["terms"]).items()
                                if term in set(surfaces))
                output_rows.append({
                    "id": sample_id,
                    "glossary": [
                        {"surface": entry.surface, "readings": list(entry.readings)}
                        for entry in selected
                    ],
                })
            output_path = output_dir / "glossaries" / name / f"{variant}.jsonl"
            write_jsonl(output_path, output_rows)
            variants[variant] = {
                "rows": len(output_rows),
                "terms_included": included,
                "terms_total": denominator,
                "included_fraction": included / denominator if denominator else None,
                "matches_existing_order": sum(
                    [entry["surface"] if isinstance(entry, dict) else entry
                     for entry in row["glossary"]] == existing_surfaces[sample_id]
                    for sample_id, row in zip(manifest_ids, output_rows, strict=True)
                ),
                "output": str(output_path),
            }

    return {
        "rows": len(manifest_ids),
        "glossary_pool_entries": len(pool),
        "excluded_terms": len(excluded),
        "gold_term_instances": denominator,
        "variants": variants,
        "inputs": {
            label: {"path": str(path), "sha256": sha256(path)}
            for label, path in {
                "manifest": manifest_path,
                "first_pass": first_path,
                "qwen": qwen_path,
                "whisper": whisper_path,
                "existing_glossary": existing_glossary_path,
                **{f"glossary_{index}": path for index, path in enumerate(glossary_paths, 1)},
                **({"exclusions": exclusion_path} if exclusion_path else {}),
            }.items()
        },
    }


def main() -> None:
    """mainの選択器・入力manifestを固定し、valとtest-novelの一覧を生成する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector", type=Path, required=True)
    parser.add_argument("--selector-commit", required=True)
    parser.add_argument("--glossary", type=Path, action="append", required=True)
    parser.add_argument("--val-manifest", type=Path, required=True)
    parser.add_argument("--val-first", type=Path, required=True)
    parser.add_argument("--val-qwen", type=Path, required=True)
    parser.add_argument("--val-whisper", type=Path, required=True)
    parser.add_argument("--val-existing-glossary", type=Path, required=True)
    parser.add_argument("--test-novel-manifest", type=Path, required=True)
    parser.add_argument("--test-novel-first", type=Path, required=True)
    parser.add_argument("--test-novel-qwen", type=Path, required=True)
    parser.add_argument("--test-novel-whisper", type=Path, required=True)
    parser.add_argument("--test-novel-existing-glossary", type=Path, required=True)
    parser.add_argument("--exclude-terms", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    selector = load_selector(args.selector)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"出力dirに既存成果物があります: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "selector_commit": args.selector_commit,
        "selector_path": str(args.selector),
        "selector_sha256": sha256(args.selector),
        "max_entries": [20, 32, 48],
        "selection_text": "Haas first-pass + Qwen0.6B; optional Whisper first-pass, joined by newline",
        "min_score": selector.DEFAULT_MIN_SCORE,
        "val": build_split(
            "val", args.val_manifest, args.val_first, args.val_qwen, args.val_whisper,
            None, args.val_existing_glossary, args.glossary, selector, args.output_dir,
        ),
        "test_novel": build_split(
            "test-novel", args.test_novel_manifest, args.test_novel_first,
            args.test_novel_qwen, args.test_novel_whisper, args.exclude_terms,
            args.test_novel_existing_glossary, args.glossary, selector, args.output_dir,
        ),
    }
    metadata_path = args.output_dir / "selection-audit.json"
    metadata_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
