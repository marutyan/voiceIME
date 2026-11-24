#!/usr/bin/env bash
set -euo pipefail

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
case "$GPU_ID" in 1|2|3) ;; *) echo "queue assigned invalid GPU: $GPU_ID" >&2; exit 2 ;; esac

TTS_WORK="$HOME/voiceime-work-tts"
HERE="$TTS_WORK/datagen/tts"
IRODORI_DIR="$TTS_WORK/Irodori-TTS"
SHARD_INDEX="${1:-02}"
case "$SHARD_INDEX" in 00|01|02) ;; *) echo "invalid shard: $SHARD_INDEX" >&2; exit 2 ;; esac
BATCH_SIZE="${2:-16}"
case "$BATCH_SIZE" in 8|16) ;; *) echo "invalid batch size: $BATCH_SIZE" >&2; exit 2 ;; esac
INPUT="$TTS_WORK/inputs/r3-audio-topup44971-20261123/shard-$SHARD_INDEX.jsonl"
OUTPUT="$TTS_WORK/outputs/r3-audio-topup-20261123/shard-$SHARD_INDEX"
WORKER_OUT="$OUTPUT/workers/worker-000/out"
QWEN_PYTHON="$TTS_WORK/venv-qwen/bin/voiceime-r3audio-tts-multi"
IRODORI_PYTHON="$IRODORI_DIR/.venv/bin/voiceime-r3audio-tts-ja"

export HF_HOME="$TTS_WORK/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export TMPDIR="$TTS_WORK/tmp"
export PATH="$TTS_WORK/tools/sox/bin:$PATH"
export PYTHONUNBUFFERED=1

[[ -f "$INPUT" && -f "$HERE/synthesize.py" && -d "$WORKER_OUT/parts" ]] || {
  echo "missing input, TTS source, or worker output" >&2
  exit 2
}

PYTHONPATH="$HERE" "$QWEN_PYTHON" "$HERE/synthesize.py" run \
  --engine multi --input "$INPUT" --out "$WORKER_OUT" --voices "$HERE/voices.json" \
  --voice-dir "$TTS_WORK/voices" --seed 0 --batch-size "$BATCH_SIZE" --default-split train

mkdir -p "$OUTPUT/parts" "$OUTPUT/audio"
for part in "$WORKER_OUT"/parts/*.jsonl; do
  [[ -f "$part" ]] || continue
  cp "$part" "$OUTPUT/parts/worker-000-$(basename "$part")"
done
cp -a "$WORKER_OUT/audio/." "$OUTPUT/audio/"
PYTHONPATH="$IRODORI_DIR:$HERE" "$IRODORI_PYTHON" "$HERE/synthesize.py" merge \
  --input "$INPUT" --out "$OUTPUT" --default-split train
