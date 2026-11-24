"""Qwen3-ASRの音声をlog-mel特徴へ変換し、再利用できる形で保存する。"""

from __future__ import annotations

import argparse
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import soundfile as sf
from transformers import WhisperFeatureExtractor


# 抽出条件を公式trainerとそろえ、保存した特徴をそのまま再利用する。
_SAMPLE_RATE = 16_000
_FEATURE_EXTRACTOR: WhisperFeatureExtractor | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """1行1件のJSON objectを読み込み、不正な行を示す。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(row)
    return rows


def init_worker(model_path: str) -> None:
    """各workerへCPU用log-mel抽出器を一度だけ読み込む。"""
    global _FEATURE_EXTRACTOR
    _FEATURE_EXTRACTOR = WhisperFeatureExtractor.from_pretrained(model_path)


def extract_features(audio_path: str) -> dict[str, np.ndarray]:
    """境界条件の異なるlog-melを保存し、batch内の位置に合わせて再利用する。"""
    if _FEATURE_EXTRACTOR is None:
        raise RuntimeError("feature extractorが初期化されていません")
    waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
    if sample_rate != _SAMPLE_RATE or waveform.ndim != 1 or waveform.size == 0:
        raise ValueError(f"音声の形式が想定外です: {audio_path}")
    if not np.isfinite(waveform).all():
        raise ValueError(f"音声にNaNまたはInfがあります: {audio_path}")
    if waveform.size > _FEATURE_EXTRACTOR.n_samples:
        raise ValueError(f"30秒を超える音声です: {audio_path}")
    reflect = _FEATURE_EXTRACTOR(
        waveform,
        sampling_rate=_SAMPLE_RATE,
        padding=False,
        truncation=False,
        return_attention_mask=True,
        return_tensors="np",
    )
    reflect_features = np.asarray(reflect["input_features"], dtype=np.float32)[0]
    reflect_mask = np.asarray(reflect["attention_mask"], dtype=np.int64)[0]
    feature_length = int(reflect_mask.sum())
    zero_padded_waveform = np.pad(
        waveform, (0, _FEATURE_EXTRACTOR.n_samples - waveform.size)
    )
    zero_padded = _FEATURE_EXTRACTOR(
        zero_padded_waveform,
        sampling_rate=_SAMPLE_RATE,
        padding=False,
        truncation=False,
        return_attention_mask=False,
        return_tensors="np",
    )
    zero_padded_features = np.asarray(
        zero_padded["input_features"], dtype=np.float32
    )[0]
    if (
        reflect_features.ndim != 2
        or reflect_features.shape[-1] != feature_length
        or zero_padded_features.ndim != 2
        or zero_padded_features.shape[-1] != _FEATURE_EXTRACTOR.nb_max_frames
        or not np.isfinite(reflect_features).all()
        or not np.isfinite(zero_padded_features).all()
    ):
        raise ValueError(f"log-mel特徴が無効です: {audio_path}")
    return {
        "reflect_features": reflect_features,
        "zero_padded_features": zero_padded_features,
        "sample_count": np.asarray(waveform.size, dtype=np.int64),
        "feature_length": np.asarray(feature_length, dtype=np.int64),
    }


def cache_one(row: dict[str, Any], cache_dir: Path) -> str:
    """1件の音声特徴を専用ファイルへ保存し、そのpathを返す。"""
    sample_id = row.get("id")
    audio_path = row.get("audio")
    if not isinstance(sample_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", sample_id
    ):
        raise ValueError(f"cache filenameに使えないidです: {sample_id}")
    if not isinstance(audio_path, str) or not audio_path:
        raise ValueError(f"{sample_id}: audio pathがありません")
    output_path = cache_dir / f"{sample_id}.npz"
    if output_path.is_file():
        with np.load(output_path, allow_pickle=False) as cached:
            reflect_features = cached["reflect_features"]
            zero_padded_features = cached["zero_padded_features"]
            sample_count = cached["sample_count"]
            feature_length = cached["feature_length"]
        if (
            reflect_features.ndim == 2
            and zero_padded_features.ndim == 2
            and sample_count.ndim == 0
            and feature_length.ndim == 0
            and np.isfinite(reflect_features).all()
            and np.isfinite(zero_padded_features).all()
        ):
            return str(output_path)
        raise ValueError(f"既存feature cacheが不正です: {output_path}")

    features = extract_features(audio_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".npz.tmp")
    with temporary_path.open("wb") as output:
        np.savez(output, **features)
    os.replace(temporary_path, output_path)
    return str(output_path)


def verify_batched_equivalence(
    rows: list[dict[str, Any]],
    cache_paths: list[str],
    extractor: WhisperFeatureExtractor,
) -> dict[str, Any]:
    """batch内のpadding条件を再現した特徴とmaskを通常処理と比較する。"""
    selected = rows[: min(2, len(rows))]
    if not selected:
        raise ValueError("入力manifestが空です")
    waveforms = []
    for row in selected:
        waveform, sample_rate = sf.read(
            row["audio"], dtype="float32", always_2d=False
        )
        if sample_rate != _SAMPLE_RATE or waveform.ndim != 1:
            raise ValueError(f"検証用音声の形式が想定外です: {row['id']}")
        waveforms.append(waveform)
    reference = extractor(
        waveforms,
        sampling_rate=_SAMPLE_RATE,
        padding=True,
        truncation=False,
        return_attention_mask=True,
        return_tensors="np",
    )
    maximum_sample_count = max(len(waveform) for waveform in waveforms)
    maximum_feature_frames = reference["input_features"].shape[-1]
    hop_length = extractor.hop_length
    maximum_absolute_difference = 0.0
    for index, _row in enumerate(selected):
        with np.load(cache_paths[index], allow_pickle=False) as cached:
            sample_count = int(cached["sample_count"])
            feature_key = (
                "reflect_features"
                if sample_count == maximum_sample_count
                else "zero_padded_features"
            )
            saved_features = cached[feature_key][:, :maximum_feature_frames]
            reference_features = reference["input_features"][index]
            reference_mask = reference["attention_mask"][index]
            cached_mask = np.zeros(maximum_feature_frames, dtype=np.int64)
            valid_frames = min(
                (sample_count + hop_length - 1) // hop_length,
                maximum_feature_frames,
            )
            cached_mask[:valid_frames] = 1
            if not np.array_equal(reference_mask, cached_mask):
                raise ValueError("cacheとbatch抽出のattention maskが一致しません")
            difference = float(
                np.max(np.abs(reference_features - saved_features), initial=0.0)
            )
            maximum_absolute_difference = max(
                maximum_absolute_difference, difference
            )
            if not np.array_equal(reference_features, saved_features):
                raise ValueError(
                    f"cacheとbatch抽出のlog-melが一致しません: max_abs_diff={difference}"
                )
    return {
        "verified_rows": len(selected),
        "max_absolute_difference": maximum_absolute_difference,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """完成manifestを一時ファイル経由で確定する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary_path, path)


