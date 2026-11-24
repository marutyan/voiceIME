"""学習音声、教師文、用語ヒントを検査し、使える行だけを保存する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import soundfile as sf
import qwen_asr  # AutoProcessorへQwen3ASRProcessorを登録する。
from transformers import AutoProcessor


# 0.25秒未満は、今回の8文字以上の発話を含めるには短すぎる音声として扱う。
MIN_AUDIO_SECONDS = 0.25
# 公式推論APIの既定max_new_tokensに合わせ、超える教師文は学習対象外にする。
MAX_TARGET_TOKENS = 512
# Qwen3-ASR-0.6Bの言語モデル設定に合わせたsystem context上限。
MAX_CONTEXT_TOKENS = 65_536
TRAIN_TEXT_PREFIX = "language Japanese<asr_text>"
AUDIO_BLOCK_FRAMES = 65_536


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """1行1件のJSON objectを読み、行番号付きで形式エラーを示す。"""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """一時ファイルへJSONLを書き、完成後に置き換える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def percentile(values: list[int | float], percentage: float) -> float | None:
    """検査対象の分布を、丸めずに再現できるpercentileで返す。"""
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentage))


def load_target(row: dict[str, Any]) -> tuple[str, str | None]:
    """trainer形式のtextから、言語指定prefixと教師本文を分ける。"""
    text = row.get("text")
    if not isinstance(text, str):
        return "", "text field is not a string"
    if not text.startswith(TRAIN_TEXT_PREFIX):
        return "", "unexpected text prefix"
    target = text[len(TRAIN_TEXT_PREFIX) :]
    if not target.strip():
        return target, "empty target"
    return target, None


def token_ids(tokenizer: Any, text: str) -> list[int]:
    """追加特殊tokenを勝手に挿入せず、対象文字列のtoken数を数える。"""
    return tokenizer(text, add_special_tokens=False)["input_ids"]


def prompt_prefix(processor: Any, prompt: str) -> str | None:
    """公式trainerと同じchat templateでsystem message長を測る。"""
    template_owner = processor if hasattr(processor, "apply_chat_template") else None
    if template_owner is None:
        return None
    messages = [
        {"role": "system", "content": prompt or ""},
        {"role": "user", "content": [{"type": "audio", "audio": None}]},
    ]
    rendered = template_owner.apply_chat_template(
        [messages], add_generation_prompt=True, tokenize=False
    )
    return rendered[0] if isinstance(rendered, list) else rendered


def check_audio(path: Path) -> tuple[float, int, int]:
    """16 kHz WAVを末尾まで読み、長さとchannel数を返す。"""
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
            if not np.isfinite(block).all():
                raise ValueError("audio contains NaN or Inf")
            frames_read += block.shape[0]
        if frames_read != audio.frames:
            raise ValueError(f"truncated audio: read {frames_read}/{audio.frames} frames")
        return audio.frames / audio.samplerate, audio.channels, frames_read


def stats(values: list[int | float]) -> dict[str, float | int | None]:
    """分布確認に必要な要約値だけを返す。"""
    if not values:
        return {"min": None, "median": None, "p95": None, "max": None}
    return {
        "min": min(values),
        "median": median(values),
        "p95": percentile(values, 95),
        "max": max(values),
    }


