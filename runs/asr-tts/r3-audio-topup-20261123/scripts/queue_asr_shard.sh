#!/usr/bin/env bash
# facultyのキューから割り当てられたGPUで、ASRの1 shardを処理する。
set -euo pipefail
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
case "$GPU_ID" in 1|2|3) ;; *) echo "queue assigned invalid GPU: $GPU_ID" >&2; exit 2 ;; esac
SHARD_INDEX="${1:?shard index required}"
ASR_WORK="$HOME/voiceime-work-asr/r3-multiasr-train-20261123"
TOPUP_SCRIPTS="$ASR_WORK/scripts/topup44971"
MAIN_SOURCE="$ASR_WORK/main-code-topup-20261123/src"
PYTHON="$HOME/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv/bin/voiceime-r3audio-asr-pipeline"
export PYTHONPATH="$MAIN_SOURCE:$TOPUP_SCRIPTS${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
[[ -f "$TOPUP_SCRIPTS/topup_pipeline.py" && -x "$PYTHON" ]] || { echo "missing ASR pipeline or Python alias" >&2; exit 2; }
printf 'ASR shard=%s GPU=%s start=%s\n' "$SHARD_INDEX" "$GPU_ID" "$(date --iso-8601=seconds)"
exec "$PYTHON" "$TOPUP_SCRIPTS/topup_pipeline.py" run-shard --shard "$SHARD_INDEX"
