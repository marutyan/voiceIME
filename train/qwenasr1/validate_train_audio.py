"""facultyへ届いた学習音声を読み切り、使える行だけのtrain JSONLを作る。"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import soundfile as sf


# 途中で切れた音声も見つけるため、ファイル全体を小さなブロックで読む。
AUDIO_BLOCK_FRAMES = 65_536


def read_audio(path: Path) -> tuple[int, int]:
    """16 kHz WAVを最後まで読めることを確かめ、sample rateとchannel数を返す。"""
    with sf.SoundFile(path, mode="r") as audio:
        if audio.format not in {"WAV", "WAVEX"}:
            raise ValueError(f"unsupported format: {audio.format}")
        if audio.samplerate != 16_000:
            raise ValueError(f"unexpected sample rate: {audio.samplerate}")
        if audio.frames <= 0 or audio.channels <= 0:
            raise ValueError("empty audio")

        frames_read = 0
        while True:
            block = audio.read(
                AUDIO_BLOCK_FRAMES,
                dtype="float32",
                always_2d=True,
            )
            if block.shape[0] == 0:
                break
            frames_read += block.shape[0]
        if frames_read != audio.frames:
            raise ValueError(f"truncated audio: read {frames_read}/{audio.frames} frames")
        return audio.samplerate, audio.channels


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """一時ファイルへJSONLを書き、完成後に置き換える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def main() -> None:
    """既着音声の存在と完全な読取を検証し、検査結果を保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-file", required=True, type=Path)
    parser.add_argument("--audio-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--invalid-report", required=True, type=Path)
    args = parser.parse_args()

    audio_root = args.audio_root.resolve()
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    missing_rows = 0
    channel_counts: Counter[int] = Counter()
    with args.train_file.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            audio_path = Path(row["audio"]).resolve()
            try:
                audio_path.relative_to(audio_root)
            except ValueError as error:
                raise ValueError(
                    f"{args.train_file}:{line_number}: audio path is outside audio-root"
                ) from error

            if not audio_path.is_file():
                missing_rows += 1
                continue
            try:
                _, channels = read_audio(audio_path)
            except (OSError, RuntimeError, ValueError) as error:
                invalid_rows.append(
                    {
                        "id": row["id"],
                        "audio": str(audio_path),
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )
                continue
            channel_counts[channels] += 1
            valid_rows.append(row)

    write_jsonl(args.output, valid_rows)
    write_jsonl(args.invalid_report, invalid_rows)
    print(
        json.dumps(
            {
                "train_rows": len(valid_rows) + missing_rows + len(invalid_rows),
                "valid_rows": len(valid_rows),
                "missing_audio_rows": missing_rows,
                "unreadable_audio_rows": len(invalid_rows),
                "channel_counts": dict(sorted(channel_counts.items())),
                "output": str(args.output),
                "invalid_report": str(args.invalid_report),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