def sha256(path: Path) -> str:
    """入力と出力manifestを識別するSHA-256を計算する。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    """入力manifestを監査し、除外理由と分布をJSONで報告する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-file", required=True, type=Path)
    parser.add_argument("--audio-root", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--invalid-report", required=True, type=Path)
    parser.add_argument("--min-audio-seconds", type=float, default=MIN_AUDIO_SECONDS)
    parser.add_argument("--max-target-tokens", type=int, default=MAX_TARGET_TOKENS)
    parser.add_argument("--max-context-tokens", type=int, default=MAX_CONTEXT_TOKENS)
    args = parser.parse_args()

    if args.output.exists() or args.invalid_report.exists():
        raise FileExistsError("audit output already exists; choose a new output path")
    audio_root = args.audio_root.resolve()
    processor = AutoProcessor.from_pretrained(
        str(args.model_path),
        local_files_only=True,
        fix_mistral_regex=True,
    )
    tokenizer = getattr(processor, "tokenizer", processor)
    special_tokens = [
        token for token in getattr(tokenizer, "all_special_tokens", []) if token
    ]
    rows = read_jsonl(args.train_file)
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    audio_durations: list[float] = []
    audio_channels: Counter[int] = Counter()
    target_chars: list[int] = []
    target_tokens: list[int] = []
    prompt_chars: list[int] = []
    prompt_tokens: list[int] = []
    templated_prefix_tokens: list[int] = []
    reasons: Counter[str] = Counter()

    for row in rows:
        row_reasons: list[str] = []
        row_id = str(row.get("id", ""))
        prompt = row.get("prompt", "")
        if not isinstance(prompt, str):
            prompt = ""
            row_reasons.append("prompt is not a string")

        target, target_error = load_target(row)
        if target_error:
            row_reasons.append(target_error)
        target_chars.append(len(target))
        target_token_count = len(token_ids(tokenizer, target)) if target else 0
        target_tokens.append(target_token_count)
        if target_token_count > args.max_target_tokens:
            row_reasons.append("target exceeds max_new_tokens limit")
        if any(token in target for token in special_tokens):
            row_reasons.append("target contains tokenizer special token")

        prompt_chars.append(len(prompt))
        prompt_token_count = len(token_ids(tokenizer, prompt)) if prompt else 0
        prompt_tokens.append(prompt_token_count)
        rendered_prefix = prompt_prefix(processor, prompt)
        if rendered_prefix is not None:
            prefix_token_count = len(token_ids(tokenizer, rendered_prefix))
            templated_prefix_tokens.append(prefix_token_count)
            if prefix_token_count > args.max_context_tokens:
                row_reasons.append("system message exceeds model context limit")
        if any(token in prompt for token in special_tokens):
            row_reasons.append("system message contains tokenizer special token")

        audio_value = row.get("audio")
        if not isinstance(audio_value, str):
            row_reasons.append("audio field is not a string")
        else:
            audio_path = Path(audio_value).resolve()
            try:
                audio_path.relative_to(audio_root)
            except ValueError as error:
                raise ValueError(f"audio path is outside audio-root: {row_id}") from error
            if not audio_path.is_file():
                row_reasons.append("audio file missing")
            else:
                try:
                    duration, channels, _ = check_audio(audio_path)
                    audio_durations.append(duration)
                    audio_channels[channels] += 1
                    if duration < args.min_audio_seconds:
                        row_reasons.append("audio shorter than minimum duration")
                except (OSError, RuntimeError, ValueError) as error:
                    row_reasons.append(f"invalid audio: {type(error).__name__}: {error}")

        if row_reasons:
            reasons.update(row_reasons)
            invalid_rows.append({"id": row_id, "reasons": row_reasons})
        else:
            valid_rows.append(row)

    write_jsonl(args.output, valid_rows)
    write_jsonl(args.invalid_report, invalid_rows)
    summary = {
        "input": str(args.train_file),
        "input_sha256": sha256(args.train_file),
        "input_rows": len(rows),
        "valid_rows": len(valid_rows),
        "invalid_rows": len(invalid_rows),
        "invalid_reason_counts": dict(sorted(reasons.items())),
        "audio_duration_seconds": stats(audio_durations),
        "audio_channel_counts": dict(sorted(audio_channels.items())),
        "target_characters": stats(target_chars),
        "target_tokens": stats(target_tokens),
        "system_message_characters": stats(prompt_chars),
        "system_message_tokens": stats(prompt_tokens),
        "templated_prefix_tokens": stats(templated_prefix_tokens),
        "minimum_audio_seconds": args.min_audio_seconds,
        "maximum_target_tokens": args.max_target_tokens,
        "maximum_context_tokens": args.max_context_tokens,
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "invalid_report": str(args.invalid_report),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
