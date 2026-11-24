#!/usr/bin/env python3
"""選択した動画のWebMだけをRange取得し、16kHzのWAVに切り出す。"""

import argparse
import json
import re
import subprocess
import threading
import time
import wave
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

import httpx2

from extract_audio import DATASET_URL, REVISION, tar_member_name, tar_member_size

ROOT = Path.home() / "voiceime-work-real"
# WAVの上限14.4 GBと合わせても、32本の一時WebMを含めて30 GBを下回る。
MAX_MEMBER_BYTES = 450_000_000
# 匿名の解決リクエストの制限は3,000件/5分。共有IPの他の通信にも余裕を残す。
REQUEST_INTERVAL_S = 0.125
RATE_LOCK = threading.Lock()
next_request_at = 0.0


def usable_wav(row):
    """サンプル形式と字幕区間に対する長さを検証する。"""
    try:
        with wave.open(row["audio_path"], "rb") as wav:
            expected = (row["end_ms"] - row["start_ms"]) * 16
            return (
                wav.getnchannels() == 1
                and wav.getframerate() == 16000
                and wav.getsampwidth() == 2
                and abs(wav.getnframes() - expected) <= 160
            )
    except (OSError, EOFError, wave.Error):
        return False


def wait_for_request():
    """すべてのshardで発行間隔とHTTP 429後の解除時刻を共有する。"""
    global next_request_at
    while True:
        with RATE_LOCK:
            now = time.monotonic()
            delay = next_request_at - now
            if delay <= 0:
                next_request_at = now + REQUEST_INTERVAL_S
                return
        time.sleep(delay)


def pause_after_rate_limit(headers):
    """Hubが通知した解除時刻まで新しいRange要求を止める。"""
    global next_request_at
    reset = re.search(r"(?:^|;)t=(\d+)", headers.get("ratelimit", ""))
    retry = headers.get("retry-after", "")
    delay = max(int(reset[1]) + 2 if reset else 60, int(retry) if retry.isdigit() else 0)
    with RATE_LOCK:
        until = time.monotonic() + delay
        if until > next_request_at + 5:
            print(f"Hub HTTP 429: Range要求を{delay}秒待機", flush=True)
        next_request_at = max(next_request_at, until)


def get_range(client, url, start, end, target=None):
    """Range応答の位置と長さを確認し、音声をストリームで一時保存する。"""
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    attempt = 0
    while attempt < 5:
        wait_for_request()
        try:
            with client.stream("GET", url, headers=headers) as response:
                if response.status_code == 429:
                    pause_after_rate_limit(response.headers)
                    continue
                actual = response.headers.get("content-range", "")
                if response.status_code != 206 or not actual.startswith(f"bytes {start}-{end}/"):
                    raise RuntimeError(f"HTTP Range応答不一致 (status {response.status_code})")
                if target is None:
                    data = response.read()
                    if len(data) != end - start + 1:
                        raise RuntimeError("tar headerの取得長が不正")
                    return data, int(actual.rsplit("/", 1)[-1])
                received = 0
                with target.open("wb") as output:
                    for block in response.iter_bytes():
                        received += len(block)
                        if received > end - start + 1:
                            raise RuntimeError("WebMの応答長が上限を超過")
                        output.write(block)
                if received != end - start + 1:
                    raise RuntimeError("WebMの取得長が不正")
                return None, received
        except (httpx2.HTTPError, RuntimeError, OSError) as error:
            attempt += 1
            if attempt == 5:
                detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
                raise RuntimeError(f"Range {start}-{end} を取得できない ({detail})") from None
            time.sleep(1 + 2 * attempt)