def main() -> None:
    """feature cacheとaudio_features列付きmanifestを作成する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--output-file", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workersは1以上である必要があります")

    rows = read_jsonl(args.input_file)
    if not rows:
        raise ValueError("入力manifestが空です")
    sample_ids = [row.get("id") for row in rows]
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("入力manifestに重複idがあります")
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    output_rows: list[dict[str, Any] | None] = [None] * len(rows)
    cache_paths: list[str | None] = [None] * len(rows)
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=init_worker,
        initargs=(str(args.model_path),),
    ) as executor:
        future_rows = {
            executor.submit(cache_one, row, args.cache_dir): index
            for index, row in enumerate(rows)
        }
        completed = 0
        for future in as_completed(future_rows):
            index = future_rows[future]
            cache_path = future.result()
            cache_paths[index] = cache_path
            output_rows[index] = {**rows[index], "audio_features": cache_path}
            completed += 1
            if completed % 500 == 0 or completed == len(rows):
                print(f"cached={completed}/{len(rows)}", flush=True)

    init_worker(str(args.model_path))
    verification = verify_batched_equivalence(
        rows,
        [path for path in cache_paths if path is not None],
        _FEATURE_EXTRACTOR,
    )
    final_rows = [row for row in output_rows if row is not None]
    if len(final_rows) != len(rows):
        raise RuntimeError("feature cacheの作成件数が入力件数と一致しません")
    write_jsonl(args.output_file, final_rows)
    verification_path = args.output_file.with_suffix(".verification.json")
    verification_path.write_text(
        json.dumps(
            {
                "rows": len(final_rows),
                "workers": args.workers,
                "feature_cache_dtype": "float32",
                **verification,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rows": len(final_rows),
                "workers": args.workers,
                "output_file": str(args.output_file),
                "cache_dir": str(args.cache_dir),
                **verification,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
