#!/usr/bin/env python3
"""test-novelの評価条件と、選択用語の効果を同じIDで照合する。"""

from __future__ import annotations

import json
import re
import unicodedata
import ast
import hashlib
import argparse
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).parent / "inputs" / "audit-source"
OUTPUTS = {
    "A": ROOT / "test-novel-a-20261122" / "test-novel-include-novel.jsonl",
    "B": ROOT / "test-novel-b-20261122" / "test-novel-include-novel.jsonl",
    "C": ROOT / "test-novel-c-20261122" / "test-novel-include-novel.jsonl",
    "B-2B": ROOT / "test-novel-b-2b-20261122" / "test-novel-include-novel.jsonl",
}
SFT2 = Path("/Users/marutyan/PrivateDev/voiceIME/runs/test-novel-sel2/e2e-include-novel.jsonl")
INPUT_EXPORT = Path(__file__).parent / "inputs" / "test-novel-model-inputs.jsonl"
SUMMARY_EXPORT = Path(__file__).parent / "test-novel-audit-summary.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def load_pool(paths: list[Path], excluded: set[str] = frozenset()) -> tuple[list[dict], dict[str, dict]]:
    merged: dict[str, dict] = {}
    for path in paths:
        for row in read_jsonl(path):
            surface = row["surface"]
            if surface in excluded:
                continue
            record = merged.setdefault(surface, {"surface": surface, "readings": []})
            readings = row.get("readings")
            if readings is None:
                readings = [row["reading"]] if row.get("reading") else []
            elif isinstance(readings, str):
                readings = [readings]
            for reading in readings:
                if reading not in record["readings"]:
                    record["readings"].append(reading)
    entries = list(merged.values())
    return entries, merged


def make_prompt_line(entry: dict) -> str:
    readings = "、".join(entry["readings"])
    return f"- {readings} → {entry['surface']}" if readings else f"- {entry['surface']}"


