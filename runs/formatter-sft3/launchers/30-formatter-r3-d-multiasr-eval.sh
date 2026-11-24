#!/usr/bin/env bash
set -euo pipefail

JOB_NAME="${0##*/}"
WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
CURRENT="$WORK/inputs/term-select-metal2"
NOVEL="$WORK/inputs/test-novel-20261122"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
BASE="$WORK/runs/formatter-sft3/multiasr-reeval-20261123"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
MODEL=""
TAG=""
LOADER_ARGS=()

case "$JOB_NAME" in
  30-formatter-r3-d-multiasr-eval-B.sh)
    TAG="B"
    MODEL="$WORK/outputs/formatter-sft3-b-fla-20261122/final"
    ;;
  30-formatter-r3-d-multiasr-eval-B-2B.sh)
    TAG="B-2B"
    MODEL="$WORK/outputs/formatter-sft3-b-2b-20261122/final"
    LOADER_ARGS=(--use-model-loader)
    ;;
  30-formatter-r3-d-multiasr-eval-B-drop0-seed1.sh)
    TAG="B-drop0-seed1"
    MODEL="$WORK/outputs/formatter-sft3-b-drop0-seed1-mainselector21-20261122/final"
    ;;
  30-formatter-r3-d-multiasr-eval-B-2B-drop0.sh)
    TAG="B-2B-drop0"
    MODEL="$WORK/outputs/formatter-sft3-b-2b-drop0-mainselector21-20261122/final"
    LOADER_ARGS=(--use-model-loader)
    ;;
  *) echo "unknown evaluation launcher: $JOB_NAME" >&2; exit 2 ;;
esac

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "queue assigned an unavailable GPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader

VAL_MANIFEST="$WORK/inputs/manifest-val-no-audio.jsonl"
NOVEL_MANIFEST="$NOVEL/test-novel.jsonl"
VAL_GLOSSARY="$CURRENT/glossary.jsonl"
NOVEL_GLOSSARY=("$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl")
for path in \
  "$REPO" "$MODEL/config.json" "$VAL_MANIFEST" "$NOVEL_MANIFEST" \
  "$VAL_GLOSSARY" "${NOVEL_GLOSSARY[@]}" "$NOVEL/exclude-v2-83.txt" \
  "$CURRENT/val-plain.jsonl" "$NOVEL/a-plain.jsonl" \
  "$MULTIASR/haas-plus-qwen06-val-plain.jsonl" \
  "$MULTIASR/haas-plus-qwen06-val-segment-merge.jsonl" \
  "$MULTIASR/haas-plus-qwen06-test-novel-plain.jsonl" \
  "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
  "$MULTIASR/formatter-glossary-qwen06-val.jsonl" \
  "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
test ! -e "$BASE/$TAG" || { echo "evaluation output already exists: $BASE/$TAG" >&2; exit 2; }

cd "$REPO"
export HF_HOME="$WORK/hf-cache"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$REPO/src:$WORK/python-deps:$KERNEL_SITE:$TORCH_SITE"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false

run_named() {
  local process_name="$1"
  shift
  (exec -a "$process_name" "$@")
}

OUT="$BASE/$TAG"
run_named "voiceime-formatter-r3-d-eval-$TAG" "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL" "${LOADER_ARGS[@]}" \
  --glossary "$VAL_GLOSSARY" "${NOVEL_GLOSSARY[@]}" \
  --out-dir "$OUT/combined" --batch-size 32 \
  --glossary-run val-qwen-plain "$MULTIASR/formatter-glossary-qwen06-val.jsonl" \
  --glossary-run val-qwen-segment-merge "$MULTIASR/formatter-glossary-qwen06-val.jsonl" \
  --glossary-run test-novel-qwen-plain "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --glossary-run test-novel-qwen-segment-merge "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --job-both val-qwen-plain "$VAL_MANIFEST" "$CURRENT/val-plain.jsonl" \
    "$MULTIASR/haas-plus-qwen06-val-plain.jsonl" - \
  --job-both val-qwen-segment-merge "$VAL_MANIFEST" "$CURRENT/val-plain.jsonl" \
    "$MULTIASR/haas-plus-qwen06-val-segment-merge.jsonl" - \
  --job-both test-novel-qwen-plain "$NOVEL_MANIFEST" "$NOVEL/a-plain.jsonl" \
    "$MULTIASR/haas-plus-qwen06-test-novel-plain.jsonl" "$NOVEL/exclude-v2-83.txt" \
  --job-both test-novel-qwen-segment-merge "$NOVEL_MANIFEST" "$NOVEL/a-plain.jsonl" \
    "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" "$NOVEL/exclude-v2-83.txt"

mkdir -p "$OUT/reports"
run_named "voiceime-formatter-r3-d-report-$TAG-val" "$PY" -m voiceime.eval.report \
  --manifest "$VAL_MANIFEST" \
  --runs "$OUT/combined/val-qwen-plain.jsonl" "$OUT/combined/val-qwen-segment-merge.jsonl" \
  > "$OUT/reports/val.report.txt"
run_named "voiceime-formatter-r3-d-report-$TAG-test-novel" "$PY" -m voiceime.eval.report \
  --manifest "$NOVEL_MANIFEST" \
  --runs "$OUT/combined/test-novel-qwen-plain.jsonl" \
    "$OUT/combined/test-novel-qwen-segment-merge.jsonl" \
  > "$OUT/reports/test-novel.report.txt"
echo "Completed multilingual-ASR reevaluation for $TAG."
