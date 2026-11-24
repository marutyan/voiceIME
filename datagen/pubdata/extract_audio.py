#!/usr/bin/env python3
"""YODASのtarから選択済みWebMだけを取得し、字幕区間をWAVに切り出す。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Any

import httpx2


REVISION = "3247e8cabda1e8e9418a6d8fe582e8c1abe75861"
DATASET_URL = "https://huggingface.co/datasets/espnet/yodas3.1/resolve"
VIDEO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


# 指定manifestの音声ファイルがWAV契約を満たすか確認する。
def wav_is_valid(path: Path) -> bool:
    """ffprobeを使わず、WAVのチャンネル、標本化周波数、標本幅を調べる。"""
    import wave

    try:
        with wave.open(str(path), "rb") as wav:
            return (
                wav.getnchannels() == 1
                and wav.getframerate() == 16_000
                and wav.getsampwidth() == 2
                and wav.getnframes() > 0
            )
    except (wave.Error, OSError):
        return False


# 選択した2分割のmanifestを読み、動画IDと字幕区間を対応付ける。
def read_manifests(paths: list[Path], audio_root: Path) -> dict[str, list[dict[str, Any]]]:
    """出力先を音声ルート内に限定し、動画ごとに行をまとめる。"""
    rows_by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    resolved_root = audio_root.resolve()
    for path in paths:
        with path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                video_id = str(row.get("video_id", ""))
                if not VIDEO_ID_PATTERN.fullmatch(video_id):
                    raise ValueError(f"{path}:{line_number}: YODASのvideo_id形式が不正です")
                output = Path(str(row.get("audio_path", ""))).resolve()
                if not output.is_relative_to(resolved_root):
                    raise ValueError(f"{path}:{line_number}: audio_pathが音声ルート外です")
                if int(row["end_ms"]) <= int(row["start_ms"]):
                    raise ValueError(f"{path}:{line_number}: 音声区間の長さが正でありません")
                row["_audio_path"] = str(output)
                rows_by_video[video_id].append(row)
    return dict(rows_by_video)


# HTTP Range応答が要求したtar位置と一致することを確かめて読む。
def read_range(client: httpx2.Client, url: str, start: int, end: int) -> bytes:
    """必要な範囲だけ取得し、Range非対応時の全件取得を防ぐ。"""
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    for attempt in range(5):
        try:
            with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 206:
                    raise RuntimeError(f"HTTP Range応答が206ではありません: {response.status_code}")
                content_range = response.headers.get("content-range", "")
                if not content_range.startswith(f"bytes {start}-{end}/"):
                    raise RuntimeError("HTTP Content-Rangeが要求位置と一致しません")
                data = response.read()
            if len(data) != end - start + 1:
                raise RuntimeError("HTTP Range応答のbyte数が一致しません")
            return data
        except (httpx2.HTTPError, OSError):
            if attempt == 4:
                raise RuntimeError("HTTP Range取得に5回失敗しました") from None
            time.sleep(1 + attempt)
    raise RuntimeError("HTTP Range取得に失敗しました")


# tar headerのoctal size fieldを整数へ変換する。
def tar_member_size(header: bytes) -> int:
    """通常のustar octal size fieldを検査してbyte数を返す。"""
    raw_size = header[124:136].strip(b"\0 ")
    if not raw_size:
        return 0
    try:
        return int(raw_size, 8)
    except ValueError as error:
        raise RuntimeError("tar headerのsize fieldがoctalではありません") from error


# tar headerの名前とchecksumを読み、破損やRange位置のずれを検知する。
def tar_member_name(header: bytes) -> str:
    """ustar prefixとnameを結合し、checksumの一致を確認する。"""
    stored_checksum = int(header[148:156].strip(b"\0 ") or b"0", 8)
    calculated_checksum = sum(header[:148]) + 8 * 32 + sum(header[156:])
    if stored_checksum != calculated_checksum:
        raise RuntimeError("tar headerのchecksumが一致しません")
    name = header[:100].split(b"\0", 1)[0].decode("utf-8", "replace")
    prefix = header[345:500].split(b"\0", 1)[0].decode("utf-8", "replace")
    return f"{prefix}/{name}" if prefix else name


# 1つのWebMを分割し、全字幕区間をPCM16の16kHzモノラルWAVへ保存する。
def cut_video(webm_path: Path, rows: list[dict[str, Any]]) -> tuple[int, float, int]:
    """各動画を一度decodeし、atrimで選択済みの字幕区間を取り出す。"""
    for row in rows:
        Path(row["_audio_path"]).parent.mkdir(parents=True, exist_ok=True)
    pending = [row for row in rows if not wav_is_valid(Path(row["_audio_path"]))]
    if not pending:
        return 0, 0.0, 0

    input_labels = "".join(f"[in{index}]" for index in range(len(pending)))
    filters = [f"[0:a:0]asplit={len(pending)}{input_labels}"]
    for index, row in enumerate(pending):
        start = int(row["start_ms"]) / 1000
        end = int(row["end_ms"]) / 1000
        filters.append(
            f"[in{index}]atrim=start={start:.3f}:end={end:.3f},"
            f"asetpts=PTS-STARTPTS[out{index}]"
        )
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(webm_path),
               "-filter_complex", ";".join(filters)]
    for index, row in enumerate(pending):
        command.extend([
            "-map", f"[out{index}]", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", "-sample_fmt", "s16", row["_audio_path"],
        ])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpegが終了コード{result.returncode}で失敗しました: {result.stderr[-500:]}")

    invalid = [row["id"] for row in pending if not wav_is_valid(Path(row["_audio_path"]))]
    if invalid:
        raise RuntimeError(f"WAV形式の確認に失敗しました: {invalid[:5]}")
    duration_s = sum((int(row["end_ms"]) - int(row["start_ms"])) / 1000 for row in pending)
    wav_bytes = sum(Path(row["_audio_path"]).stat().st_size for row in pending)
    return len(pending), duration_s, wav_bytes


# 1つのshardをRangeで走査し、manifestにあるWebMだけ取得する。
def extract_shard(
    shard: str,
    rows_by_video: dict[str, list[dict[str, Any]]],
    revision: str,
    source_root: Path,
) -> dict[str, Any]:
    """tar内の選択WebMだけを一時保存し、切り出し後に削除する。"""
    wanted = {
        video_id
        for video_id, rows in rows_by_video.items()
        if rows[0]["shard"] == shard
        and any(not wav_is_valid(Path(row["_audio_path"])) for row in rows)
    }
    if not wanted:
        return {"shard": shard, "videos": 0, "clips": 0, "archive_header_bytes": 0,
                "audio_member_bytes": 0, "clip_duration_s": 0.0, "wav_bytes": 0}

    url = f"{DATASET_URL}/{revision}/data/ja/audio/{shard}.tar"
    source_root.mkdir(parents=True, exist_ok=True)
    remaining = set(wanted)
    extracted_videos = 0
    clip_count = 0
    header_bytes = 0
    audio_member_bytes = 0
    clip_duration_s = 0.0
    wav_bytes = 0

    with httpx2.Client(follow_redirects=True, timeout=120) as client:
        with client.stream("HEAD", url, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200:
                raise RuntimeError(f"tarのHEAD取得に失敗しました: HTTP {response.status_code}")
            total_size = int(response.headers.get("content-length", "0"))
        if total_size <= 0:
            raise RuntimeError("tarのContent-Lengthを取得できません")

        offset = 0
        header_requests = 0
        while offset + 512 <= total_size and remaining:
            header = read_range(client, url, offset, offset + 511)
            header_bytes += len(header)
            header_requests += 1
            if header_requests % 1000 == 0:
                print(
                    f"shard {shard}: scanned {offset / total_size:.1%} of tar headers, "
                    f"{len(wanted) - len(remaining)}/{len(wanted)} selected videos found",
                    flush=True,
                )
            if header == bytes(512):
                break
            name = tar_member_name(header)
            size = tar_member_size(header)
            member_data_offset = offset + 512
            next_offset = member_data_offset + ((size + 511) // 512) * 512
            member_name = PurePosixPath(name).name
            if member_name.endswith(".webm"):
                video_id = member_name[:-5]
                if video_id in remaining:
                    source_path = source_root / f"{video_id}.webm"
                    temporary_path = source_path.with_suffix(".webm.part")
                    body = read_range(client, url, member_data_offset, member_data_offset + size - 1)
                    temporary_path.write_bytes(body)
                    temporary_path.replace(source_path)
                    audio_member_bytes += size
                    clip_rows = rows_by_video[video_id]
                    clips, duration_s, bytes_written = cut_video(source_path, clip_rows)
                    source_path.unlink()
                    extracted_videos += 1
                    clip_count += clips
                    clip_duration_s += duration_s
                    wav_bytes += bytes_written
                    remaining.remove(video_id)
            offset = next_offset

    if remaining:
        raise RuntimeError(f"選択したWebMがshard内に見つかりません: {len(remaining)}件")
    return {
        "shard": shard,
        "videos": extracted_videos,
        "clips": clip_count,
        "archive_header_bytes": header_bytes,
        "audio_member_bytes": audio_member_bytes,
        "clip_duration_s": clip_duration_s,
        "wav_bytes": wav_bytes,
    }


# 入力manifestをshard単位で処理し、音声生成の実績を保存する。
def main() -> None:
    """GPUを使わず、選択済みの音声だけをfaculty上で切り出す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-manifest", type=Path, required=True)
    parser.add_argument("--pool-manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workersは1以上にしてください")

    rows_by_video = read_manifests(
        [args.eval_manifest, args.pool_manifest], args.audio_root
    )
    shards = sorted({rows[0]["shard"] for rows in rows_by_video.values()})
    shard_results = []
    with ThreadPoolExecutor(max_workers=min(args.workers, len(shards))) as executor:
        futures = {
            executor.submit(
                extract_shard, shard, rows_by_video, args.revision, args.source_root
            ): shard
            for shard in shards
        }
        for future in as_completed(futures):
            result = future.result()
            shard_results.append(result)
            print(
                f"shard {result['shard']}: {result['videos']} videos, "
                f"{result['clips']} clips, "
                f"{result['archive_header_bytes']} header bytes, "
                f"{result['audio_member_bytes']} selected WebM bytes",
                flush=True,
            )
    shard_results.sort(key=lambda result: result["shard"])
    missing = [
        row["id"]
        for rows in rows_by_video.values()
        for row in rows
        if not wav_is_valid(Path(row["_audio_path"]))
    ]
    if missing:
        raise RuntimeError(f"WAVが不足しています: {len(missing)}件")

    stats = {
        "dataset": "espnet/yodas3.1",
        "revision": args.revision,
        "method": "HTTP Rangeでtar headerを512 byteずつ読み、選択WebMだけ取得してffmpegで字幕区間を切り出す。",
        "video_count": len(rows_by_video),
        "clip_count": sum(len(rows) for rows in rows_by_video.values()),
        "shards": shard_results,
        "archive_header_bytes": sum(item["archive_header_bytes"] for item in shard_results),
        "audio_member_bytes": sum(item["audio_member_bytes"] for item in shard_results),
        "clip_duration_s": sum(
            (int(row["end_ms"]) - int(row["start_ms"])) / 1000
            for rows in rows_by_video.values()
            for row in rows
        ),
        "wav_bytes": sum(
            Path(row["_audio_path"]).stat().st_size
            for rows in rows_by_video.values()
            for row in rows
        ),
        "all_wavs_valid": True,
    }
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    args.stats.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
