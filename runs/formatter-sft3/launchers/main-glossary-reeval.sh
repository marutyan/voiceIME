#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
CURRENT="$WORK/inputs/term-select-metal2"
PRIVATE="$WORK/inputs/formatter-sft3-current"
NOVEL="$WORK/inputs/test-novel-20261122"
BASE="$WORK/runs/formatter-sft3/main-glossary-reeval-20261122"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" != *,* ]] || { echo "queue assigned multiple GPUs: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader

for path in \
  "$REPO" \
  "$PRIVATE/manifest-devuser-no-audio.jsonl" \
  "$WORK/inputs/manifest-val-no-audio.jsonl" \
  "$CURRENT/glossary.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" \
  "$CURRENT/unseen-terms-devuser.txt" \
  "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" \
  "$PRIVATE/e2e-devuser.jsonl" "$PRIVATE/e2e-val.jsonl" \
  "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" \
  "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" "$NOVEL/exclude-v2-83.txt"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
for path in \
  "$WORK/outputs/formatter-sft3-a-fla-20261122/final" \
  "$WORK/outputs/formatter-sft3-b-fla-20261122/final" \
  "$WORK/outputs/formatter-sft3-c-accepted-20261122/final" \
  "$WORK/outputs/formatter-sft3-b-2b-20261122/final"; do
  test -d "$path" || { echo "missing model: $path" >&2; exit 2; }
done
test ! -e "$BASE" || { echo "output already exists: $BASE" >&2; exit 2; }

cd "$REPO"
export HF_HOME="$WORK/hf-cache"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$REPO/src:$WORK/python-deps:$KERNEL_SITE:$TORCH_SITE"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
mkdir -p "$BASE"

run_named() {
  local process_name="$1"
  shift
  (exec -a "$process_name" "$@")
}

eval_current() {
  local name="$1" model="$2" input_mode="$3" use_loader="$4"
  local out="$BASE/$name/current"
  local loader_args=()
  [[ "$use_loader" == "yes" ]] && loader_args+=(--use-model-loader)
  mkdir -p "$out"
  case "$input_mode" in
    single)
      run_named "voiceime-formatter-r3-mainselect-$name-current" "$PY" train/formatter/eval_transformers.py \
        --model "$model" "${loader_args[@]}" --glossary "$CURRENT/glossary.jsonl" --out-dir "$out" --batch-size 32 \
        --job devuser-s-50 "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-asr.jsonl" - \
        --job devuser-s-50-no-unseen "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-asr.jsonl" "$CURRENT/unseen-terms-devuser.txt" \
        --job val-asr-1000 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-asr.jsonl" -
      ;;
    both)
      run_named "voiceime-formatter-r3-mainselect-$name-current" "$PY" train/formatter/eval_transformers.py \
        --model "$model" "${loader_args[@]}" --glossary "$CURRENT/glossary.jsonl" --out-dir "$out" --batch-size 32 \
        --job-both devuser-s-50 "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" - \
        --job-both devuser-s-50-no-unseen "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" "$CURRENT/unseen-terms-devuser.txt" \
        --job-both val-asr-1000 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" -
      ;;
    combined_first)
      run_named "voiceime-formatter-r3-mainselect-$name-current" "$PY" train/formatter/eval_transformers.py \
        --model "$model" "${loader_args[@]}" --glossary "$CURRENT/glossary.jsonl" --out-dir "$out" --batch-size 32 \
        --job-combined-first devuser-s-50 "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" - \
        --job-combined-first devuser-s-50-no-unseen "$PRIVATE/manifest-devuser-no-audio.jsonl" "$PRIVATE/devuser-plain.jsonl" "$PRIVATE/devuser-asr.jsonl" "$CURRENT/unseen-terms-devuser.txt" \
        --job-combined-first val-asr-1000 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" -
      ;;
  esac
}

