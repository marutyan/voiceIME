#!/usr/bin/env python3
"""RangeでHTTP 502が続いたシャードを、失敗した位置から再取得する。"""

import json
import os
import re
import time
from collections import defaultdict

import extract_clips
from prepare import ROOT, read_rows, write_rows

LARGE_SHARDS = {"0105", "0106"}


def main():
    """一次取得を終えたシャードについて、未取得分だけを一度再試行する。"""
    groups = defaultdict(lambda: defaultdict(list))
    for row in read_rows(ROOT / "selection-v3/candidates.jsonl"):
        groups[row["shard"]][row["video_id"]].append(row)
    status = ROOT / "extract-status"
    output = ROOT / "recovery-status"
    output.mkdir(exist_ok=True)
    checked = set()
    extraction_pid = int((ROOT / "logs/extraction.pid").read_text())
    while checked != set(groups):
        ready = sorted(
            {file.stem for file in status.glob("*.json")} - checked,
            key=lambda shard: (shard not in LARGE_SHARDS, shard),
        )
        for shard in ready:
            checked.add(shard)
            source = json.loads((status / f"{shard}.json").read_text())
            error = source["errors"].get("archive", "")
            match = re.search(r"^Range (\d+)-\d+ .*status 502", error)
            if not match or (output / f"{shard}.json").exists():
                continue
            # 一次取得と並行する間は合計9リクエスト/秒を上限とする。
            extract_clips.REQUEST_INTERVAL_S = 0.125 if (ROOT / "logs/extraction-complete").exists() else 1.0
            rows, result = extract_clips.extract_shard(shard, groups[shard], start_offset=int(match[1]))
            write_rows(output / f"{shard}.jsonl", rows)
            extract_clips.write_json(output / f"{shard}.json", result)
            print(f"{shard}: 再取得でWAV {result['valid'] - source['valid']} 件追加", flush=True)
        if checked == set(groups):
            break
        try:
            os.kill(extraction_pid, 0)
        except ProcessLookupError:
            if {file.stem for file in status.glob("*.json")} <= checked:
                raise RuntimeError("シャードの一次取得が途中で終了した") from None
        time.sleep(60)


if __name__ == "__main__":
    main()
