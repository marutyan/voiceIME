#!/usr/bin/env python3
"""条件Dの学習用パイプラインを再利用して、実音声の認識を行う。"""

import argparse
import itertools
import json
import time
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import train_pipeline as pipeline
from voiceime.asr.base import load_audio
from voiceime.formatter.glossary import load_glossary, load_term_list

ROOT = Path.home() / "voiceime-work-real"
PUB = Path.home() / "voiceime-work-pubdata"
NOVEL = Path.home() / "voiceime-work-fr3/inputs/test-novel-20261122/test-novel.jsonl"


def term_key(surface):
    """大文字小文字と全角半角だけが違う語も除外対象に含める。"""
    return unicodedata.normalize("NFKC", surface).casefold()


def duration(row):
    """検証済みWAVの実長をbatchの並べ替えに使う。"""
    with wave.open(row["audio_path"], "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def first_pass(records, shard):
    """ヒントなしHaasを同じ設定で実行し、認識済みshardは再利用する。"""
    output = pipeline.OUTPUTS / f"haas-firstpass-shard-{shard:02d}.jsonl"
    if output.exists():
        rows = pipeline.read_jsonl(output)
        assert [row["id"] for row in rows] == [row["id"] for row in records]
        return rows

    def run_batch(group):
        """1つのHaas workerで割り当てられた音声を認識する。"""
        worker = pipeline.SpeechWorker(pipeline.HAAS_THREADS_PER_WORKER)
        try:
            rows = []
            for record in group:
                audio = load_audio(Path(record["audio_abs"]))
                started = time.perf_counter()
                transcription = worker.transcribe(audio, None)
                rows.append({
                    "id": record["id"],
                    "haas_first_pass_hyp": transcription.text,
                    "haas_first_pass_latency_s": time.perf_counter() - started,
                })
                if len(rows) % 100 == 0 and group[0] is records[0]:
                    print(f"Haas 1回目: {len(rows)}/{len(group)} (worker 0)", flush=True)
            return rows
        finally:
            worker.close()

    count = min(len(records), pipeline.HAAS_WORKERS_PER_GPU)
    with ThreadPoolExecutor(max_workers=count) as pool:
        groups = list(pool.map(run_batch, [records[i::count] for i in range(count)]))
    indexed = {row["id"]: row for row in itertools.chain.from_iterable(groups)}
    rows = [indexed[record["id"]] for record in records]
    pipeline.write_jsonl(output, rows)
    return rows


def main():
    """対象manifestと除外用語を固定し、割当GPUで3つの仮説を作る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dataset", choices=["train", "pub-eval"], required=True)
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()

    pipeline.assigned_gpu()
    exclusions = load_term_list(pipeline.TRAIN_EXCLUSIONS)
    novel = {term for row in pipeline.read_jsonl(NOVEL) for term in row["novel_terms"]}
    assert len(novel) == 500
    args.output.mkdir(parents=True, exist_ok=True)
    pipeline.OUTPUTS = args.output
    pipeline.SPEECH = ROOT / "scripts/haas_worker.sh"
    pipeline.TRAIN_EXCLUSIONS = args.output / "excluded.txt"
    masks = {term_key(term) for term in exclusions | novel}
    variants = {
        entry.surface for entry in load_glossary(pipeline.GLOSSARY_V1, pipeline.GLOSSARY_V2)
        if term_key(entry.surface) in masks
    }
    excluded_surfaces = exclusions | novel | variants
    pipeline.TRAIN_EXCLUSIONS.write_text("".join(f"{term}\n" for term in sorted(excluded_surfaces)))
    rows = pipeline.read_jsonl(args.manifest)
    assert rows and len(rows) == len({row["id"] for row in rows})
    excluded_videos = {row["video_id"] for row in pipeline.read_jsonl(PUB / "final-manifest/pub-eval.jsonl")}
    if args.dataset == "train":
        assert not excluded_videos.intersection(row["video_id"] for row in rows)
    else:
        assert len(rows) == 300 and {row["video_id"] for row in rows} == excluded_videos
    records = [
        {
            **row, "dataset": args.dataset, "duration_s": duration(row),
            "audio_abs": row["audio_path"], "target_text": row["spoken_text"],
        }
        for row in rows
    ]
    records.sort(key=lambda row: (-row["duration_s"], row["id"]))
    qwen_path, qwen_run = pipeline.qwen_firstpass(args.shard, records)
    plain_rows = first_pass(records, args.shard)
    for row, plain in zip(records, plain_rows, strict=True):
        row.update(plain)
    combined_path, twopass_run = pipeline.run_twopass(
        args.shard, records, pipeline.read_jsonl(qwen_path)
    )
    combined_rows = pipeline.read_jsonl(combined_path)
    pipeline.validate_output_rows(combined_rows, [row["id"] for row in records], combined_path)
    assert all(
        term_key(entry["surface"]) not in masks
        for row in combined_rows
        for entry in row["formatter_glossary"]
    )
    metadata = {
        "dataset": args.dataset, "rows": len(combined_rows),
        "manifest_sha256": pipeline.file_sha256(args.manifest),
        "excluded_terms": len(excluded_surfaces),
        "qwen": qwen_run, "twopass": twopass_run,
    }
    (args.output / "asr-summary.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
