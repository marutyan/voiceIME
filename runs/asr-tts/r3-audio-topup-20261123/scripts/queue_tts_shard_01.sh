#!/usr/bin/env bash
set -euo pipefail
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
case "$GPU_ID" in 1|2|3) ;; *) echo "queue assigned invalid GPU: $GPU_ID" >&2; exit 2 ;; esac
TTS_WORK="$HOME/voiceime-work-tts"
INPUT="$TTS_WORK/inputs/r3-audio-topup44971-20261123/shard-01.jsonl"
OUTPUT="$TTS_WORK/outputs/r3-audio-topup-20261123/shard-01"
RUNNER="$TTS_WORK/datagen/tts/faculty_run_r3audio.sh"
[[ -f "$INPUT" && -f "$RUNNER" ]] || { echo "missing staged input or runner" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
export BATCH_SIZE=32 SEED=0
exec -a voiceime-r3audio-tts-runner /bin/bash "$RUNNER" "$INPUT" "$OUTPUT" "$GPU_ID" 1 train
