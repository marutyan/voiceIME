#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/maru/voiceime-work-asr/r3-multiasr-train-20261123
PY=/home/maru/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv/bin/voiceime-r3multi-train-pipeline
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" != *,* && "$GPU_ID" != "0" ]] || { echo "invalid queue GPU: $GPU_ID" >&2; exit 2; }
export PYTHONPATH="$ROOT/main-code/src${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
exec "$PY" "$ROOT/scripts/train_pipeline.py" run-shard --shard 1
