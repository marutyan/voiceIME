#!/usr/bin/env python3
"""両方のASR出力で崩れた正解用語の学習例を2倍にする。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    """JSONLを読み込む。"""
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_hypotheses(path: Path) -> dict[str, str]:
    """ASR出力をIDで引けるようにし、重複IDを拒否する。"""
    result: dict[str, str] = {}
    for row in read_jsonl(path):
        sample_id, hyp = row.get("id"), row.get("hyp")
        if not isinstance(sample_id, str) or not isinstance(hyp, str):
            raise ValueError(f"{path}: idとhypは文字列である必要があります")
        if sample_id in result:
            raise ValueError(f"{path}: IDが重複しています")
        result[sample_id] = hyp
    return result


def term_is_present(text: str, entry) -> bool:
    """表記または読みが入力にそのまま現れるか調べる。"""
    return any(form and form in text for form in (entry.surface, *entry.readings))


def write_jsonl(path: Path, rows: list[dict]) -> str:
    """学習行をJSONLへ保存し、出力のSHA-256を返す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            file.write(line)
            digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def main() -> None:
    """学習時の用語選択規則で対象行を探し、データ行数を維持して2倍にする。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--first-pass", type=Path, required=True)
    parser.add_argument("--second-pass", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.repo / "train" / "formatter"))
    from voiceime.formatter.glossary import entry_from_record, load_glossary, select_glossary
    from voiceime.formatter.prompt import FormatterInput, formatter_input_text

    selector_path = args.repo / "src/voiceime/formatter/glossary.py"
    selector_hash = hashlib.sha256(selector_path.read_bytes()).hexdigest()

    rows = read_jsonl(args.train)
    first_by_id = load_hypotheses(args.first_pass)
    second_by_id = load_hypotheses(args.second_pass)
    pool = load_glossary(args.glossary)
    focus_indices: list[int] = []
    candidates = 0
    matched_rows = 0

    for index, row in enumerate(rows):
        sample_id = row.get("id")
        first, second = first_by_id.get(sample_id), second_by_id.get(sample_id)
        if first is None or second is None:
            continue
        matched_rows += 1
        asr_input = FormatterInput(first_pass=first, second_pass=second)
        if row.get("glossary_fixed") is True:
            selected = [entry_from_record(entry) for entry in row.get("glossary", [])]
        else:
            selected = select_glossary(formatter_input_text(asr_input), pool, 20)
        selected_surfaces = {entry.surface for entry in selected}

        spoken = row.get("spoken_text_kana", row.get("spoken_text", ""))
        target = row.get("target_text", "")
        gold = [
            entry_from_record(record)
            for record in row.get("glossary", [])
            if any(reading and reading in spoken for reading in entry_from_record(record).readings)
        ]
        listed_gold = [entry for entry in gold if entry.surface in selected_surfaces and entry.surface in target]
        candidates += len(listed_gold)
        if any(not term_is_present(first, entry) and not term_is_present(second, entry) for entry in listed_gold):
            focus_indices.append(index)

    if not focus_indices:
        raise RuntimeError("対象条件を満たす学習行がありません")
    if len(focus_indices) * 2 >= len(rows):
        raise RuntimeError("対象行が多すぎるため、同じデータ件数を保てません")

    focus_set = set(focus_indices)
    replacement_candidates = [index for index in range(len(rows)) if index not in focus_set]
    rng = random.Random(20261122)
    removed = set(rng.sample(replacement_candidates, len(focus_indices)))
    output_rows = [row for index, row in enumerate(rows) if index not in removed]
    output_rows.extend(rows[index] for index in focus_indices)
    if len(output_rows) != len(rows):
        raise RuntimeError("出力の学習行数が元データと一致しません")

    report = {
        "source_rows": len(rows),
        "rows_with_both_asr_passes": matched_rows,
        "selected_gold_term_occurrences": candidates,
        "focus_rows_duplicated_once": len(focus_indices),
        "nonfocus_rows_removed": len(removed),
        "output_rows": len(output_rows),
        "replacement_seed": 20261122,
        "glossary_selector_sha256": selector_hash,
        "output_sha256": write_jsonl(args.output, output_rows),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
