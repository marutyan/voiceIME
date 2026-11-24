#!/usr/bin/env python3
"""第3弾train全体から、既存12,000件を除く合成入力を作る。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_FULL_ROWS = 56_971
EXPECTED_EXISTING_ROWS = 12_000
EXPECTED_EXISTING_ID_DIGEST = "92b84abc12e17ca2d8b4c1e6ff0bf99b9ca8b3ccc955d5f4987324c970315a2f"
SHARD_COUNT = 3


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONL全体を読み、壊れた行を入力エラーとして止める。"""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def id_digest(ids: list[str] | set[str]) -> str:
    """ID集合をソートしてハッシュし、並び順によらない確認値を返す。"""
    payload = "\n".join(sorted(ids)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def unit_hash(*parts: object) -> float:
    """TTS本体と同じ方法で、IDとseedから安定した割当値を作る。"""
    payload = "\x1f".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def write_compressed_jsonl(path: Path, rows: list[dict[str, Any]]) -> tuple[str, int, int]:
    """再送しやすいgzip JSONLを書き、非圧縮内容のhashとサイズを返す。"""
    digest = hashlib.sha256()
    plain_bytes = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as output:
                for row in rows:
                    line = json.dumps(row, ensure_ascii=False) + "\n"
                    encoded = line.encode("utf-8")
                    digest.update(encoded)
                    plain_bytes += len(encoded)
                    output.write(line)
    return digest.hexdigest(), plain_bytes, path.stat().st_size


def main() -> None:
    """全trainと既存音声IDを照合し、音声長見積り順に3 shardへ分ける。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selected-ids", type=Path, required=True)
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise FileExistsError(f"既存の一時出力を上書きしない: {args.out_dir}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(args.source)
    source_ids = [str(row.get("id", "")) for row in rows]
    if len(rows) != EXPECTED_FULL_ROWS or not all(source_ids):
        raise ValueError(f"全trainの件数またはIDが不正: {len(rows)}")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("全trainに重複IDがある")
    if any(row.get("split") != "train" for row in rows):
        raise ValueError("入力にtrain以外のsplitがある")
    required = ("spoken_text_kana", "spoken_text_mixed", "target_text", "terms", "glossary")
    if any(any(key not in row for key in required) for row in rows):
        raise ValueError("train入力の必要項目が足りない")

    selected = set(args.selected_ids.read_text(encoding="utf-8").splitlines())
    if len(selected) != EXPECTED_EXISTING_ROWS:
        raise ValueError(f"既存音声ID一覧の件数が不正: {len(selected)}")
    selected_digest = id_digest(selected)
    if selected_digest != EXPECTED_EXISTING_ID_DIGEST:
        raise ValueError(f"既存音声ID一覧のhashがfaculty manifestと異なる: {selected_digest}")
    missing_selected = selected - set(source_ids)
    if missing_selected:
        raise ValueError(f"既存音声IDが全trainに見つからない: {len(missing_selected)}件")

    remaining = [row for row in rows if row["id"] not in selected]
    remaining_ids = [row["id"] for row in remaining]
    if len(remaining) != EXPECTED_FULL_ROWS - EXPECTED_EXISTING_ROWS:
        raise ValueError(f"残りtrain件数が不正: {len(remaining)}")

    voices = json.loads(args.voices.read_text(encoding="utf-8"))
    train_voices = [voice for voice in voices if voice.get("use") == "train-val"]
    test_voices = [voice for voice in voices if voice.get("use") == "test-synth"]
    if len(train_voices) != 24 or len(test_voices) != 6:
        raise ValueError(f"評価用と学習用の声の集合が不正: train={len(train_voices)}, test={len(test_voices)}")
    if {voice["speaker"] for voice in train_voices} & {voice["speaker"] for voice in test_voices}:
        raise ValueError("学習用と評価用の声が重複している")

    engine_counts: Counter[str] = Counter()
    speaker_counts: Counter[str] = Counter()
    estimated_seconds = 0.0
    previous_estimated_seconds = 0.0
    for row in rows:
        voice_pool = train_voices
        voice = voice_pool[int(unit_hash(0, "voice", row["id"]) * len(voice_pool))]
        speaker_counts[voice["speaker"]] += row["id"] not in selected
        if row["id"] not in selected:
            engine = "multi" if unit_hash(0, "engine", row["id"]) < 0.2 else "ja"
            engine_counts[engine] += 1
            estimated_seconds += float(row["est_seconds"])
        else:
            previous_estimated_seconds += float(row["est_seconds"])

    ordered = sorted(remaining, key=lambda row: (-float(row["est_seconds"]), row["id"]))
    shards = [ordered[index::SHARD_COUNT] for index in range(SHARD_COUNT)]
    shard_summaries = []
    for index, shard in enumerate(shards):
        path = args.out_dir / f"shard-{index:02d}.jsonl.gz"
        digest, plain_bytes, compressed_bytes = write_compressed_jsonl(path, shard)
        shard_summaries.append(
            {
                "shard": index,
                "rows": len(shard),
                "id_sha256": id_digest([row["id"] for row in shard]),
                "jsonl_sha256": digest,
                "jsonl_bytes": plain_bytes,
                "gzip_bytes": compressed_bytes,
                "estimated_speech_seconds": sum(float(row["est_seconds"]) for row in shard),
            }
        )

    metadata = {
        "source_path": str(args.source),
        "source_bytes": args.source.stat().st_size,
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "full_train_rows": len(rows),
        "full_train_unique_ids": len(set(source_ids)),
        "full_train_id_sha256": id_digest(source_ids),
        "existing_rows": len(selected),
        "existing_id_sha256": selected_digest,
        "remaining_rows": len(remaining),
        "remaining_unique_ids": len(set(remaining_ids)),
        "remaining_id_sha256": id_digest(remaining_ids),
        "remaining_input_sha256": hashlib.sha256(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in remaining).encode("utf-8")
        ).hexdigest(),
        "voice_pool": {"train_val": len(train_voices), "test_synth": len(test_voices)},
        "seed": 0,
        "engine_counts": dict(engine_counts),
        "speaker_counts": dict(sorted(speaker_counts.items())),
        "previous_estimated_speech_hours": previous_estimated_seconds / 3600,
        "remaining_estimated_speech_hours": estimated_seconds / 3600,
        "sharding": "descending est_seconds then stable ID; round-robin across three shards",
        "shards": shard_summaries,
    }
    (args.out_dir / "preparation.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