eval_novel() {
  local name="$1" model="$2" input_mode="$3" use_loader="$4"
  local out="$BASE/$name/test-novel"
  local loader_args=()
  [[ "$use_loader" == "yes" ]] && loader_args+=(--use-model-loader)
  mkdir -p "$out"
  case "$input_mode" in
    single)
      run_named "voiceime-formatter-r3-mainselect-$name-novel" "$PY" train/formatter/eval_transformers.py \
        --model "$model" "${loader_args[@]}" --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
        --out-dir "$out" --batch-size 32 \
        --job test-novel-include-novel "$NOVEL/test-novel.jsonl" "$NOVEL/a-segment-merge.jsonl" "$NOVEL/exclude-v2-83.txt"
      ;;
    both)
      run_named "voiceime-formatter-r3-mainselect-$name-novel" "$PY" train/formatter/eval_transformers.py \
        --model "$model" "${loader_args[@]}" --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
        --out-dir "$out" --batch-size 32 \
        --job-both test-novel-include-novel "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" "$NOVEL/exclude-v2-83.txt"
      ;;
    combined_first)
      run_named "voiceime-formatter-r3-mainselect-$name-novel" "$PY" train/formatter/eval_transformers.py \
        --model "$model" "${loader_args[@]}" --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
        --out-dir "$out" --batch-size 32 \
        --job-combined-first test-novel-include-novel "$NOVEL/test-novel.jsonl" "$NOVEL/a-plain.jsonl" "$NOVEL/a-segment-merge.jsonl" "$NOVEL/exclude-v2-83.txt"
      ;;
  esac
}

eval_current A "$WORK/outputs/formatter-sft3-a-fla-20261122/final" single no
eval_novel A "$WORK/outputs/formatter-sft3-a-fla-20261122/final" single no
eval_current B "$WORK/outputs/formatter-sft3-b-fla-20261122/final" both no
eval_novel B "$WORK/outputs/formatter-sft3-b-fla-20261122/final" both no
eval_current C "$WORK/outputs/formatter-sft3-c-accepted-20261122/final" combined_first no
eval_novel C "$WORK/outputs/formatter-sft3-c-accepted-20261122/final" combined_first no
eval_current B-2B "$WORK/outputs/formatter-sft3-b-2b-20261122/final" both yes
eval_novel B-2B "$WORK/outputs/formatter-sft3-b-2b-20261122/final" both yes

run_named voiceime-formatter-r3-mainselect-report-devuser "$PY" -m voiceime.eval.report \
  --manifest "$PRIVATE/manifest-devuser-no-audio.jsonl" \
  --runs "$PRIVATE/e2e-devuser.jsonl" \
    "$BASE/A/current/devuser-s-50.jsonl" "$BASE/B/current/devuser-s-50.jsonl" \
    "$BASE/C/current/devuser-s-50.jsonl" "$BASE/B-2B/current/devuser-s-50.jsonl" \
  > "$BASE/devuser-all.report.txt"
run_named voiceime-formatter-r3-mainselect-report-devuser-no-unseen "$PY" -m voiceime.eval.report \
  --manifest "$PRIVATE/manifest-devuser-no-audio.jsonl" \
  --runs "$BASE/A/current/devuser-s-50-no-unseen.jsonl" "$BASE/B/current/devuser-s-50-no-unseen.jsonl" \
    "$BASE/C/current/devuser-s-50-no-unseen.jsonl" "$BASE/B-2B/current/devuser-s-50-no-unseen.jsonl" \
  --unseen-terms "$CURRENT/unseen-terms-devuser.txt" > "$BASE/devuser-no-unseen.report.txt"
run_named voiceime-formatter-r3-mainselect-report-val "$PY" -m voiceime.eval.report \
  --manifest "$WORK/inputs/manifest-val-no-audio.jsonl" \
  --runs "$PRIVATE/e2e-val.jsonl" \
    "$BASE/A/current/val-asr-1000.jsonl" "$BASE/B/current/val-asr-1000.jsonl" \
    "$BASE/C/current/val-asr-1000.jsonl" "$BASE/B-2B/current/val-asr-1000.jsonl" \
  > "$BASE/val.report.txt"
run_named voiceime-formatter-r3-mainselect-report-testnovel "$PY" -m voiceime.eval.report \
  --manifest "$NOVEL/test-novel.jsonl" \
  --runs "$PRIVATE/e2e-testnovel-sft2.jsonl" \
    "$BASE/A/test-novel/test-novel-include-novel.jsonl" \
    "$BASE/B/test-novel/test-novel-include-novel.jsonl" \
    "$BASE/C/test-novel/test-novel-include-novel.jsonl" \
    "$BASE/B-2B/test-novel/test-novel-include-novel.jsonl" \
  > "$BASE/test-novel.report.txt"

echo "Main glossary reevaluation completed."
