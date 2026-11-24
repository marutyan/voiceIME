#!/usr/bin/env bash
set -euo pipefail
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
case "$GPU_ID" in 1|2|3) ;; *) echo "queue assigned invalid GPU: $GPU_ID" >&2; exit 2 ;; esac
RESUME="$HOME/voiceime-work-tts/datagen/tts/resume_qwen_batch16.sh"
[[ -f "$RESUME" ]] || { echo "missing Qwen resume script" >&2; exit 2; }
exec -a voiceime-r3audio-tts-resume-runner /bin/bash "$RESUME" 01 8
