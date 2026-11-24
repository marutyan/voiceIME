#!/usr/bin/env python3
"""字幕区間が同じ候補の既存音声を再利用して、最終manifestを組み立てる。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


# 同じ動画の同じ時刻と字幕なら、語の注釈が変わっても音声は再利用できる。
def audio_identity(row: dict[str, Any]) -> str:
    """動画ID、開始・終了時刻、字幕文をJSON化してSHA-256を返す。"""
    identity = {
        "video_id": row["video_id"],
        "start_ms": int(row["start_ms"]),
        "end_ms": int(row["end_ms"]),
        "spoken_text": row["spoken_text"],
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# JSONLのmanifestを辞書の配列として読む。
def read_rows(path: Path) -> list[dict[str, Any]]:
    """空行を無視し、各行をJSON objectとして読む。"""
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


# 以前に切り出した同一音声を引き継ぎ、新規候補だけ新しい音声pathを割り当てる。
def reconcile(
    old_paths: list[Path],
    new_paths: list[Path],
    output_dir: Path,
    audio_root: Path,
) -> dict[str, Any]:
    """同一区間の既存ID/pathを保ち、未取得区間へ衝突しないIDを付ける。"""
    old_audio: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    old_count = 0
    for path in old_paths:
        for row in read_rows(path):
            old_audio[audio_identity(row)].append(row)
            old_count += 1

    final_rows: dict[str, list[dict[str, Any]]] = {"pub-eval": [], "pub-pool": []}
    reused = Counter()
    added = Counter()
    seen_ids: set[str] = set()

    for path in new_paths:
        rows = read_rows(path)
        if not rows:
            raise ValueError(f"manifestが空です: {path}")
        split = str(rows[0].get("split", ""))
        if split not in final_rows or any(row.get("split") != split for row in rows):
            raise ValueError(f"splitの値が不正です: {path}")

        for row in rows:
            matches = old_audio[audio_identity(row)]
            if matches:
                previous = matches.popleft()
                row["id"] = previous["id"]
                row["audio_path"] = previous["audio_path"]
                reused[split] += 1
            else:
                sample_id = f"yodas-{split}-x{audio_identity(row)[:12]}"
                if sample_id in seen_ids:
                    sample_id = f"yodas-{split}-x{audio_identity(row)[:20]}"
                row["id"] = sample_id
                row["audio_path"] = str(audio_root / split / f"{sample_id}.wav")
                added[split] += 1
            if row["id"] in seen_ids:
                raise ValueError(f"重複したmanifest IDです: {row['id']}")
            seen_ids.add(row["id"])
            if int(row["end_ms"]) - int(row["start_ms"]) < 500:
                raise ValueError(f"500ms未満の区間が残っています: {row['id']}")
            final_rows[split].append(row)

    eval_videos = {row["video_id"] for row in final_rows["pub-eval"]}
    pool_videos = {row["video_id"] for row in final_rows["pub-pool"]}
    if eval_videos & pool_videos:
        raise ValueError("同じvideo_idがpub-evalとpub-poolの両方にあります")

    output_dir.mkdir(parents=True, exist_ok=True)
    split_stats: dict[str, dict[str, int]] = {}
    for split, rows in final_rows.items():
        with (output_dir / f"{split}.jsonl").open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        split_stats[split] = {
            "segments": len(rows),
            "videos": len({row["video_id"] for row in rows}),
            "term_occurrences": sum(
                len(row["terms"]) + len(row["terms_katakana_in_caption"])
                for row in rows
            ),
        }

    stats = {
        "old_manifest_rows": old_count,
        "final_manifest_rows": sum(len(rows) for rows in final_rows.values()),
        "reused_audio_rows": dict(reused),
        "new_audio_rows": dict(added),
        "unused_old_audio_rows": sum(len(rows) for rows in old_audio.values()),
        "same_video_overlap": False,
        "splits": split_stats,
    }
    (output_dir / "reconciliation-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return stats


# 以前と新しいmanifestの場所を受け取り、再利用可能な音声を照合する。
def main() -> None:
    """選定済み候補のmanifestを照合し、再利用状況を記録する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-eval", type=Path, required=True)
    parser.add_argument("--old-pool", type=Path, required=True)
    parser.add_argument("--new-eval", type=Path, required=True)
    parser.add_argument("--new-pool", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    args = parser.parse_args()
    stats = reconcile(
        [args.old_eval, args.old_pool],
        [args.new_eval, args.new_pool],
        args.output_dir,
        args.audio_root,
    )
    print(json.dumps(stats, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
