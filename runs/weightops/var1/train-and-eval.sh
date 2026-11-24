#!/usr/bin/env bash
# VARを学習し、従来の容量評価とval-ゆれを同じジョブで実行する。
set -euo pipefail

cd "$HOME/voiceime-work-wops"
source rsi1/faculty-env.sh
VAR="$WORK/var1"
FIX="$WORK/fix1"
FULL="$WORK/full1"
export PYTHONPATH="$FIX:$PYTHONPATH:$WORK/fix2:$FULL"
TRAIN_RUNS="$FULL/data/train-runs"
BASE_MODEL="$FR3/hf-cache/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17"
INITIAL="$FULL/outputs/FULL-scratch/best"
TAG="${1:?条件名またはauditが必要}"
MODEL="$INITIAL"
EPOCHS=1
LR=1e-5
case "$TAG" in
  VAR-cont|audit) ;;
  VAR-scratch)
    MODEL="$BASE_MODEL"
    EPOCHS=2
    LR=2e-5
    ;;
  *) echo "不明な条件: $TAG" >&2; exit 2 ;;
esac

test -s "$VAR/data/generation-audit.json"
test -s "$MODEL/config.json"
ARGS=(
  --model "$MODEL" --disable-cudnn-sdp
  --train "$FULL/data/train-fixed.jsonl" --augmentation "$VAR/data/augmentation-var.jsonl"
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
)

if [[ "$TAG" == audit ]]; then
  export CUDA_VISIBLE_DEVICES=""
  exec nice "$PY" "$VAR/verify_dynamic.py" "$VAR/data/verify-dynamic.json" \
    --output-dir "$VAR/audit-unused" "${ARGS[@]}"
fi

GPU_ID="${CUDA_VISIBLE_DEVICES:?キューのGPU割当が必要}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "指定外のGPU: $GPU_ID" >&2; exit 2; }
OUTPUT="$VAR/outputs/$TAG"
test ! -e "$OUTPUT"
test ! -e "$WORK/runs/capacity/$TAG"

# 割当GPUの計算プロセスだけを確認する。
assert_idle_gpu() {
  local processes
  nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
  processes=$(nvidia-smi --id="$GPU_ID" --query-compute-apps=pid --format=csv,noheader)
  [[ -z "$processes" ]] || { echo "GPU $GPU_ID に計算プロセスがあります: $processes" >&2; exit 2; }
}

# 容量評価と同じ推論コードに、固定したval-ゆれの3入力を渡す。
eval_variant() (
  local tag="$1" model="$2"
  local inputs="$VAR/val-variants" output="$WORK/runs/var1/$1"
  local novel_glossary="$FR3/inputs/test-novel-20261122"
  test -s "$inputs/audit.json"
  test ! -e "$output"
  cd "$FR3/repo"
  export PYTHONPATH="$PWD/src:$PWD/train/formatter:$PYTHONPATH"
  assert_idle_gpu
  exec -a "voiceime-wops-$tag-var-eval" "$PY" train/formatter/eval_transformers.py \
    --model "$model" --batch-size 32 --max-glossary 32 --out-dir "$output" \
    --glossary "$novel_glossary/glossary-v1.jsonl" "$novel_glossary/glossary-v2.jsonl" \
    --glossary-run val-variants "$inputs/formatter-glossary.jsonl" \
    --job-multiasr val-variants "$inputs/manifest.jsonl" "$inputs/first-pass.jsonl" \
      "$inputs/segment-merge.jsonl" "$inputs/qwen06-hypothesis.jsonl" -
)

assert_idle_gpu
(
  exec -a "voiceime-wops-$TAG-train" "$PY" "$FIX/train_fix.py" --output-dir "$OUTPUT" "${ARGS[@]}"
)
assert_idle_gpu
bash "$FIX/capacity-eval.sh" "$TAG" "$OUTPUT/best"
assert_idle_gpu
eval_variant "$TAG" "$OUTPUT/best"
assert_idle_gpu
CUDA_VISIBLE_DEVICES="" "$PY" "$VAR/score_var.py" "$TAG"
if [[ "$TAG" == VAR-cont ]]; then
  eval_variant FULL-scratch "$INITIAL"
  assert_idle_gpu
  CUDA_VISIBLE_DEVICES="" "$PY" "$VAR/score_var.py" FULL-scratch
fi
