#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
ASR_ROOT="$HOME/voiceime-work-asr/r3-multiasr-train-20261123"
QWEN_ROOT="$HOME/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e"
QWEN_SOURCE="$HOME/voiceime-work-qwenasr/Qwen3-ASR"
PY="$QWEN_ROOT/.venv/bin/python"
PIPELINE_DIR="$ASR_ROOT/scripts"
OUTPUT="$WORK/runs/formatter-sft3/d-multiasr-legacy-20261123"
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"

[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "queue assigned an unavailable GPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
for path in \
  "$PY" \
  "$REPO/runs/formatter-sft3/generate_legacy_qwen.py" \
  "$PIPELINE_DIR/train_pipeline.py" \
  "$QWEN_ROOT/data/tts/train/manifest.jsonl" \
  "$WORK/inputs/sft3-20261122/haas-train-clean.jsonl"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done

export PYTHONPATH="$QWEN_ROOT/.venv/lib/python3.12/site-packages:$WORK/python-deps:$QWEN_SOURCE:$ASR_ROOT/main-code/src:$ASR_ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
exec -a voiceime-formatter-r3-d-qwen-legacy "$PY" \
  "$REPO/runs/formatter-sft3/generate_legacy_qwen.py" \
  --pipeline-dir "$PIPELINE_DIR" \
  --manifest "$QWEN_ROOT/data/tts/train/manifest.jsonl" \
  --legacy-asr "$WORK/inputs/sft3-20261122/haas-train-clean.jsonl" \
  --output-dir "$OUTPUT"
