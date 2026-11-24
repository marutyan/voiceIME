#!/usr/bin/env bash
set -euo pipefail

JOB_NAME="${0##*/}"
WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
D_INPUT="$WORK/inputs/d-multiasr-20261123"
CURRENT="$WORK/inputs/term-select-metal2"
DEV_PRIVATE="$WORK/inputs/d-eval-devuser-20261123"
NOVEL="$WORK/inputs/test-novel-20261122"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
BASE="/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
MODEL=""
TAG=""
LOADER_ARGS=()
MEASURE_LATENCY=no

case "$JOB_NAME" in
  51-formatter-r3-d-eval-08b-drop0075-restart1.sh)
    TAG="D-0.8B-drop0.075"
    MODEL="/var/tmp/voiceime-work-fr3-d-20261123/outputs/formatter-sft3-d-0.8b-drop0075-restart1/final"
    MEASURE_LATENCY=yes
    ;;
  51-formatter-r3-d-eval-2b-drop0075-restart1.sh)
    TAG="D-2B-drop0.075"
    MODEL="/var/tmp/voiceime-work-fr3-d-20261123/outputs/formatter-sft3-d-2b-drop0075-restart1/final"
    LOADER_ARGS=(--use-model-loader)
    MEASURE_LATENCY=yes
    ;;
  51-formatter-r3-d-eval-08b-drop0-restart1.sh)
    TAG="D-0.8B-drop0"
    MODEL="/var/tmp/voiceime-work-fr3-d-20261123/outputs/formatter-sft3-d-0.8b-drop0-restart1/final"
    ;;
  *) echo "unknown D evaluation launcher: $JOB_NAME" >&2; exit 2 ;;
esac

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "queue assigned an unavailable GPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
VAL_MANIFEST="$WORK/inputs/manifest-val-no-audio.jsonl"
DEV_MANIFEST="$DEV_PRIVATE/manifest-devuser-no-audio.jsonl"
for path in \
  "$REPO" "$MODEL/config.json" "$VAL_MANIFEST" "$DEV_MANIFEST" \
  "$D_INPUT/val-runs/first-pass.jsonl" "$D_INPUT/val-runs/segment-merge.jsonl" \
  "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/exclude-v2-83.txt" \
  "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" \
  "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
  "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  "$DEV_PRIVATE/devuser-plain.jsonl" "$DEV_PRIVATE/devuser-asr.jsonl" \
  "$CURRENT/glossary.jsonl" "$CURRENT/unseen-terms-devuser.txt"; do
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
OUT="$BASE/$TAG"
cleanup_private_outputs() {
  rm -f "$OUT/devuser/devuser-s-50.jsonl" "$OUT/devuser/devuser-s-50-no-unseen.jsonl" \
    "$OUT/devuser/devuser-s-50.jsonl.partial" \
    "$OUT/devuser/devuser-s-50-no-unseen.jsonl.partial"
}
trap cleanup_private_outputs EXIT
mkdir -p "$OUT/reports"

run_named() {
  local process_name="$1"
  shift
  (exec -a "$process_name" "$@")
}

run_named "voiceime-formatter-r3-d-eval-$TAG-multiasr" "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL" "${LOADER_ARGS[@]}" \
  --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
  --out-dir "$OUT/multiasr" --batch-size 32 \
  --glossary-run val-segment-merge "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  --glossary-run test-novel-segment-merge "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --job-multiasr val-segment-merge "$VAL_MANIFEST" \
    "$D_INPUT/val-runs/first-pass.jsonl" "$D_INPUT/val-runs/segment-merge.jsonl" \
    "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" - \
  --job-multiasr test-novel-segment-merge "$NOVEL/test-novel.jsonl" \
    "$NOVEL/a-plain.jsonl" "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
    "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" "$NOVEL/exclude-v2-83.txt"

run_named "voiceime-formatter-r3-d-eval-$TAG-devuser" "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL" "${LOADER_ARGS[@]}" --glossary "$CURRENT/glossary.jsonl" \
  --out-dir "$OUT/devuser" --batch-size 32 \
  --job-multiasr devuser-s-50 "$DEV_MANIFEST" "$DEV_PRIVATE/devuser-plain.jsonl" \
    "$DEV_PRIVATE/devuser-asr.jsonl" - - \
  --job-multiasr devuser-s-50-no-unseen "$DEV_MANIFEST" "$DEV_PRIVATE/devuser-plain.jsonl" \
    "$DEV_PRIVATE/devuser-asr.jsonl" - "$CURRENT/unseen-terms-devuser.txt"

run_named "voiceime-formatter-r3-d-report-$TAG-val" "$PY" -m voiceime.eval.report \
  --manifest "$VAL_MANIFEST" --runs "$OUT/multiasr/val-segment-merge.jsonl" \
  > "$OUT/reports/val.report.txt"
run_named "voiceime-formatter-r3-d-report-$TAG-test-novel" "$PY" -m voiceime.eval.report \
  --manifest "$NOVEL/test-novel.jsonl" --runs "$OUT/multiasr/test-novel-segment-merge.jsonl" \
  > "$OUT/reports/test-novel.report.txt"
run_named "voiceime-formatter-r3-d-audit-$TAG" "$PY" runs/formatter-sft3/audit_d_eval.py \
  --results-dir "$OUT/multiasr" \
  --val-manifest "$VAL_MANIFEST" \
  --val-first "$D_INPUT/val-runs/first-pass.jsonl" \
  --val-combined "$D_INPUT/val-runs/segment-merge.jsonl" \
  --val-qwen "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" \
  --val-glossary "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  --test-novel-manifest "$NOVEL/test-novel.jsonl" \
  --test-novel-first "$NOVEL/a-plain.jsonl" \
  --test-novel-combined "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
  --test-novel-qwen "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" \
  --test-novel-glossary "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --output "$OUT/audit.json"
run_named "voiceime-formatter-r3-d-report-$TAG-devuser" "$PY" -m voiceime.eval.report \
  --manifest "$DEV_MANIFEST" --runs "$OUT/devuser/devuser-s-50.jsonl" \
    "$OUT/devuser/devuser-s-50-no-unseen.jsonl" \
  > "$OUT/reports/devuser.report.txt"

if [[ "$MEASURE_LATENCY" == "yes" ]]; then
  LATENCY_OUT="$OUT/latency-val-batch1"
  run_named "voiceime-formatter-r3-d-latency-$TAG-batch1" "$PY" train/formatter/eval_transformers.py \
    --model "$MODEL" "${LOADER_ARGS[@]}" \
    --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
    --out-dir "$LATENCY_OUT" --batch-size 1 \
    --glossary-run val-batch1 "$D_INPUT/val-runs/formatter-glossary.jsonl" \
    --job-multiasr val-batch1 "$VAL_MANIFEST" \
      "$D_INPUT/val-runs/first-pass.jsonl" "$D_INPUT/val-runs/segment-merge.jsonl" \
      "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" -
  run_named "voiceime-formatter-r3-d-latency-summary-$TAG" "$PY" \
    runs/formatter-sft3/summarize_batch1_latency.py \
    --input "$LATENCY_OUT/val-batch1.jsonl" --output "$OUT/latency-val-batch1.json"
fi

echo "Completed D evaluation for $TAG."
