#!/usr/bin/env bash
# omittedの語を直した元データ＋拡張データで学習し、val loss最良の重みを標準の一覧と上限20/32/48の一覧で評価する。
set -euo pipefail

cd "$HOME/voiceime-work-wops"
source rsi1/faculty-env.sh
FIX="$WORK/fix1"
# 直したデータの読み込みと、一覧・正解文の食い違いを防ぐ処理（train_support.py）をrsi1より先に読む。
export PYTHONPATH="$FIX:$PYTHONPATH"
case "${0##*/}" in
  70-wops-fix-08b-scratch.sh)
    # 条件Dの最初の学習（40-formatter-r3-d-08b-drop0.sh）と同じ元のQwen3.5-0.8Bから始める。
    TAG="FIX-0.8B-scratch"
    MODEL="$FR3/hf-cache/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17"
    EPOCHS=2
    LR=2e-5
    ;;
  71-wops-fix-08b-cont.sh)
    TAG="FIX-0.8B-cont"
    MODEL="$WORK/outputs/RSI-0.8B/best"
    EPOCHS=1
    LR=1e-5
    ;;
  *) echo "不明なジョブ名: $0" >&2; exit 2 ;;
esac

GPU_ID="${CUDA_VISIBLE_DEVICES:?キューのGPU割当が必要}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "指定外のGPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader

OUTPUT="$WORK/outputs/$TAG"
TRAIN="$FIX/data/train-fixed.jsonl"
AUGMENTED="$FIX/data/augmentation-fixed.jsonl"
test ! -e "$OUTPUT"
test -s "$FIX/data/fix-audit.json"
test -s "$FIX/data/verify-dynamic-after.json"
test -e "$MODEL/config.json"

# キューの割当を引き継いで、他担当のプロセスと区別できる名前で実行する。
run_named() (
  local phase="$1"
  shift
  exec -a "voiceime-wops-$TAG-$phase" "$@"
)

run_named train "$PY" "$FIX/train_fix.py" \
  --model "$MODEL" --disable-cudnn-sdp \
  --train "$TRAIN" --augmentation "$AUGMENTED" \
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
  --method full --epochs "$EPOCHS" --learning-rate "$LR" \
  --batch-size 16 --grad-accum 2 --max-length 1024 --eval-steps 250 \
  --dataloader-workers 16 --gradient-checkpointing \
  --glossary-drop-prob 0 --max-distractors 8 --seed 0 --output-dir "$OUTPUT"

# r2（72-wops-rsi-train.sh）と同じ標準の一覧で評価する。
NOVEL="$FR3/inputs/test-novel-20261122"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
VAL="$D_INPUT/val-runs"
OUT="$WORK/runs/fix1/$TAG"

run_named eval "$PY" "$REPO/train/formatter/eval_transformers.py" \
  --model "$OUTPUT/best" --batch-size 32 --out-dir "$OUT/multiasr" \
  --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
  --glossary-run val-segment-merge "$VAL/formatter-glossary.jsonl" \
  --glossary-run test-novel-segment-merge "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --job-multiasr val-segment-merge "$FR3/inputs/manifest-val-no-audio.jsonl" \
    "$VAL/first-pass.jsonl" "$VAL/segment-merge.jsonl" "$VAL/qwen06-hypothesis.jsonl" - \
  --job-multiasr test-novel-segment-merge "$NOVEL/test-novel.jsonl" \
    "$NOVEL/a-plain.jsonl" "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
    "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" "$NOVEL/exclude-v2-83.txt"

# PMの容量評価と同じ一覧（上限20/32/48）で評価する。
bash "$FIX/capacity-eval.sh" "$TAG" "$OUTPUT/best"
