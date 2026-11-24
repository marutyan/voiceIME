#!/usr/bin/env python3
"""投稿者字幕から、動画が重複しない実音声学習候補を選ぶ。"""

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path.home() / "voiceime-work-real"
PUB = Path.home() / "voiceime-work-pubdata"
JAPANESE = re.compile(r"[ぁ-ゖァ-ヺ㐀-鿿々]")
CUE = re.compile(r"^(?:\[[^\]]*\]|【[^】]*】|（[^）]*）|\([^)]*\)|[♪♫♬\s]+)$")


def contiguous_clips(video, segments):
    """字幕の欠落区間をまたがず、同じ字幕行を使わない最短の連続区間を選ぶ。"""
    ordered = []
    duration_ms = int(video["length"] * 1000)
    for segment in sorted(segments, key=lambda item: item["start"]):
        line = segment["text"].strip()
        start = max(0, int(segment["start"]))
        end = min(duration_ms, start + int(segment["duration"]))
        length = sum(not char.isspace() for char in line)
        if not line or CUE.fullmatch(line) or end <= start:
            ordered.append(None)
        else:
            ordered.append((start, end, line, length))
    windows = []
    alternatives = set()
    for first, segment in enumerate(ordered):
        if segment is None:
            continue
        start, end, _, _ = segment
        parts = []
        length = 0
        first_valid = True
        for last in range(first, len(ordered)):
            item = ordered[last]
            if item is None:
                break
            line_start, line_end, line, line_length = item
            if parts and line_start - end > 1000:
                break
            end = max(end, line_end)
            length += line_length
            if end - start > 15000 or length > 80:
                break
            parts.append(line)
            if 3000 <= end - start and 10 <= length:
                caption = "\n".join(parts)
                if JAPANESE.search(caption):
                    if first_valid:
                        windows.append((last, first, start, end, caption))
                        first_valid = False
                    alternatives.add((start, end, caption))
    # 行番号の早い終点から選ぶと、残りの字幕を最も多く次の区間へ回せる。
    rows = []
    previous = -1
    for last, first, start, end, caption in sorted(windows):
        if first > previous:
            rows.append((start, end, caption))
            previous = last
    used_ranges = {(start, end) for start, end, _ in rows}
    remaining = {}
    for start, end, caption in sorted(alternatives):
        if (start, end) not in used_ranges:
            remaining[(start, end)] = (start, end, caption)
    return rows, list(remaining.values())



def main():
    """全メタデータを走査し、各動画から均等に近い順序で3万件を選ぶ。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    eval_rows = [
        json.loads(line)
        for line in (PUB / "final-manifest/pub-eval.jsonl").read_text().splitlines()
    ]
    excluded = {row["video_id"] for row in eval_rows}
    assert len(eval_rows) == 300 and len(excluded) == 93
    counts = Counter()
    eligible = []
    supplements = {}
    for path in sorted((PUB / "yodas3/data/ja/metadata").glob("*.parquet")):
        for batch in pq.ParquetFile(path).iter_batches(
            columns=["id", "shard", "transcript", "length"], batch_size=256
        ):
            for video in batch.to_pylist():
                counts["metadata_videos"] += 1
                segments = json.loads(video["transcript"] or "null")
                if not segments or any("words" in segment for segment in segments):
                    continue
                counts["manual_caption_videos"] += 1
                if video["id"] in excluded:
                    counts["excluded_pub_eval_videos"] += 1
                    continue
                clips, alternate = contiguous_clips(video, segments)
                if clips:
                    rng.shuffle(clips)
                    eligible.append((video, clips[:40]))
                    if len(clips) < 40 and alternate:
                        random.Random(f"0:{video['id']}").shuffle(alternate)
                        supplements[video["id"]] = alternate[:40 - len(clips)]
        counts["metadata_shards"] += 1
    assert counts["metadata_shards"] == 108 and counts["manual_caption_videos"] == 5182
    assert counts["excluded_pub_eval_videos"] == len(excluded)
    counts["eligible_videos"] = len(eligible)
    counts["eligible_clips_after_cap"] = sum(len(clips) for _, clips in eligible)
    rng.shuffle(eligible)
    output = []
    # 先に字幕行を共有しない区間を使い、不足分だけ別の連続行の組み合わせで補う。
    for depth in (0, 1):
        for rank in range(40):
            for video, clips in eligible:
                if depth:
                    clips = supplements.get(video["id"], [])

                if rank >= len(clips):
                    continue
                start, end, caption = clips[rank]
                video_id = video["id"]
                shard = video["shard"]
                clip_id = f"real-{video_id}-{start}-{end}"
                output.append({
                    "id": clip_id, "video_id": video_id, "speaker": video_id, "shard": shard,
                    "start_ms": start, "end_ms": end, "spoken_text": caption, "supplemental": bool(depth),
                    "audio_path": str(ROOT / "audio" / shard / f"{clip_id}.wav"),
                })
                if len(output) == 30000:
                    break
            if len(output) == 30000:
                break
        if len(output) == 30000:
            break
    ids = {row["id"] for row in output}
    by_video = Counter(row["video_id"] for row in output)
    assert len(ids) == len(output) and not excluded.intersection(by_video)
    assert max(by_video.values()) <= 40
    counts.update({
        "selected_clips": len(output), "selected_videos": len(by_video),
        "selected_supplemental_clips": sum(row["supplemental"] for row in output),
        "selected_audio_ms": sum(row["end_ms"] - row["start_ms"] for row in output),
        "selected_shards": len({row["shard"] for row in output}),
    })
    path = args.output_dir / "candidates.jsonl"
    temp = path.with_suffix(".tmp")
    with temp.open("w") as file:
        for row in output:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    temp.replace(path)
    (args.output_dir / "selection.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(json.dumps(counts), flush=True)


if __name__ == "__main__":
    main()
