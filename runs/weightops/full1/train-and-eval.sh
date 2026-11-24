#!/usr/bin/env bash
# 条件Dの実ASR入力で学習し、bestの容量評価と集計を同じジョブで続ける。
set -euo pipefail

cd "$HOME/voiceime-work-wops"
source rsi1/faculty-env.sh
FULL="$WORK/full1"
FIX="$WORK/fix1"
export PYTHONPATH="$FIX:$PYTHONPATH:$WORK/fix2"
TRAIN_RUNS="$FULL/data/train-runs"
BASE_MODEL="$FR3/hf-cache/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17"
TRAIN_SCRIPT="$FIX/train_fix.py"
TAG="${1:?条件名またはauditが必要}"
MODEL="$WORK/outputs/fixsoup-a050"
EPOCHS=1
LR=1e-5
DROP_ARGS=()
case "$TAG" in
  FULL-cont) ;;
  FULL-scratch)
    MODEL="$BASE_MODEL"
    EPOCHS=2
    LR=2e-5
    ;;
  FULL-cont-drop|audit)
    TRAIN_SCRIPT="$FULL/train_full_drop.py"
    DROP_ARGS=(--seen-drop-prob 0.15 --seen-drop-terms "$FULL/data/seen-drop-terms.txt")
    ;;
  *) echo "不明な条件: $TAG" >&2; exit 2 ;;
esac

test -s "$FULL/data/data-audit.json"
test -s "$MODEL/config.json"
ARGS=(
  --model "$MODEL" --disable-cudnn-sdp
  --train "$FULL/data/train-fixed.jsonl" --augmentation "$FIX/data/augmentation-fixed.jsonl"
  --train-asr-run-nohint "$TRAIN_RUNS/first-pass.jsonl"
  --train-asr-run-combined "$TRAIN_RUNS/segment-merge.jsonl"
  --train-asr-run-qwen "$TRAIN_RUNS/qwen06-hypothesis.jsonl"
  --train-glossary-run "$TRAIN_RUNS/formatter-glossary.jsonl"
  --input-passes multiasr --allow-partial-asr --asr-noise-prob 1.0 --user-punct-prob 0.5
  --val "$FR3/inputs/val-select.jsonl"
  --val-asr-run-nohint "$D_INPUT/val-runs/first-pass.jsonl"
  --val-asr-run-combined "$D_INPUT/val-runs/segment-merge.jsonl"
  --val-asr-run-qwen "$D_INPUT/val-runs/qwen06-hypothesis.jsonl"
  --val-glossary-run "$D_INPUT/val-runs/formatter-glossary.jsonl"
  --glossary "$D_INPUT/legacy/training-glossary.jsonl"
  --method full --epochs "$EPOCHS" --learning-rate "$LR"
  --batch-size 16 --grad-accum 2 --max-length 1024 --eval-steps 250
  --dataloader-workers 16 --gradient-checkpointing
  --glossary-drop-prob 0 --max-distractors 8 --seed 0
  "${DROP_ARGS[@]}"
)

if [[ "$TAG" == audit ]]; then
  export CUDA_VISIBLE_DEVICES=""
  exec nice "$PY" "$FULL/verify_dynamic.py" "$FULL/data/verify-dynamic.json" \
    --output-dir "$FULL/audit-unused" "${ARGS[@]}"
fi

GPU_ID="${CUDA_VISIBLE_DEVICES:?キューのGPU割当が必要}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "指定外のGPU: $GPU_ID" >&2; exit 2; }
OUTPUT="$FULL/outputs/$TAG"
test ! -e "$OUTPUT"
test ! -e "$WORK/runs/capacity/$TAG"

# 割当GPUだけを調べ、ほかの計算プロセスがある状態では起動しない。
assert_idle_gpu() {
  local processes
  nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
  processes=$(nvidia-smi --id="$GPU_ID" --query-compute-apps=pid --format=csv,noheader)
  if [[ -n "$processes" ]]; then
    echo "GPU $GPU_ID に計算プロセスが存在します: $processes" >&2
    exit 2
  fi
}

assert_idle_gpu
(
  exec -a "voiceime-wops-$TAG-train" "$PY" "$TRAIN_SCRIPT" --output-dir "$OUTPUT" "${ARGS[@]}"
)
assert_idle_gpu
bash "$FIX/capacity-eval.sh" "$TAG" "$OUTPUT/best"
assert_idle_gpu
CUDA_VISIBLE_DEVICES="" "$PY" "$FULL/score_full.py" --progress "$TAG"
