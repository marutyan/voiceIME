#!/usr/bin/env python3
"""B学習の既存実ASR行へ、同じQwen3-ASR 0.6Bで仮説を追加する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """空行を除いたJSONLを辞書の配列として読む。"""
    with path.open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"JSON objectでない行があります: {path}")
    return rows


def sha256(path: Path) -> str:
    """再現用に入力ファイルのSHA-256を返す。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    """既存のB実ASR IDだけを、他の出力先へ分けてQwen推論する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--legacy-asr", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    pipeline_dir = args.pipeline_dir.expanduser().resolve()
    if str(pipeline_dir) not in sys.path:
        sys.path.insert(0, str(pipeline_dir))
    import train_pipeline as pipeline

    legacy_rows = read_jsonl(args.legacy_asr)
    legacy_ids = [str(row.get("id", "")) for row in legacy_rows]
    if not all(legacy_ids) or len(set(legacy_ids)) != len(legacy_ids):
        raise ValueError("既存ASR runのIDが空または重複しています")

    manifest_rows = read_jsonl(args.manifest)
    manifest_ids = [str(row.get("id", "")) for row in manifest_rows]
    if len(set(manifest_ids)) != len(manifest_ids):
        raise ValueError("Qwen ASR用manifestに重複IDがあります")
    by_id = {row["id"]: row for row in manifest_rows}
    missing_ids = [sample_id for sample_id in legacy_ids if sample_id not in by_id]
    if missing_ids:
        raise ValueError(f"Qwen ASR用manifestに既存ASR行がありません: {len(missing_ids)}件")

    # 学習時と同じID順を保ち、既存ASRのないmanifest行をQwenへ渡さない。
    records = []
    for sample_id in legacy_ids:
        record = dict(by_id[sample_id])
        audio_path = (args.manifest.parent / record["audio_path"]).resolve()
        if not audio_path.is_file():
            raise FileNotFoundError(f"既存ASR行の音声がありません: {sample_id}")
        record["audio_abs"] = str(audio_path)
        records.append(record)

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"既存の補完出力を上書きしません: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pipeline.OUTPUTS = args.output_dir
    output_path, run_metadata = pipeline.qwen_firstpass(99, records)
    output_rows = read_jsonl(output_path)
    output_ids = [row.get("id") for row in output_rows]
    if output_ids != legacy_ids:
        raise ValueError("生成したQwen仮説のID順が既存ASR行と一致しません")

    metadata = {
        "rows": len(output_rows),
        "legacy_asr": str(args.legacy_asr),
        "legacy_asr_sha256": sha256(args.legacy_asr),
        "manifest": str(args.manifest),
        "manifest_sha256": sha256(args.manifest),
        "qwen_hypothesis": str(output_path),
        "qwen_hypothesis_sha256": sha256(output_path),
        "run": run_metadata,
    }
    metadata_path = args.output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
