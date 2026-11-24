#!/usr/bin/env bash
set -euo pipefail

JOB_NAME="${0##*/}"
case "$JOB_NAME" in
  20-formatter-r3-b-mainselect-drop0.sh)
    TAG="drop0"; DROP=0; DISTRACTORS=8
    ;;
  20-formatter-r3-b-mainselect-distractors0.sh)
    TAG="distractors0"; DROP=0.15; DISTRACTORS=0
    ;;
  20-formatter-r3-b-mainselect-clean.sh)
    TAG="clean"; DROP=0; DISTRACTORS=0
    ;;
  *) echo "unknown variant launcher: $JOB_NAME" >&2; exit 2 ;;
esac

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
INPUT="$WORK/inputs/sft3-20261122"
CURRENT="$WORK/inputs/term-select-metal2"
PRIVATE="$WORK/inputs/formatter-sft3-current"
NOVEL="$WORK/inputs/test-novel-20261122"
MODEL="$WORK/hf-cache/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17"
OUTPUT="$WORK/outputs/formatter-sft3-b-mainselect-$TAG-20261122"
EVAL="$WORK/runs/formatter-sft3/mainselect-b-$TAG-20261122"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" != *,* ]] || { echo "queue assigned multiple GPUs: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
for path in \
  "$REPO" "$MODEL" "$INPUT/train-sft3.jsonl" "$INPUT/haas-train-clean.jsonl" \
  "$INPUT/haas2p-train-clean.jsonl" "$INPUT/glossary-v2-train-clean.jsonl" \
  "$WORK/inputs/val-select.jsonl" "$INPUT/haas-val.jsonl" "$WORK/inputs/haas2p-val.jsonl" \
  "$CURRENT/glossary.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" \
  "$CURRENT/unseen-terms-devuser.txt" "$PRIVATE/manifest-devuser-no-audio.jsonl" \
  "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" \
  "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" \
  "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" "$NOVEL/exclude-v2-83.txt"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
test ! -e "$OUTPUT" || { echo "training output already exists: $OUTPUT" >&2; exit 2; }
test ! -e "$EVAL" || { echo "evaluation output already exists: $EVAL" >&2; exit 2; }

cd "$REPO"
export HF_HOME="$WORK/hf-cache"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$REPO/src:$WORK/python-deps:$KERNEL_SITE:$TORCH_SITE"
export PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false

run_named() {
  local process_name="$1"
  shift
  (exec -a "$process_name" "$@")
}

run_named "voiceime-formatter-r3-$TAG-train" "$PY" train/formatter/train.py \
  --model "$MODEL" \
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
  --batch-size 32 \
  --grad-accum 1 \
  --max-length 1024 \
  --eval-steps 250 \
  --dataloader-workers 16 \
  --gradient-checkpointing \
  --glossary-drop-prob "$DROP" \
  --max-distractors "$DISTRACTORS" \
  --seed 0 \
  --output-dir "$OUTPUT"

CURRENT_OUT="$EVAL/current"
NOVEL_OUT="$EVAL/test-novel"
mkdir -p "$CURRENT_OUT" "$NOVEL_OUT"
run_named "voiceime-formatter-r3-$TAG-current-eval" "$PY" train/formatter/eval_transformers.py \
  --model "$OUTPUT/final" --glossary "$CURRENT/glossary.jsonl" \
  --out-dir "$CURRENT_OUT" --batch-size 32 \
  --job-both devuser-s-50 "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" - \
  --job-both devuser-s-50-no-unseen "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" "$CURRENT/unseen-terms-devuser.txt" \
  --job-both val-asr-1000 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" -
run_named "voiceime-formatter-r3-$TAG-testnovel-eval" "$PY" train/formatter/eval_transformers.py \
  --model "$OUTPUT/final" --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
  --out-dir "$NOVEL_OUT" --batch-size 32 \
  --job-both test-novel-include-novel "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" "$NOVEL/exclude-v2-83.txt"

run_named "voiceime-formatter-r3-$TAG-report-devuser" "$PY" -m voiceime.eval.report \
  --manifest "$PRIVATE/manifest-devuser-no-audio.jsonl" --runs "$CURRENT_OUT/devuser-s-50.jsonl" \
  --unseen-terms "$CURRENT/unseen-terms-devuser.txt" > "$EVAL/devuser.report.txt"
run_named "voiceime-formatter-r3-$TAG-report-devuser-no-unseen" "$PY" -m voiceime.eval.report \
  --manifest "$PRIVATE/manifest-devuser-no-audio.jsonl" --runs "$CURRENT_OUT/devuser-s-50-no-unseen.jsonl" \
  --unseen-terms "$CURRENT/unseen-terms-devuser.txt" > "$EVAL/devuser-no-unseen.report.txt"
run_named "voiceime-formatter-r3-$TAG-report-val" "$PY" -m voiceime.eval.report \
  --manifest "$WORK/inputs/manifest-val-no-audio.jsonl" --runs "$CURRENT_OUT/val-asr-1000.jsonl" \
  > "$EVAL/val.report.txt"
run_named "voiceime-formatter-r3-$TAG-report-testnovel" "$PY" -m voiceime.eval.report \
  --manifest "$NOVEL/test-novel.jsonl" --runs "$NOVEL_OUT/test-novel-include-novel.jsonl" \
  > "$EVAL/test-novel.report.txt"
echo "Main-glossary variant $TAG training and evaluation completed."
