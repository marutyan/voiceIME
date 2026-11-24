#!/usr/bin/env python3
"""3つのTTS shardを検証し、整形・ASRが読む単一manifestにまとめる。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import wave
from collections import Counter
from pathlib import Path
from typing import Any

from synthesize import SOURCE, TTS_MODEL, length_problem, load_voices, plan_row


SHARD_COUNT = 3
EXPECTED_ROWS = 44_971
EXPECTED_FULL_ROWS = 56_971
OLD_MANIFEST = Path.home() / "voiceime-work-tts/outputs/r3-train-20261122/manifest.jsonl"
VOICES = Path.home() / "voiceime-work-tts/datagen/tts/voices.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、壊れた行を出力不整合として止める。"""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def id_digest(ids: list[str] | set[str]) -> str:
    """ID集合をソートしてSHA-256にし、manifest間の完全性を照合する。"""
    payload = "\n".join(sorted(ids)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256(path: Path) -> str:
    """ファイルのSHA-256を計算する。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def queue_job_result(queue_root: Path, job_name: str) -> dict[str, str]:
    """done/failedのどちらへ移ったjobかと、キューの平均使用率記録を返す。"""
    for state in ("done", "failed"):
        util_path = queue_root / state / f"{job_name}.util"
        if util_path.is_file():
            return {
                "state": state,
                "average_util": util_path.read_text(encoding="utf-8").strip(),
            }
    return {"state": "unavailable", "average_util": "queue .util not found"}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """一時ファイルへ書いてから置き換え、途中のmanifestを完成品に見せない。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def main() -> None:
    """入力shard・音声・既存trainとのID集合を検証して統合する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True, help="faculty_run.shの共通出力親")
    parser.add_argument("--inputs", type=Path, required=True, help="3つの合成入力JSONLがある場所")
    parser.add_argument("--prep-metadata", type=Path, required=True, help="手元で作った集計metadata")
    parser.add_argument("--queue", type=Path, default=Path.home() / "voiceime-queue/done")
    parser.add_argument("--confirmed-missing", help="再試行後も長さの条件を通らなかったと確認済みのID")
    args = parser.parse_args()

    prep = json.loads(args.prep_metadata.read_text(encoding="utf-8"))
    voices = load_voices(VOICES)
    confirmed_missing = {args.confirmed_missing} if args.confirmed_missing else set()
    missing_details = {}
    expected_speakers = Counter(prep["speaker_counts"])
    all_rows: list[dict[str, Any]] = []
    all_meta: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_counts: Counter[str] = Counter()
    speaker_counts: Counter[str] = Counter()
    total_audio_seconds = 0.0
    total_wav_bytes = 0
    shard_summaries = []

    for shard_index in range(SHARD_COUNT):
        shard_name = f"shard-{shard_index:02d}"
        input_path = args.inputs / f"{shard_name}.jsonl"
        output_dir = args.work / shard_name
        input_rows = read_jsonl(input_path)
        if sha256(input_path) != prep["shards"][shard_index]["jsonl_sha256"]:
            raise ValueError(f"{shard_name}: 合成入力のSHA-256が準備時と異なる")
        manifest_path = output_dir / "manifest.jsonl"
        tts_meta_path = output_dir / "tts_meta.jsonl"
        discarded_path = output_dir / "discarded.jsonl"
        manifest_rows = read_jsonl(manifest_path)
        tts_meta_rows = read_jsonl(tts_meta_path)
        discarded_rows = read_jsonl(discarded_path)
        input_ids = [str(row["id"]) for row in input_rows]
        manifest_ids = [str(row["id"]) for row in manifest_rows]
        expected_ids = [row_id for row_id in input_ids if row_id not in confirmed_missing]
        if manifest_ids != expected_ids:
            raise ValueError(
                f"{shard_name}: TTS出力が入力順・件数と不一致 "
                f"(input={len(input_ids)} manifest={len(manifest_ids)} discarded={len(discarded_rows)})"
            )
        if len(manifest_ids) != len(set(manifest_ids)) or seen.intersection(manifest_ids):
            raise ValueError(f"{shard_name}: shard内またはshard間に重複IDがある")
        discarded_ids = [str(row["id"]) for row in discarded_rows]
        if set(discarded_ids) != confirmed_missing.intersection(input_ids) or len(discarded_ids) != len(set(discarded_ids)):
            raise ValueError(f"{shard_name}: 確認済み以外のTTS破棄行がある")
        eligible_rows = []
        for row in input_rows:
            if row["id"] in confirmed_missing:
                plan = plan_row(row, voices, 0)
                speaker = plan["voice"]["speaker"]
                expected_speakers[speaker] -= 1
                missing_details[row["id"]] = {
                    "speaker": speaker, "source": SOURCE[plan["engine"]],
                    "reason": discarded_rows[0]["reason"],
                    "has_omitted_terms": bool(row["omitted_terms"]),
                }
            else:
                eligible_rows.append(row)
        if len(tts_meta_rows) != len(manifest_rows):
            raise ValueError(f"{shard_name}: TTS metadata件数がmanifestと異なる")

        for input_row, row, meta in zip(eligible_rows, manifest_rows, tts_meta_rows, strict=True):
            plan = plan_row(input_row, voices, 0)
            if (
                row["speaker"] != plan["voice"]["speaker"]
                or row["source"] != SOURCE[plan["engine"]]
                or row["spoken_text"] != plan["text"]
                or row["split"] != "train"
                or row["target_text"] != input_row["target_text"]
                or row["omitted_terms"] != input_row["omitted_terms"]
                or meta["id"] != row["id"]
                or meta["tts_model"] != TTS_MODEL[plan["engine"]]
                or meta["speed"] != plan["speed"]
                or meta["intonation"] != plan["intonation"]
            ):
                raise ValueError(f"音声の割当または行の内容が入力と異なる: {row['id']}")
            audio_path = output_dir / str(row["audio_path"])
            if not audio_path.is_file():
                raise FileNotFoundError(f"manifestの音声がない: {audio_path}")
            with wave.open(str(audio_path), "rb") as audio:
                params = audio.getparams()
                if (
                    params.nchannels != 1
                    or params.sampwidth != 2
                    or params.framerate != 16_000
                    or params.comptype != "NONE"
                ):
                    raise ValueError(f"WAV形式が前回条件と異なる: {audio_path} {params}")
                duration = params.nframes / params.framerate
                if length_problem(row["spoken_text"], duration) or abs(duration - meta["duration_s"]) > 0.001:
                    raise ValueError(f"音声長が記録または長さの合格条件と異なる: {audio_path}")
                total_audio_seconds += duration
            total_wav_bytes += audio_path.stat().st_size
            speaker = str(row.get("speaker", ""))
            if speaker not in prep["speaker_counts"]:
                raise ValueError(f"評価用または未割当の声が混じった: {speaker}")
            speaker_counts[speaker] += 1
            source_counts[str(row.get("source", ""))] += 1
            row["audio_path"] = f"{shard_name}/{row['audio_path']}"

        all_rows.extend(manifest_rows)
        all_meta.extend(tts_meta_rows)
        seen.update(manifest_ids)
        job_name = f"80-r3audio-tts-topup44971-{shard_name}"
        queue_result = queue_job_result(args.queue.parent, job_name)
        shard_summaries.append(
            {
                "shard": shard_index,
                "rows": len(manifest_rows),
                "id_sha256": id_digest(manifest_ids),
                "queue_job_state": queue_result["state"],
                "queue_util": queue_result["average_util"],
                "manifest_sha256": sha256(manifest_path),
            }
        )

    all_rows.sort(key=lambda row: row["id"])
    all_meta_by_id: dict[str, dict[str, Any]] = {}
    for meta in all_meta:
        meta_id = str(meta["id"])
        if meta_id in all_meta_by_id:
            raise ValueError(f"TTS metadataに重複IDがある: {meta_id}")
        all_meta_by_id[meta_id] = meta
    all_meta = [all_meta_by_id[row["id"]] for row in all_rows]

    recovery_jobs: dict[str, dict[str, str]] = {}
    for state in ("done", "failed"):
        for job_path in sorted((args.queue.parent / state).glob("80-r3audio-tts-*-topup44971-*.sh")):
            job_name = job_path.stem
            if "-shard-" in job_name and "-resume-" not in job_name and "-rescue-" not in job_name:
                continue
            recovery_jobs[job_name] = queue_job_result(args.queue.parent, job_name)

    actual_ids = {row["id"] for row in all_rows}
    if len(all_rows) != EXPECTED_ROWS - len(confirmed_missing) or len(actual_ids) != len(all_rows):
        raise ValueError(f"統合manifest件数が不正: rows={len(all_rows)}, unique={len(actual_ids)}")
    if set(missing_details) != confirmed_missing or id_digest(actual_ids | confirmed_missing) != prep["remaining_id_sha256"]:
        raise ValueError("TTS出力のID集合が、元trainから既存12,000件を除いた差集合と異なる")
    if speaker_counts != expected_speakers:
        raise ValueError("声ごとの合成件数が割当と一致しない")

    old_rows = read_jsonl(OLD_MANIFEST)
    old_ids = {str(row["id"]) for row in old_rows}
    if len(old_rows) != len(old_ids) or len(old_ids) != 12_000:
        raise ValueError(f"既存train音声manifestが不正な件数: {len(old_ids)}")
    if id_digest(old_ids) != prep["existing_id_sha256"]:
        raise ValueError("前回12,000件のfaculty manifestが入力準備時のID一覧と異なる")
    if actual_ids & old_ids:
        raise ValueError(f"既存12,000件とtop-upのIDが重複: {len(actual_ids & old_ids)}")
    full_ids = actual_ids | old_ids
    if len(full_ids) != EXPECTED_FULL_ROWS - len(confirmed_missing) or id_digest(full_ids | confirmed_missing) != prep["full_train_id_sha256"]:
        raise ValueError("既存音声とtop-up音声のID和集合が全train 56,971件と一致しない")

    manifest_path = args.work / "manifest.jsonl"
    meta_path = args.work / "tts_meta.jsonl"
    write_jsonl(manifest_path, all_rows)
    write_jsonl(meta_path, all_meta)
    metadata = {
        "coverage": "remaining_train_with_confirmed_tts_failures" if confirmed_missing else "complete_remaining_train_rows",
        "source_train_rows": EXPECTED_FULL_ROWS,
        "existing_rows": len(old_ids),
        "topup_rows": len(all_rows),
        "unique_topup_ids": len(actual_ids),
        "missing_topup_ids": sorted(confirmed_missing),
        "missing_topup_details": missing_details,
        "topup_id_sha256": id_digest(actual_ids),
        "full_train_id_sha256": id_digest(full_ids),
        "seed": 0,
        "initial_batch_size": 32,
        "voice_pool": 24,
        "evaluation_voice_rows": 0,
        "speaker_counts": dict(sorted(speaker_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "recovery_queue_jobs": recovery_jobs,
        "audio": {
            "format": "WAV PCM16, 16 kHz, mono",
            "hours": total_audio_seconds / 3600,
            "seconds": total_audio_seconds,
            "bytes": total_wav_bytes,
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "tts_meta_sha256": sha256(meta_path),
        },
        "shards": shard_summaries,
        "outputs": {"manifest": str(manifest_path), "tts_meta": str(meta_path)},
    }
    (args.work / "generation-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
