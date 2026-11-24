"""実験プロセス中の指定GPU使用率を1秒間隔で記録する。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


def process_exists(pid: int) -> bool:
    """PIDが生存しているか確認し、存在確認以外の権限エラーを伝える。"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_gpu_sample(gpu_index: int) -> tuple[int, int]:
    """nvidia-smiから使用率とVRAM使用量を整数で読む。"""
    result = subprocess.run(
        [
            "nvidia-smi",
            "-i",
            str(gpu_index),
            "--query-gpu=utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    utilization, memory = result.stdout.strip().split(",")
    return int(utilization.strip()), int(memory.strip())


def main() -> None:
    """対象プロセスの終了までCSVを取り、loaded sampleの平均をJSONに残す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--gpu", type=int, default=2)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--loaded-memory-mib", type=int, default=10_000)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if args.pid < 1 or args.gpu < 0 or args.loaded_memory_mib < 0:
        raise ValueError("pid、gpu、loaded-memory-mibの値が不正です")
    if args.interval_seconds <= 0:
        raise ValueError("interval-secondsは0より大きい必要があります")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    all_samples = 0
    loaded_utilizations: list[int] = []
    with args.output.open("w", encoding="utf-8") as output:
        output.write("timestamp_utc,utilization_pct,memory_mib\n")
        output.flush()
        while process_exists(args.pid):
            utilization, memory = read_gpu_sample(args.gpu)
            timestamp = datetime.now(timezone.utc).isoformat()
            output.write(f"{timestamp},{utilization},{memory}\n")
            output.flush()
            all_samples += 1
            if memory >= args.loaded_memory_mib:
                loaded_utilizations.append(utilization)
            time.sleep(args.interval_seconds)

    summary = {
        "pid": args.pid,
        "gpu": args.gpu,
        "all_samples": all_samples,
        "loaded_memory_threshold_mib": args.loaded_memory_mib,
        "loaded_samples": len(loaded_utilizations),
        "loaded_average_gpu_utilization_pct": (
            mean(loaded_utilizations) if loaded_utilizations else None
        ),
        "loaded_nonzero_samples": sum(value > 0 for value in loaded_utilizations),
        "loaded_max_gpu_utilization_pct": (
            max(loaded_utilizations) if loaded_utilizations else None
        ),
        "csv": str(args.output),
    }
    summary_path = args.output.with_suffix(args.output.suffix + ".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
