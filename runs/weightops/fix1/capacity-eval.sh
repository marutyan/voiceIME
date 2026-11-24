#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
D_INPUT="$WORK/inputs/d-multiasr-20261123"
NOVEL="$WORK/inputs/test-novel-20261122"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
LIST_DIR="$WORK/inputs/glossary-capacity-20261123-corrected"
BASE="$HOME/voiceime-work-wops/runs/capacity"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
# PMの容量評価（75-wops-capacity-rsi08b.sh）と同じ入力・一覧で、引数のモデルを評価する。
TAG="${1:?評価名}"
MODEL="${2:?重みの場所}"


GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "queue assigned an unavailable GPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader

VAL_MANIFEST="$WORK/inputs/manifest-val-no-audio.jsonl"
VAL_FIRST="$D_INPUT/val-runs/first-pass.jsonl"
VAL_COMBINED="$D_INPUT/val-runs/segment-merge.jsonl"
VAL_QWEN="$D_INPUT/val-runs/qwen06-hypothesis.jsonl"
NOVEL_MANIFEST="$NOVEL/test-novel.jsonl"
NOVEL_FIRST="$NOVEL/a-plain.jsonl"
NOVEL_COMBINED="$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl"
NOVEL_QWEN="$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl"
for path in \
  "$REPO" "$MODEL/config.json" "$VAL_MANIFEST" \
  "$VAL_FIRST" "$VAL_COMBINED" "$VAL_QWEN" \
  "$NOVEL_MANIFEST" "$NOVEL_FIRST" "$NOVEL_COMBINED" "$NOVEL_QWEN" \
  "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" "$NOVEL/exclude-v2-83.txt" \
  "$LIST_DIR/selection-audit.json"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
for variant in \
  max20-haas-qwen max20-haas-qwen-whisper \
  max32-haas-qwen max32-haas-qwen-whisper \
  max48-haas-qwen max48-haas-qwen-whisper; do
  test -e "$LIST_DIR/glossaries/val/$variant.jsonl" || exit 2
  test -e "$LIST_DIR/glossaries/test-novel/$variant.jsonl" || exit 2
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
INFER_OUT="$OUT/inference"
ARGS=(
  --model "$MODEL"
  --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl"
  --out-dir "$INFER_OUT"
  --batch-size 32
  --max-glossary 48
)
VAL_REPORT_ARGS=(--manifest "$VAL_MANIFEST")
NOVEL_REPORT_ARGS=(--manifest "$NOVEL_MANIFEST")
for variant in \
  max20-haas-qwen max20-haas-qwen-whisper \
  max32-haas-qwen max32-haas-qwen-whisper \
  max48-haas-qwen max48-haas-qwen-whisper; do
  val_job="val-$variant"
  novel_job="test-novel-$variant"
  ARGS+=(
    --glossary-run "$val_job" "$LIST_DIR/glossaries/val/$variant.jsonl"
    --glossary-run "$novel_job" "$LIST_DIR/glossaries/test-novel/$variant.jsonl"
    --job-multiasr "$val_job" "$VAL_MANIFEST" "$VAL_FIRST" "$VAL_COMBINED" "$VAL_QWEN" -
    --job-multiasr "$novel_job" "$NOVEL_MANIFEST" "$NOVEL_FIRST" "$NOVEL_COMBINED" "$NOVEL_QWEN" "$NOVEL/exclude-v2-83.txt"
  )
  VAL_REPORT_ARGS+=(--runs "$INFER_OUT/$val_job.jsonl")
  NOVEL_REPORT_ARGS+=(--runs "$INFER_OUT/$novel_job.jsonl")
done

run_named "voiceime-wops-capacity-eval" \
  "$PY" train/formatter/eval_transformers.py "${ARGS[@]}"

mkdir -p "$OUT/reports"
run_named "voiceime-wops-capacity-report-val" \
  "$PY" -m voiceime.eval.report "${VAL_REPORT_ARGS[@]}" > "$OUT/reports/val.report.txt"
run_named "voiceime-wops-capacity-report-novel" \
  "$PY" -m voiceime.eval.report "${NOVEL_REPORT_ARGS[@]}" > "$OUT/reports/test-novel.report.txt"
run_named "voiceime-wops-capacity-audit" \
  "$PY" "$WORK/launchers/audit_glossary_capacity_eval.py" \
    --val-manifest "$VAL_MANIFEST" --val-first "$VAL_FIRST" \
    --val-combined "$VAL_COMBINED" --val-qwen "$VAL_QWEN" \
    --test-novel-manifest "$NOVEL_MANIFEST" --test-novel-first "$NOVEL_FIRST" \
    --test-novel-combined "$NOVEL_COMBINED" --test-novel-qwen "$NOVEL_QWEN" \
    --results-dir "$INFER_OUT" --glossary-dir "$LIST_DIR/glossaries" \
    --output "$OUT/audit.json"

echo "Completed glossary capacity evaluation for $TAG."