def source_constant(path: Path, name: str):
    """ソースの定数をASTから読み、入力書き出しにも実装の定義を使う。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"{path}: {name} が見つかりません")


def prompt_input_text(value: str | dict) -> str:
    """FormatterInputの保存形式を、prompt.pyと同じ区切りでuser本文にする。"""
    if isinstance(value, str):
        return value
    sections = []
    if value.get("first_pass") is not None:
        sections.append(f"1回目（ヒントなし）:\n{value['first_pass']}")
    if value.get("second_pass") is not None:
        sections.append(f"2回目（ヒントあり）:\n{value['second_pass']}")
    if value.get("combined_text") is not None:
        sections.append(f"結合文（2回目の採否を区間ごとに判断）:\n{value['combined_text']}")
    return "\n\n".join(sections)


def terms_for_row(row: dict) -> list[str]:
    return [term for term in row.get("terms", []) if isinstance(term, str)]


def classify_missing_term(reference: str, hypothesis: str, term: str, readings: list[str]) -> str:
    """用語を含む正解範囲が出力で読み・別表記・削除のどれになったかを分類する。"""
    normalized_hypothesis = normalize(hypothesis)
    if any(normalize(reading) in normalized_hypothesis for reading in readings if reading):
        return "reading_as_is"

    spans = []
    search_from = 0
    while True:
        start = reference.find(term, search_from)
        if start < 0:
            break
        spans.append((start, start + len(term)))
        search_from = start + len(term)
    if not spans:
        return "reference_term_not_found"

    opcodes = SequenceMatcher(None, reference, hypothesis, autojunk=False).get_opcodes()
    for start, end in spans:
        replacement = []
        for tag, ref_start, ref_end, hyp_start, hyp_end in opcodes:
            overlaps_term = max(ref_start, start) < min(ref_end, end)
            inserted_within_term = tag == "insert" and start <= ref_start <= end
            if tag != "equal" and (overlaps_term or inserted_within_term):
                replacement.append(hypothesis[hyp_start:hyp_end])
        if "".join(replacement).strip():
            return "different_output"
    return "dropped"


def main() -> None:
    parser = argparse.ArgumentParser(description="test-novelの入力・用語一覧・出力を照合する")
    parser.add_argument(
        "--results-root",
        type=Path,
        help="再評価JSONLのroot。指定時はA/B/C/B-2B配下を読む",
    )
    parser.add_argument(
        "--extra-run",
        action="append",
        default=[],
        metavar="NAME=JSONL",
        help="追加条件の出力JSONLを同じ一覧監査へ含める",
    )
    parser.add_argument("--input-export", type=Path, default=INPUT_EXPORT)
    parser.add_argument("--summary-export", type=Path, default=SUMMARY_EXPORT)
    args = parser.parse_args()
    outputs = OUTPUTS if args.results_root is None else {
        "A": args.results_root / "A" / "test-novel" / "test-novel-include-novel.jsonl",
        "B": args.results_root / "B" / "test-novel" / "test-novel-include-novel.jsonl",
        "C": args.results_root / "C" / "test-novel" / "test-novel-include-novel.jsonl",
        "B-2B": args.results_root / "B-2B" / "test-novel" / "test-novel-include-novel.jsonl",
    }
    for spec in args.extra_run:
        name, separator, run_path = spec.partition("=")
        if not separator or not name or name in outputs or not run_path:
            parser.error(f"extra-runは重複しないNAME=JSONLで指定してください: {spec}")
        outputs[name] = Path(run_path)
    manifest_path = ROOT / "test-novel.jsonl"
    plain_rows = read_jsonl(ROOT / "a-plain.jsonl")
    combined_rows = read_jsonl(ROOT / "a-segment-merge.jsonl")
    manifest_rows = read_jsonl(manifest_path)
    sft2_rows = read_jsonl(SFT2)
    current_pool_paths = [ROOT / "glossary-v1.jsonl", ROOT / "glossary-v2.jsonl"]
    excluded = {
        line.strip()
        for line in (ROOT / "exclude-v2-83.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    sft3_pool, sft3_by_surface = load_pool(current_pool_paths, excluded)
    _, sft2_by_surface = load_pool(current_pool_paths, excluded)
    prompt_module = Path(__file__).parents[2] / "src" / "voiceime" / "formatter" / "prompt.py"
    system_prompt = source_constant(prompt_module, "SYSTEM_PROMPT")
    glossary_header = source_constant(prompt_module, "GLOSSARY_HEADER")
    empty_glossary = source_constant(prompt_module, "EMPTY_GLOSSARY")
    input_header = source_constant(prompt_module, "INPUT_HEADER")

    collections = {
        "manifest": manifest_rows,
        "ASR first": plain_rows,
        "ASR second/combined": combined_rows,
        "SFT2": sft2_rows,
        **{name: read_jsonl(path) for name, path in outputs.items()},
    }
    id_lists = {name: [row.get("id") for row in rows] for name, rows in collections.items()}
    reference_ids = id_lists["manifest"]
    if len(reference_ids) != 500 or any(ids != reference_ids for ids in id_lists.values()):
        raise ValueError({name: (len(ids), ids[:3]) for name, ids in id_lists.items()})

    by_id = {name: {row["id"]: row for row in rows} for name, rows in collections.items()}
    asr_first = {row["id"]: row["hyp"] for row in plain_rows}
    asr_second = {row["id"]: row["hyp"] for row in combined_rows}
    input_shape_match = Counter()
    selection_match = Counter()
    model_stats: dict[str, dict] = {}
    export_rows = []

    for sample_id in reference_ids:
        row = by_id["manifest"][sample_id]
        sft2 = by_id["SFT2"][sample_id]
        if sft2.get("input_text") != asr_second[sample_id]:
            input_shape_match["SFT2_second_pass_match"] += 0
        else:
            input_shape_match["SFT2_second_pass_match"] += 1
        exported_conditions = {}
        for name in outputs:
            result = by_id[name][sample_id]
            raw = result["input_text"]
            if name == "A":
                expected = {"first_pass": None, "second_pass": asr_second[sample_id], "combined_text": None}
                match = raw == expected["second_pass"]
            elif name == "C":
                expected = {"first_pass": asr_first[sample_id], "second_pass": None, "combined_text": asr_second[sample_id]}
                match = isinstance(raw, dict) and raw.get("first_pass") == expected["first_pass"] and raw.get("second_pass") is None and raw.get("combined_text") == expected["combined_text"]
            else:
                expected = {"first_pass": asr_first[sample_id], "second_pass": asr_second[sample_id], "combined_text": None}
                match = isinstance(raw, dict) and raw.get("first_pass") == expected["first_pass"] and raw.get("second_pass") == expected["second_pass"] and raw.get("combined_text") is None
            input_shape_match[f"{name}_expected_input"] += int(match)
            entries_by_surface = sft3_by_surface
            selected = result.get("glossary", [])
            entries = [entries_by_surface.get(surface, {"surface": surface, "readings": []}) for surface in selected]
            user_message = (
                f"{glossary_header}\n"
                + ("\n".join(make_prompt_line(entry) for entry in entries) or empty_glossary)
                + f"\n\n{input_header}\n"
                + prompt_input_text(raw)
            )
            model_glossary_surfaces = set(selected)
            for other_name in outputs:
                other_selected = by_id[other_name][sample_id].get("glossary", [])
                selection_match[f"{name}_matches_{other_name}"] += int(
                    selected == other_selected
                )
            stats = model_stats.setdefault(name, {
                "examples": 0, "terms": 0, "included": 0, "included_correct": 0,
                "excluded": 0, "excluded_correct": 0, "miss_categories_included": Counter(),
                "failure_output_types": Counter(),
                "glossary_pool_size": len(sft3_pool), "selected_order_matches_sft2": 0,
                "selected_entries_missing_from_pool": 0,
            })
            stats["examples"] += 1
            stats["selected_order_matches_sft2"] += int(selected == sft2.get("glossary", []))
            stats["selected_entries_missing_from_pool"] += sum(surface not in entries_by_surface for surface in selected)
            term_entries = {entry["surface"]: entry for entry in row.get("glossary", [])}
            hyp = result.get("hyp", "")
            for term in terms_for_row(row):
                stats["terms"] += 1
                included = term in model_glossary_surfaces
                correct = hyp.count(term) > 0
                bucket = "included" if included else "excluded"
                stats[bucket] += 1
                stats[f"{bucket}_correct"] += int(correct)
                category = None
                if included and not correct:
                    gold = term_entries.get(term, {})
                    readings = gold.get("readings", [])
                    if isinstance(readings, str):
                        readings = [readings]
                    stats["failure_output_types"][classify_missing_term(
                        row.get("target_text", ""), hyp, term, readings
                    )] += 1
                    normalized_hyp = normalize(hyp)
                    reading_forms = {normalize(reading) for reading in readings if reading}
                    if any(reading and reading in normalized_hyp for reading in reading_forms):
                        category = "reading_as_is"
                    else:
                        collided = False
                        for entry in entries:
                            if entry["surface"] == term or entry["surface"] not in hyp:
                                continue
                            other_readings = {normalize(value) for value in entry.get("readings", [])}
                            if reading_forms & other_readings:
                                collided = True
                                break
                        category = "other_glossary_term_same_reading" if collided else "omitted_or_other_text"
                    stats["miss_categories_included"][category] += 1
                exported_conditions[name] = {
                    "asr_input": raw,
                    "first_pass": expected["first_pass"],
                    "second_pass": expected["second_pass"],
                    "combined_text": expected["combined_text"],
                    "selected_glossary": entries,
                    "selected_glossary_lines": [make_prompt_line(entry) for entry in entries],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                }
        export_rows.append({"id": sample_id, "conditions": exported_conditions})

    # SFT2の選択用語はv1だけで構成した当時の出力一覧をそのまま保存する。
    sft2_pool_size = len(sft3_pool)
    sft2_stats = {"examples": 500, "glossary_pool_size": sft2_pool_size, "selected_order_matches_A": 0,
                  "selected_entries_missing_from_pool": 0, "terms": 0, "included": 0,
                  "included_correct": 0, "excluded": 0, "excluded_correct": 0,
                  "miss_categories_included": Counter(), "failure_output_types": Counter()}
    for sample_id in reference_ids:
        gold_row = by_id["manifest"][sample_id]
        output = by_id["SFT2"][sample_id]
        surfaces = output.get("glossary", [])
        sft2_stats["selected_order_matches_A"] += int(surfaces == by_id["A"][sample_id].get("glossary", []))
        entries = [sft2_by_surface.get(surface, {"surface": surface, "readings": []}) for surface in surfaces]
        sft2_stats["selected_entries_missing_from_pool"] += sum(surface not in sft2_by_surface for surface in surfaces)
        term_entries = {entry["surface"]: entry for entry in gold_row.get("glossary", [])}
        hyp = output.get("hyp", "")
        for term in terms_for_row(gold_row):
            sft2_stats["terms"] += 1
            included = term in surfaces
            correct = hyp.count(term) > 0
            bucket = "included" if included else "excluded"
            sft2_stats[bucket] += 1
            sft2_stats[f"{bucket}_correct"] += int(correct)
            if included and not correct:
                gold = term_entries.get(term, {})
                readings = gold.get("readings", [])
                if isinstance(readings, str):
                    readings = [readings]
                sft2_stats["failure_output_types"][classify_missing_term(
                    gold_row.get("target_text", ""), hyp, term, readings
                )] += 1
                forms = {normalize(value) for value in readings if value}
                if any(value and value in normalize(hyp) for value in forms):
                    category = "reading_as_is"
                else:
                    collided = any(
                        entry["surface"] != term and entry["surface"] in hyp
                        and bool(forms & {normalize(value) for value in entry.get("readings", [])})
                        for entry in entries
                    )
                    category = "other_glossary_term_same_reading" if collided else "omitted_or_other_text"
                sft2_stats["miss_categories_included"][category] += 1
        sft2_entries = [
            sft2_by_surface.get(surface, {"surface": surface, "readings": []})
            for surface in surfaces
        ]
        # SFT2の実測入力と用語一覧を添え、PMがSFT2へ同じ入力を再現しやすくする。
        export_rows[reference_ids.index(sample_id)]["sft2_observed"] = {
            "asr_input": output.get("input_text"),
            "selected_glossary": sft2_entries,
            "selected_glossary_lines": [make_prompt_line(entry) for entry in sft2_entries],
        }
    model_stats["SFT2"] = sft2_stats

    args.input_export.parent.mkdir(parents=True, exist_ok=True)
    with args.input_export.open("w", encoding="utf-8") as stream:
        for row in export_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    for stats in model_stats.values():
        stats["miss_categories_included"] = dict(stats["miss_categories_included"])
        stats["failure_output_types"] = dict(stats["failure_output_types"])
        stats["included_accuracy"] = stats["included_correct"] / stats["included"] if stats["included"] else None
        stats["excluded_accuracy"] = stats["excluded_correct"] / stats["excluded"] if stats["excluded"] else None
    summary = {
        "manifest": str(manifest_path), "manifest_count": len(manifest_rows),
        "ids_identical_in_order": {name: ids == reference_ids for name, ids in id_lists.items()},
        "input_match_counts": dict(input_shape_match),
        "selection_match_counts": dict(selection_match),
        "glossary_pool": {"sft2_entries": sft2_pool_size, "sft3_entries": len(sft3_pool),
                          "excluded_surfaces": len(excluded)},
        "models": model_stats,
        "source_sha256": {
            path.name + ("/" + path.parent.name if path.parent.name.startswith("test-novel-") else ""): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [manifest_path, ROOT / "a-plain.jsonl", ROOT / "a-segment-merge.jsonl", *outputs.values(), SFT2, prompt_module]
        },
        "prompt_source": str(prompt_module),
        "export": str(args.input_export),
    }
    args.summary_export.parent.mkdir(parents=True, exist_ok=True)
    args.summary_export.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