def cut_audio(source, rows):
    """各動画を一度デコードし、区間ごとに検証済みWAVを確定する。"""
    filters = ["[0:a:0]asplit=" + str(len(rows)) + "".join(f"[i{i}]" for i in range(len(rows)))]
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-filter_complex_threads", "1", "-threads", "1", "-i", str(source),
    ]
    outputs = []
    for i, row in enumerate(rows):
        start = row["start_ms"] / 1000
        end = row["end_ms"] / 1000
        filters.append(f"[i{i}]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[o{i}]")
        path = Path(row["audio_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        outputs.append((row, path.with_suffix(".part.wav"), path))
    command.extend(["-filter_complex", ";".join(filters)])
    for i, (_, temporary, _) in enumerate(outputs):
        command.extend(["-map", f"[o{i}]", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(temporary)])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        print(f"ffmpeg {source.stem}: {result.stderr[-500:]}", flush=True)
    for row, temporary, path in outputs:
        if usable_wav({**row, "audio_path": str(temporary)}):
            temporary.replace(path)
        else:
            temporary.unlink(missing_ok=True)


def extract_shard(shard, by_video, *, start_offset=0):
    """tar headerを順にたどり、候補の動画だけを取得する。"""
    remaining = {
        video_id: [row for row in rows if not usable_wav(row)]
        for video_id, rows in by_video.items()
    }
    remaining = {video_id: rows for video_id, rows in remaining.items() if rows}
    url = f"{DATASET_URL}/{REVISION}/data/ja/audio/{shard}.tar"
    tmp = ROOT / "tmp-webm" / f"{shard}.webm"
    headers = downloaded = 0
    errors = {}
    try:
        with httpx2.Client(follow_redirects=True, timeout=90) as client:
            offset = start_offset
            while remaining:
                header, total = get_range(client, url, offset, offset + 511)
                headers += 1
                if headers % 250 == 0:
                    print(f"{shard}: header={headers} 残り動画={len(remaining)}", flush=True)
                if header == bytes(512):
                    break
                size = tar_member_size(header)
                name = PurePosixPath(tar_member_name(header)).name
                data_offset = offset + 512
                offset = data_offset + ((size + 511) // 512) * 512
                if name.endswith(".webm") and name[:-5] in remaining:
                    video_id = name[:-5]
                    rows = remaining.pop(video_id)
                    try:
                        if not 0 < size <= MAX_MEMBER_BYTES:
                            raise RuntimeError(f"一時WebMの上限外: {size} bytes")
                        _, received = get_range(client, url, data_offset, data_offset + size - 1, tmp)
                        downloaded += received
                        cut_audio(tmp, rows)
                    except RuntimeError as error:
                        errors[video_id] = str(error)
                    finally:
                        tmp.unlink(missing_ok=True)
                if offset + 512 > total:
                    break
    except RuntimeError as error:
        errors["archive"] = str(error)
    if remaining:
        errors["unvisited_videos"] = len(remaining)
    rows = [row for group in by_video.values() for row in group]
    valid = [row for row in rows if usable_wav(row)]
    invalid = sorted({row["id"] for row in rows} - {row["id"] for row in valid})
    result = {
        "shard": shard, "headers": headers, "webm_bytes": downloaded,
        "valid": len(valid), "invalid_ids": invalid, "errors": errors,
        "wav_bytes": sum(Path(row["audio_path"]).stat().st_size for row in valid),
    }
    print(f"{shard}: WAV {len(valid)}/{len(rows)} 件、エラー {len(errors)}", flush=True)
    return valid, result


def write_json(path, data):
    """集計を一時ファイルから確定する。"""
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def main():
    """集計をshardごとに保存し、追加取得後も検証済みWAVを再利用する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 33), default=32)
    parser.add_argument("--manifest", type=Path, default=ROOT / "candidates.jsonl")
    parser.add_argument("--shard")
    args = parser.parse_args()
    groups = defaultdict(lambda: defaultdict(list))
    for line in args.manifest.read_text().splitlines():
        row = json.loads(line)
        if args.shard is None or row["shard"] == args.shard:
            groups[row["shard"]][row["video_id"]].append(row)
    assert groups and all(re.fullmatch(r"\d{4}", shard) for shard in groups)
    (ROOT / "tmp-webm").mkdir(exist_ok=True)
    status = ROOT / "extract-status"
    status.mkdir(exist_ok=True)
    # 候補の多いshardから始めると、同じRange要求数で早く多くの音声が揃う。
    shard_order = sorted(groups, key=lambda shard: (-sum(map(len, groups[shard].values())), shard))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(extract_shard, shard, groups[shard]): shard for shard in shard_order
        }
        for future in as_completed(futures):
            shard = futures[future]
            valid, result = future.result()
            path = status / f"{shard}.jsonl"
            temp = path.with_suffix(".tmp")
            temp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in valid))
            temp.replace(path)
            write_json(status / f"{shard}.json", result)


if __name__ == "__main__":
    main()
