#!/usr/bin/env bash
# 監査済みの元データ＋拡張データで学習し、val loss最良の重みを既存設定で評価する。
set -euo pipefail

cd "$HOME/voiceime-work-wops"
source rsi1/faculty-env.sh
case "${0##*/}" in
  72-wops-rsi-08b.sh)
    TAG="RSI-0.8B"
    MODEL="$WORK/outputs/soup-a050"
    DROP=0
    LOADER_ARGS=()
    ;;
  72-wops-rsi-2b.sh)
    TAG="RSI-2B"
    MODEL="$FR3/outputs/formatter-sft3-d-2b-drop0075-restart1/final"
    DROP=0.075
    LOADER_ARGS=(--use-model-loader)
    ;;
  *) echo "不明なジョブ名: $0" >&2; exit 2 ;;
esac

GPU_ID="${CUDA_VISIBLE_DEVICES:?キューのGPU割当が必要}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "指定外のGPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader

OUTPUT="$WORK/outputs/$TAG"
AUGMENTED="$RSI/data/augmentation.jsonl"
test ! -e "$OUTPUT"
test -s "$RSI/data/augmentation-audit.json"

# キューの割当を引き継いで、他担当のプロセスと区別できる名前で実行する。
run_named() (
  local phase="$1"
  shift
  exec -a "voiceime-wops-$TAG-$phase" "$@"
)

run_named train "$PY" "$RSI/train_rsi.py" \
  --model "$MODEL" "${LOADER_ARGS[@]}" --disable-cudnn-sdp \
  --train "$FR3/inputs/sft3-20261122/train-sft3.jsonl" --augmentation "$AUGMENTED" \
  --train-asr-run-nohint "$D_INPUT/train-runs/first-pass.jsonl" \
  --train-asr-run-combined "$D_INPUT/train-runs/segment-merge.jsonl" \
  --train-asr-run-qwen "$D_INPUT/train-runs/qwen06-hypothesis.jsonl" \
  --train-glossary-run "$D_INPUT/train-runs/formatter-glossary.jsonl" \
  --input-passes multiasr --allow-partial-asr --asr-noise-prob 1.0 --user-punct-prob 0.5 \
  --val "$FR3/inputs/val-select.jsonl" \
  --val-asr-run-nohint "$D_INPUT/val-runs/first-pass.jsonl" \
  --val-asr-run-combined "$D_INPUT/val-runs/segment-merge.jsonl" \
  --val-asr-run-qwen "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" \
  --val-glossary-run "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  --glossary "$D_INPUT/legacy/training-glossary.jsonl" \
  --method full --epochs 1 --learning-rate 1e-5 \
  --batch-size 16 --grad-accum 2 --max-length 1024 --eval-steps 250 \
  --dataloader-workers 16 --gradient-checkpointing \
  --glossary-drop-prob "$DROP" --max-distractors 8 --seed 0 --output-dir "$OUTPUT"

NOVEL="$FR3/inputs/test-novel-20261122"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
VAL="$D_INPUT/val-runs"
OUT="$WORK/runs/rsi1/$TAG"

run_named eval "$PY" "$REPO/train/formatter/eval_transformers.py" \
  --model "$OUTPUT/best" "${LOADER_ARGS[@]}" --batch-size 32 --out-dir "$OUT/multiasr" \
  --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
  --glossary-run val-segment-merge "$VAL/formatter-glossary.jsonl" \
  --glossary-run test-novel-segment-merge "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --job-multiasr val-segment-merge "$FR3/inputs/manifest-val-no-audio.jsonl" \
    "$VAL/first-pass.jsonl" "$VAL/segment-merge.jsonl" "$VAL/qwen06-hypothesis.jsonl" - \
  --job-multiasr test-novel-segment-merge "$NOVEL/test-novel.jsonl" \
    "$NOVEL/a-plain.jsonl" "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
    "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" "$NOVEL/exclude-v2-83.txt"
