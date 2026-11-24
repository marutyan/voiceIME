#!/usr/bin/env bash
set -euo pipefail
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
case "$GPU_ID" in 1|2|3) ;; *) echo "queue assigned invalid GPU: $GPU_ID" >&2; exit 2 ;; esac
RESCUE="$HOME/voiceime-work-tts/datagen/tts/rescue_tts_failures.sh"
[[ -f "$RESCUE" ]] || { echo "missing TTS rescue script" >&2; exit 2; }
exec -a voiceime-r3audio-tts-rescue-runner /bin/bash "$RESCUE" 00
