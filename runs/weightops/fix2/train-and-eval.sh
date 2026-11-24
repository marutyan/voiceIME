#!/usr/bin/env bash
# FIX1-contと同じ条件で、FIX2のデータを使って追加学習する。
set -euo pipefail

cd "$HOME/voiceime-work-wops"
source rsi1/faculty-env.sh
FIX="$WORK/fix2"
TRAIN="$FIX/data/train-fixed.jsonl"
AUGMENTED="$FIX/data/augmentation-fixed.jsonl"
test -s "$FIX/data/fix-audit.json"

# 学習と全行監査に同じデータセットの引数を渡す。
ARGS=(
  --disable-cudnn-sdp
  --train "$TRAIN" --augmentation "$AUGMENTED"
  --train-asr-run-nohint "$D_INPUT/train-runs/first-pass.jsonl"
  --train-asr-run-combined "$D_INPUT/train-runs/segment-merge.jsonl"
  --train-asr-run-qwen "$D_INPUT/train-runs/qwen06-hypothesis.jsonl"
  --train-glossary-run "$D_INPUT/train-runs/formatter-glossary.jsonl"
  --input-passes multiasr --allow-partial-asr --asr-noise-prob 1.0 --user-punct-prob 0.5
  --val "$FR3/inputs/val-select.jsonl"
  --val-asr-run-nohint "$D_INPUT/val-runs/first-pass.jsonl"
  --val-asr-run-combined "$D_INPUT/val-runs/segment-merge.jsonl"
  --val-asr-run-qwen "$D_INPUT/val-runs/qwen06-hypothesis.jsonl"
  --val-glossary-run "$D_INPUT/val-runs/formatter-glossary.jsonl"
  --glossary "$D_INPUT/legacy/training-glossary.jsonl"
  --method full --epochs 1 --learning-rate 1e-5
  --batch-size 16 --grad-accum 2 --max-length 1024 --eval-steps 250
  --dataloader-workers 16 --gradient-checkpointing
  --glossary-drop-prob 0 --max-distractors 8 --seed 0
)

case "${1:?条件名または audit}" in
  audit)
    export CUDA_VISIBLE_DEVICES="" PYTHONPATH="$PYTHONPATH:$WORK/fix1"
    exec nice "$PY" "$FIX/verify_dynamic.py" "$FIX/data/verify-dynamic.json" \
      --model "$WORK/outputs/RSI-0.8B/best" --output-dir "$FIX/audit-unused" "${ARGS[@]}"
    ;;
  FIX2-0.8B-cont)
    TAG="$1"
    MODEL="$WORK/outputs/RSI-0.8B/best"
    ;;
  FIX2-0.8B-contfix)
    TAG="$1"
    MODEL="$WORK/outputs/FIX-0.8B-cont/best"
    ;;
  *) echo "不明な条件: $1" >&2; exit 2 ;;
esac

GPU_ID="${CUDA_VISIBLE_DEVICES:?キューのGPU割当が必要}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "指定外のGPU: $GPU_ID" >&2; exit 2; }
OUTPUT="$FIX/outputs/$TAG"
test ! -e "$OUTPUT"
test ! -e "$WORK/runs/capacity/$TAG"
test -s "$MODEL/config.json"
test -s "$MODEL/model.safetensors"

# キューが割り当てたGPUに計算プロセスが残っていないことを直前に確認する。
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
  # FIX1が追加した正解文の切り替えと一覧の除外を外し、同じ学習処理を使う。
  exec -a "voiceime-wops-$TAG-train" "$PY" "$RSI/train_rsi.py" \
    --model "$MODEL" --output-dir "$OUTPUT" "${ARGS[@]}"
)
assert_idle_gpu
bash "$WORK/fix1/capacity-eval.sh" "$TAG" "$OUTPUT/best"
assert_idle_gpu
