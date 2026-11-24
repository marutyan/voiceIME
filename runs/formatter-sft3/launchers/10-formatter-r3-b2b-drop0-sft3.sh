#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
INPUT="$WORK/inputs/sft3-20261122"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
MODEL="$HOME/voiceime-work-f2b/hf-cache/hub/models--Qwen--Qwen3.5-2B/snapshots/15852e8c16360a2fea060d615a32b45270f8a8fc"
OUTPUT="$WORK/outputs/formatter-sft3-b-2b-drop0-20261122"

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" != *,* ]] || { echo "queue assigned multiple GPUs: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
for path in "$REPO" "$INPUT/train-sft3.jsonl" "$INPUT/haas-train-clean.jsonl" \
  "$INPUT/haas2p-train-clean.jsonl" "$INPUT/glossary-v2-train-clean.jsonl" \
  "$WORK/inputs/val-select.jsonl" "$INPUT/haas-val.jsonl" "$WORK/inputs/haas2p-val.jsonl" \
  "$MODEL/config.json"; do
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

exec -a voiceime-formatter-r3-b2b-drop0-train "$PY" train/formatter/train.py \
  --model "$MODEL" \
  --use-model-loader \
  --train "$INPUT/train-sft3.jsonl" \
  --train-asr-run "$INPUT/haas2p-train-clean.jsonl" \
  --train-asr-run-nohint "$INPUT/haas-train-clean.jsonl" \
  --input-passes both \
  --nohint-prob 0 \
  --allow-partial-asr \
  --asr-noise-prob 1.0 \
  --user-punct-prob 0.5 \
  --val "$WORK/inputs/val-select.jsonl" \
  --val-asr-run "$WORK/inputs/haas2p-val.jsonl" \
  --val-asr-run-nohint "$INPUT/haas-val.jsonl" \
  --glossary "$INPUT/glossary-v2-train-clean.jsonl" \
  --method full \
  --epochs 2 \
  --learning-rate 2e-5 \
  --batch-size 4 \
  --grad-accum 8 \
  --max-length 1024 \
  --eval-steps 250 \
  --dataloader-workers 4 \
  --gradient-checkpointing \
  --glossary-drop-prob 0 \
  --max-distractors 8 \
  --seed 0 \
  --output-dir "$OUTPUT"
