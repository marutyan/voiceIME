#!/usr/bin/env python3
"""修正版manifestから音声なしの再集計用manifestを作る。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    """JSONLを読み込む。"""
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> str:
    """manifestを保存し、SHA-256を返す。"""
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_audio_path(rows: list[dict]) -> list[dict]:
    """評価用manifestからfacultyに存在しない音声パスだけを外す。"""
    result = []
    for row in rows:
        copied = dict(row)
        copied.pop("audio_path", None)
        result.append(copied)
    return result


def main() -> None:
    """修正版の全行と、既存評価と同じ50 IDのmanifestを出力する。"""
    root = Path.home() / "voiceime-work-fr3/inputs/formatter-sft3-current"
    corrected = read_jsonl(root / "manifest-devuser-fixed-20261122.jsonl")
    previous = read_jsonl(root / "manifest-devuser-no-audio.jsonl")
    corrected_by_id = {row["id"]: row for row in corrected}
    previous_ids = {row["id"] for row in previous}
    if not previous_ids.issubset(corrected_by_id):
        raise ValueError("修正版manifestに既存評価IDがありません")

    matched = [corrected_by_id[row["id"]] for row in previous]
    changed_fields: dict[str, int] = {}
    changed_target_ids: list[str] = []
    for old in previous:
        new = corrected_by_id[old["id"]]
        for field in set(old) | set(new):
            if field == "audio_path":
                continue
            if old.get(field) != new.get(field):
                changed_fields[field] = changed_fields.get(field, 0) + 1
                if field == "target_text":
                    changed_target_ids.append(old["id"])

    full_hash = write_jsonl(
        root / "manifest-devuser-fixed-no-audio-20261122.jsonl",
        without_audio_path(corrected),
    )
    eval_hash = write_jsonl(
        root / "manifest-devuser-scripted-fixed-no-audio-20261122.jsonl",
        without_audio_path(matched),
    )
    print(json.dumps({
        "corrected_source_rows": len(corrected),
        "existing_eval_rows": len(matched),
        "matched_ids": len(previous_ids),
        "changed_fields_in_existing_eval": changed_fields,
        "changed_target_ids": changed_target_ids,
        "full_no_audio_sha256": full_hash,
        "scripted_eval_no_audio_sha256": eval_hash,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
