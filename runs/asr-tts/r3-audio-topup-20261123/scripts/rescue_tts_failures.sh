#!/usr/bin/env bash
set -euo pipefail

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
case "$GPU_ID" in 1|2|3) ;; *) echo "queue assigned invalid GPU: $GPU_ID" >&2; exit 2 ;; esac
SHARD_INDEX="${1:?shard index required}"
case "$SHARD_INDEX" in 00|01|02) ;; *) echo "invalid shard: $SHARD_INDEX" >&2; exit 2 ;; esac
RETRY_OFFSET="${2:-0}"
RETRIES="${3:-12}"
[[ "$RETRY_OFFSET" =~ ^[0-9]+$ && "$RETRIES" =~ ^[0-9]+$ ]] || exit 2

TTS_WORK="$HOME/voiceime-work-tts"
HERE="$TTS_WORK/datagen/tts"
IRODORI_DIR="$TTS_WORK/Irodori-TTS"
INPUT="$TTS_WORK/inputs/r3-audio-topup44971-20261123/shard-$SHARD_INDEX.jsonl"
RESCUE_DIR="$TTS_WORK/inputs/r3-audio-topup44971-20261123/rescue"
RESCUE_INPUT="$RESCUE_DIR/shard-$SHARD_INDEX.jsonl"
OUTPUT="$TTS_WORK/outputs/r3-audio-topup-20261123/shard-$SHARD_INDEX"
WORKER_OUT="$OUTPUT/workers/worker-000/out"
IRODORI_PYTHON="$IRODORI_DIR/.venv/bin/voiceime-r3audio-tts-ja"
QWEN_PYTHON="$TTS_WORK/venv-qwen/bin/voiceime-r3audio-tts-multi"

export HF_HOME="$TTS_WORK/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export TMPDIR="$TTS_WORK/tmp"
export PATH="$TTS_WORK/tools/sox/bin:$PATH"
export PYTHONUNBUFFERED=1

[[ -f "$INPUT" && -f "$HERE/synthesize.py" && -d "$WORKER_OUT/parts" ]] || {
  echo "missing input, TTS source, or worker output" >&2
  exit 2
}

mkdir -p "$RESCUE_DIR"
read -r ROW_COUNT JA_COUNT MULTI_COUNT < <(PYTHONPATH="$IRODORI_DIR:$HERE" "$IRODORI_PYTHON" - "$INPUT" "$WORKER_OUT" "$HERE" "$RESCUE_INPUT" <<'PY'
import json
import sys
from pathlib import Path

input_path, output_dir, tts_dir, rescue_path = map(Path, sys.argv[1:])
sys.path.insert(0, str(tts_dir))
from synthesize import load_voices, plan_row, read_rows  # noqa: E402

rows = read_rows(input_path, "train")
voices = load_voices(tts_dir / "voices.json")
parts = output_dir / "parts"
failed_ids: set[str] = set()
done_ids: set[str] = set()
for engine in ("ja", "multi"):
    failed_path = parts / f"{engine}.failed.jsonl"
    done_path = parts / f"{engine}.jsonl"
    if failed_path.exists():
        failed_ids.update(
            str(json.loads(line)["id"])
            for line in failed_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if done_path.exists():
        done_ids.update(
            str(json.loads(line)["manifest"]["id"])
            for line in done_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

by_id = {row["id"]: row for row in rows}
unknown = failed_ids - set(by_id)
if unknown:
    raise SystemExit(f"failed IDs are absent from input: {sorted(unknown)[:3]}")
rescue = [by_id[record_id] for record_id in sorted(failed_ids - done_ids)]
rescue = [
    row for row in rescue
    if plan_row(row, voices, 0)["engine"] in ("ja", "multi")
]
rescue_path.parent.mkdir(parents=True, exist_ok=True)
with rescue_path.open("w", encoding="utf-8") as destination:
    for row in rescue:
        destination.write(json.dumps(row, ensure_ascii=False) + "\n")
ja_count = sum(plan_row(row, voices, 0)["engine"] == "ja" for row in rescue)
multi_count = len(rescue) - ja_count
print(len(rescue), ja_count, multi_count)
PY
)

echo "shard=$SHARD_INDEX gpu=$GPU_ID retry_rows=$ROW_COUNT ja=$JA_COUNT multi=$MULTI_COUNT"
if [[ "$ROW_COUNT" -eq 0 ]]; then
  echo "no failed TTS rows to rescue"
  exit 0
fi

ENTRY=("$HERE/synthesize.py")
if [[ "$RETRY_OFFSET" -gt 0 ]]; then
  [[ "$ROW_COUNT" -eq 1 ]] || { echo "only one row can continue its attempt numbers" >&2; exit 2; }
  ENTRY=("$HERE/retry_tts_attempts.py" "$RETRY_OFFSET")
fi
if [[ "$JA_COUNT" -gt 0 ]]; then
  PYTHONPATH="$IRODORI_DIR:$HERE" "$IRODORI_PYTHON" "${ENTRY[@]}" run \
    --engine ja --input "$RESCUE_INPUT" --out "$WORKER_OUT" --voices "$HERE/voices.json" \
    --voice-dir "$TTS_WORK/voices" --seed 0 --batch-size 32 --default-split train --retries "$RETRIES"
fi
if [[ "$MULTI_COUNT" -gt 0 ]]; then
  PYTHONPATH="$HERE" "$QWEN_PYTHON" "${ENTRY[@]}" run \
    --engine multi --input "$RESCUE_INPUT" --out "$WORKER_OUT" --voices "$HERE/voices.json" \
    --voice-dir "$TTS_WORK/voices" --seed 0 --batch-size 32 --default-split train --retries "$RETRIES"
fi

mkdir -p "$OUTPUT/parts" "$OUTPUT/audio"
for part in "$WORKER_OUT"/parts/*.jsonl; do
  [[ -f "$part" ]] || continue
  cp "$part" "$OUTPUT/parts/worker-000-$(basename "$part")"
done
cp -an "$WORKER_OUT/audio/." "$OUTPUT/audio/"
PYTHONPATH="$IRODORI_DIR:$HERE" "$IRODORI_PYTHON" "$HERE/synthesize.py" merge \
  --input "$INPUT" --out "$OUTPUT" --default-split train
