#!/usr/bin/env bash
set -euo pipefail
source "$HOME/voiceime-work-real/scripts/formatter_env.sh"
gpu="${CUDA_VISIBLE_DEVICES:?キューからGPUの割当が必要}"
[[ "$gpu" =~ ^[1-3]$ ]]
nvidia-smi -i "$gpu" --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader

# 推論の入力3本と固定用語一覧を、既存の評価器の引数にそろえる。
condition_d_job() {
  local label="$1" manifest="$2" dir="$3"
  D_JOB=(--glossary-run "$label" "$dir/formatter-glossary.jsonl"
    --job-multiasr "$label" "$manifest" "$dir/first-pass.jsonl"
    "$dir/segment-merge.jsonl" "$dir/qwen06-hypothesis.jsonl" -)
}

phase="${0##*/}"
case "$phase" in
  82-real-teacher.sh)
    input="$REAL/teacher-inputs"
    condition_d_job real-teacher "$input/manifest.jsonl" "$input"
    exec -a voiceime-real-teacher "$PY" "$CODE/eval_transformers.py" \
      --model "$RSI" --batch-size 32 --out-dir "$REAL/teacher-output" \
      --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" "${D_JOB[@]}"
    ;;
  83-real-train.sh)
    tag=REAL-0.8B
    output="$REAL/outputs/$tag"
    test ! -e "$output"
    test -s "$FIX/data/verify-dynamic.json"
    exec -a "voiceime-real-train-$tag" "$PY" "$REAL/scripts/train_real.py" \
      --model "$RSI" --disable-cudnn-sdp \
      --train "$SYNTHETIC" \
      --real "$REAL/training-inputs/$tag.jsonl" --augmentation "$AUGMENTATION" \
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
      --glossary-drop-prob 0 --max-distractors 8 --seed 0 --output-dir "$output"
    ;;
  82-real-rsi-eval.sh)
    # valとtest-novelは既存のRSI評価を再利用する。
    condition_d_job pub-eval "$PUB_EVAL" "$REAL/pub-eval-inputs"
    exec -a voiceime-real-eval-rsi "$PY" "$CODE/eval_transformers.py" \
      --model "$RSI" --batch-size 32 --out-dir "$REAL/eval/RSI-0.8B" \
      --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" "${D_JOB[@]}"
    ;;
  84-real-eval.sh)
    tag=REAL-0.8B
    model="$REAL/outputs/$tag/best"
    condition_d_job val "$FR3/inputs/manifest-val-no-audio.jsonl" "$D_INPUT/val-runs"
    val_job=("${D_JOB[@]}")
    condition_d_job pub-eval "$PUB_EVAL" "$REAL/pub-eval-inputs"
    exec -a "voiceime-real-eval-$tag" "$PY" "$CODE/eval_transformers.py" \
      --model "$model" --batch-size 32 --out-dir "$REAL/eval/$tag" \
      --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
      "${val_job[@]}" "${D_JOB[@]}" \
      --glossary-run test-novel "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
      --job-multiasr test-novel "$NOVEL/test-novel.jsonl" \
        "$NOVEL/a-plain.jsonl" "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
        "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" "$NOVEL/exclude-v2-83.txt"
    ;;
  *) exit 2 ;;
esac
