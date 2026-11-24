#!/usr/bin/env bash
set -euo pipefail

JOB_NAME="${0##*/}"
case "$JOB_NAME" in
  20-formatter-r3-b-drop0-focus-eval.sh)
    TAG="b-drop0-focus"; MODEL="$HOME/voiceime-work-fr3/outputs/formatter-sft3-b-drop0-focus-20261122/final"; USE_LOADER=0
    ;;
  20-formatter-r3-b-drop0-seed1-eval.sh)
    TAG="b-drop0-seed1"; MODEL="$HOME/voiceime-work-fr3/outputs/formatter-sft3-b-drop0-seed1-20261122/final"; USE_LOADER=0
    ;;
  20-formatter-r3-b2b-drop0-eval.sh)
    TAG="b-2b-drop0"; MODEL="$HOME/voiceime-work-fr3/outputs/formatter-sft3-b-2b-drop0-20261122/final"; USE_LOADER=1
    ;;
  *) echo "unknown evaluation launcher: $JOB_NAME" >&2; exit 2 ;;
esac

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
CURRENT="$WORK/inputs/term-select-metal2"
PRIVATE="$WORK/inputs/formatter-sft3-current"
NOVEL="$WORK/inputs/test-novel-20261122"
MANIFEST="$PRIVATE/manifest-devuser-scripted-fixed-no-audio-20261122.jsonl"
BASE="$WORK/runs/formatter-sft3/corrected-eval-$TAG-20261122"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" != *,* ]] || { echo "queue assigned multiple GPUs: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
for path in \
  "$REPO" "$MODEL/config.json" "$MANIFEST" "$PRIVATE/devuser-plain.jsonl" \
  "$PRIVATE/devuser-asr.jsonl" "$CURRENT/glossary.jsonl" \
  "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" \
  "$CURRENT/unseen-terms-devuser.txt" "$WORK/inputs/manifest-val-no-audio.jsonl" \
  "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" \
  "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" "$NOVEL/exclude-v2-83.txt"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
test ! -e "$BASE" || { echo "evaluation output already exists: $BASE" >&2; exit 2; }

cd "$REPO"
export HF_HOME="$WORK/hf-cache"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$REPO/src:$WORK/python-deps:$KERNEL_SITE:$TORCH_SITE"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
mkdir -p "$BASE/current" "$BASE/test-novel"

run_named() {
  local process_name="$1"
  shift
  (exec -a "$process_name" "$@")
}
LOADER_ARGS=()
[[ "$USE_LOADER" == 1 ]] && LOADER_ARGS+=(--use-model-loader)

run_named "voiceime-formatter-r3-$TAG-current-eval" "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL" "${LOADER_ARGS[@]}" --glossary "$CURRENT/glossary.jsonl" \
  --out-dir "$BASE/current" --batch-size 32 \
  --job-both devuser-s-50 "$MANIFEST" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" - \
  --job-both devuser-s-50-no-unseen "$MANIFEST" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" "$CURRENT/unseen-terms-devuser.txt" \
  --job-both val-asr-1000 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" -

run_named "voiceime-formatter-r3-$TAG-testnovel-eval" "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL" "${LOADER_ARGS[@]}" \
  --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
  --out-dir "$BASE/test-novel" --batch-size 32 \
  --job-both test-novel-include-novel "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" "$NOVEL/exclude-v2-83.txt"

run_named "voiceime-formatter-r3-$TAG-report-devuser" "$PY" -m voiceime.eval.report \
  --manifest "$MANIFEST" --runs "$BASE/current/devuser-s-50.jsonl" \
  --unseen-terms "$CURRENT/unseen-terms-devuser.txt" > "$BASE/devuser.report.txt"
run_named "voiceime-formatter-r3-$TAG-report-devuser-no-unseen" "$PY" -m voiceime.eval.report \
  --manifest "$MANIFEST" --runs "$BASE/current/devuser-s-50-no-unseen.jsonl" \
  --unseen-terms "$CURRENT/unseen-terms-devuser.txt" > "$BASE/devuser-no-unseen.report.txt"
run_named "voiceime-formatter-r3-$TAG-report-val" "$PY" -m voiceime.eval.report \
  --manifest "$WORK/inputs/manifest-val-no-audio.jsonl" \
  --runs "$BASE/current/val-asr-1000.jsonl" > "$BASE/val.report.txt"
run_named "voiceime-formatter-r3-$TAG-report-testnovel" "$PY" -m voiceime.eval.report \
  --manifest "$NOVEL/test-novel.jsonl" \
  --runs "$BASE/test-novel/test-novel-include-novel.jsonl" > "$BASE/test-novel.report.txt"
echo "Evaluation completed for $TAG."
