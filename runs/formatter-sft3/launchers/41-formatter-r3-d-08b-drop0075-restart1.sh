#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
INPUT="$WORK/inputs/sft3-20261122"
VAL="$WORK/inputs/val-select.jsonl"
D_INPUT="$WORK/inputs/d-multiasr-20261123"
MODEL="$WORK/hf-cache/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17"
OUTPUT="/var/tmp/voiceime-work-fr3-d-20261123/outputs/formatter-sft3-d-0.8b-drop0075-restart1"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"

[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "queue assigned an unavailable GPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
for path in "$REPO" "$INPUT/train-sft3.jsonl" "$VAL" \
  "$D_INPUT/train-runs/first-pass.jsonl" "$D_INPUT/train-runs/segment-merge.jsonl" \
  "$D_INPUT/train-runs/qwen06-hypothesis.jsonl" "$D_INPUT/train-runs/formatter-glossary.jsonl" \
  "$D_INPUT/val-runs/first-pass.jsonl" "$D_INPUT/val-runs/segment-merge.jsonl" \
  "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  "$D_INPUT/legacy/training-glossary.jsonl" "$MODEL/config.json"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
test ! -e "$OUTPUT" || { echo "training output already exists: $OUTPUT" >&2; exit 2; }

cd "$REPO"
export HF_HOME="$WORK/hf-cache"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$REPO/src:$WORK/python-deps:$KERNEL_SITE:$TORCH_SITE"
export PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false

exec -a voiceime-formatter-r3-d-08b-drop0075-train "$PY" train/formatter/train.py \
  --model "$MODEL" --disable-cudnn-sdp \
  --train "$INPUT/train-sft3.jsonl" \
  --train-asr-run-nohint "$D_INPUT/train-runs/first-pass.jsonl" \
  --train-asr-run-combined "$D_INPUT/train-runs/segment-merge.jsonl" \
  --train-asr-run-qwen "$D_INPUT/train-runs/qwen06-hypothesis.jsonl" \
  --train-glossary-run "$D_INPUT/train-runs/formatter-glossary.jsonl" \
  --input-passes multiasr --allow-partial-asr --asr-noise-prob 1.0 --user-punct-prob 0.5 \
  --val "$VAL" \
  --val-asr-run-nohint "$D_INPUT/val-runs/first-pass.jsonl" \
  --val-asr-run-combined "$D_INPUT/val-runs/segment-merge.jsonl" \
  --val-asr-run-qwen "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" \
  --val-glossary-run "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  --glossary "$D_INPUT/legacy/training-glossary.jsonl" \
  --method full --epochs 2 --learning-rate 2e-5 \
  --batch-size 32 --grad-accum 1 --max-length 1024 --eval-steps 250 \
  --dataloader-workers 16 --gradient-checkpointing \
  --glossary-drop-prob 0.075 --max-distractors 8 --seed 0 --output-dir "$OUTPUT"
