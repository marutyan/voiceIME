"""Qwen3-ASR用に音声manifestを変換し、学習と検証の条件を固定する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path, PurePosixPath
from typing import Any


# 公式trainerのJSON readerがsplit間の列一致を要求するため、学習用schemaを固定する。
TRAINER_FIELDS = ("id", "audio", "text", "prompt", "hinted")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、行番号とともに形式エラーを示す。"""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """親directoryを作り、UTF-8のJSONLを再現可能な順序で保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")


def unique_surfaces(entries: list[dict[str, Any]]) -> list[str]:
    """用語entryから空欄を除き、最初に現れた順でsurfaceを重複除去する。"""
    return list(
        dict.fromkeys(
            entry["surface"]
            for entry in entries
            if isinstance(entry.get("surface"), str) and entry["surface"]
        )
    )


def build_prompt(
    row: dict[str, Any],
    *,
    include_hints: bool,
    allowed_surfaces: set[str],
    distractor_pool: list[str],
    rng: random.Random,
    drop_probability: float,
    max_distractors: int,
    max_entries: int,
) -> str:
    """指定行のsystem contextを作り、正解語の欠落と無関係語を再現する。"""
    if not include_hints:
        return ""

    row_surfaces = [
        surface
        for surface in unique_surfaces(row.get("glossary", []))
        if surface in allowed_surfaces
    ]
    gold_surfaces = set(row.get("terms", [])) & set(row_surfaces)
    kept = [
        surface
        for surface in row_surfaces
        if surface not in gold_surfaces or rng.random() >= drop_probability
    ]
    used = set(kept)
    candidates = [
        surface
        for surface in distractor_pool
        if surface not in used and surface not in gold_surfaces
    ]
    distractor_count = min(
        rng.randint(0, max_distractors),
        len(candidates),
        max(0, max_entries - len(kept)),
    )
    kept.extend(rng.sample(candidates, distractor_count))
    rng.shuffle(kept)
    return ", ".join(kept[:max_entries])


def remote_audio_path(
    manifest_path: Path, row: dict[str, Any], remote_data_root: PurePosixPath
) -> str:
    """manifest相対音声pathを検査し、facultyの対応pathへ写す。"""
    relative_path = PurePosixPath(row["audio_path"])
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"音声pathはmanifest相対pathが必要です: {row['audio_path']}")
    local_path = manifest_path.parent.joinpath(*relative_path.parts)
    if not local_path.is_file():
        raise FileNotFoundError(local_path)
    split = manifest_path.parent.name
    return str(remote_data_root / split / relative_path)


def make_asr_row(
    row: dict[str, Any],
    *,
    audio: str,
    prompt: str,
    hinted: bool,
) -> dict[str, Any]:
    """公式trainer形式と、後段の評価に必要な正解・用語情報をまとめる。"""
    return {
        "id": row["id"],
        "audio": audio,
        "text": f"language Japanese<asr_text>{row['target_text']}",
        "prompt": prompt,
        "hinted": hinted,
        "target_text": row["target_text"],
        "terms": row.get("terms", []),
        "glossary": row.get("glossary", []),
        "fillers": row.get("fillers", 0),
        "tags": row.get("tags", []),
    }


def trainer_row(row: dict[str, Any]) -> dict[str, Any]:
    """公式trainerへ渡す列だけを残し、train/validationのschemaをそろえる。"""
    return {key: row[key] for key in TRAINER_FIELDS}


def parse_args() -> argparse.Namespace:
    """CLI引数を読む。data sourceはmain checkoutの読み取り専用pathを渡す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-manifest", required=True, type=Path)
    parser.add_argument("--val-manifest", required=True, type=Path)
    parser.add_argument("--glossary", required=True, type=Path)
    parser.add_argument("--remote-data-root", required=True, type=PurePosixPath)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--selection-manifest", required=True, type=Path)
    parser.add_argument("--selection-size", type=int, default=200)
    parser.add_argument("--pilot-size", type=int, default=64)
    parser.add_argument("--pilot-eval-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--nohint-probability", type=float, default=0.5)
    parser.add_argument("--drop-probability", type=float, default=0.15)
    parser.add_argument("--max-distractors", type=int, default=8)
    parser.add_argument("--max-entries", type=int, default=64)
    return parser.parse_args()


def main() -> None:
    """用train splitのみでcontextを作り、再利用可能なmanifestを出力する。"""
    args = parse_args()
    train_rows = read_jsonl(args.train_manifest)
    val_rows = read_jsonl(args.val_manifest)
    glossary_rows = read_jsonl(args.glossary)
    train_glossary_rows = [
        row for row in glossary_rows if row.get("split") == "train"
    ]
    train_surfaces = unique_surfaces(train_glossary_rows)
    if len(train_surfaces) != len(train_glossary_rows):
        raise ValueError("train glossaryに重複surfaceがあります")
    train_surface_set = set(train_surfaces)

    train_rng = random.Random(args.seed)
    train_output: list[dict[str, Any]] = []
    hinted_train = 0
    for row in train_rows:
        hinted = train_rng.random() >= args.nohint_probability
        prompt = build_prompt(
            row,
            include_hints=hinted,
            allowed_surfaces=train_surface_set,
            distractor_pool=train_surfaces,
            rng=train_rng,
            drop_probability=args.drop_probability,
            max_distractors=args.max_distractors,
            max_entries=args.max_entries,
        )
        hinted_train += hinted
        prepared = make_asr_row(
            row,
            audio=remote_audio_path(
                args.train_manifest, row, args.remote_data_root
            ),
            prompt=prompt,
            hinted=hinted,
        )
        train_output.append(trainer_row(prepared))

    if not 0 <= args.selection_size <= len(val_rows):
        raise ValueError("selection-sizeがval件数の範囲外です")
    selection_rng = random.Random(args.seed)
    selected_indices = sorted(
        selection_rng.sample(range(len(val_rows)), args.selection_size)
    )
    hint_rng = random.Random(args.seed + 1)
    hinted_indices = set(
        hint_rng.sample(selected_indices, args.selection_size // 2)
    )
    val_prompt_rng = random.Random(args.seed + 2)
    val_output: list[dict[str, Any]] = []
    local_manifest: list[dict[str, Any]] = []
    for index in selected_indices:
        row = val_rows[index]
        hinted = index in hinted_indices
        row_surfaces = set(unique_surfaces(row.get("glossary", [])))
        row_surfaces &= train_surface_set
        prompt = build_prompt(
            row,
            include_hints=hinted,
            allowed_surfaces=row_surfaces,
            distractor_pool=train_surfaces,
            rng=val_prompt_rng,
            drop_probability=args.drop_probability,
            max_distractors=args.max_distractors,
            max_entries=args.max_entries,
        )
        audio = remote_audio_path(args.val_manifest, row, args.remote_data_root)
        val_output.append(
            make_asr_row(row, audio=audio, prompt=prompt, hinted=hinted)
        )
        local_row = dict(row)
        local_row["audio_path"] = str(
            args.val_manifest.parent / row["audio_path"]
        )
        local_manifest.append(local_row)

    pilot_rows = train_output[: args.pilot_size]
    pilot_hinted = [row for row in val_output if row["hinted"]]
    pilot_nohint = [row for row in val_output if not row["hinted"]]
    pilot_eval = (
        pilot_hinted[: args.pilot_eval_size // 2]
        + pilot_nohint[: args.pilot_eval_size // 2]
    )
    val_training_rows = [trainer_row(row) for row in val_output]
    pilot_eval_training_rows = [trainer_row(row) for row in pilot_eval]
    selected_ids = "\n".join(row["id"] for row in val_output).encode("utf-8")
    summary = {
        "train_rows": len(train_output),
        "train_hinted_rows": hinted_train,
        "train_nohint_rows": len(train_output) - hinted_train,
        "train_glossary_surfaces": len(train_surfaces),
        "val_selection_rows": len(val_output),
        "val_hinted_rows": len(pilot_hinted),
        "val_nohint_rows": len(pilot_nohint),
        "val_selection_seed": args.seed,
        "val_selection_ids_sha256": hashlib.sha256(selected_ids).hexdigest(),
        "pilot_train_rows": len(pilot_rows),
        "pilot_eval_rows": len(pilot_eval),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "train.jsonl", train_output)
    write_jsonl(args.output_dir / "pilot-train.jsonl", pilot_rows)
    write_jsonl(args.output_dir / "val-200.jsonl", val_training_rows)
    write_jsonl(args.output_dir / "pilot-val.jsonl", pilot_eval_training_rows)
    write_jsonl(
        args.output_dir / "val-200-manifest.jsonl",
        [
            {
                "id": row["id"],
                "audio_path": row["audio"],
                "target_text": row["target_text"],
                "fillers": row["fillers"],
                "terms": row["terms"],
                "glossary": row["glossary"],
                "tags": row["tags"],
            }
            for row in val_output
        ],
    )
    write_jsonl(args.output_dir / "train-glossary.jsonl", train_glossary_rows)
    write_jsonl(args.selection_manifest, local_manifest)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
