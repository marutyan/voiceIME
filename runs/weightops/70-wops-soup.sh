#!/usr/bin/env bash
# facultyのキューで補間と既存条件Dの2 split評価を実行する。
set -euo pipefail

case "${0##*/}" in
  70-wops-soup-a025.sh) TAG=soup-a025; ALPHA=0.25 ;;
  70-wops-soup-a050.sh) TAG=soup-a050; ALPHA=0.5 ;;
  70-wops-soup-a075.sh) TAG=soup-a075; ALPHA=0.75 ;;
  *) echo "不明なキュージョブ名: $0" >&2; exit 2 ;;
esac

WORK="$HOME/voiceime-work-wops"
FR3="$HOME/voiceime-work-fr3"
REPO="$FR3/repo"
VAL="$FR3/inputs/d-multiasr-20261123/val-runs"
VAL_MANIFEST="$FR3/inputs/manifest-val-no-audio.jsonl"
NOVEL="$FR3/inputs/test-novel-20261122"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
PY="$FR3/kernels-venv/bin/python"
MODEL="$WORK/outputs/$TAG"
OUT="$WORK/runs/$TAG"

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" =~ ^[1-3]$ ]] || { echo "指定外のGPU: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader

export HF_HOME="$WORK/hf-cache"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
export PYTHONPATH="$REPO/src:$FR3/python-deps:$FR3/kernels-venv/lib/python3.12/site-packages:$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export XDG_CACHE_HOME="$WORK/cache" TORCH_HOME="$WORK/cache/torch" TRITON_CACHE_DIR="$WORK/cache/triton"

# キューから付与されたGPUを使い、プロセス名を他の担当と区別する。
run_named() (
  local role="$1"
  shift
  exec -a "voiceime-wops-$TAG-$role" "$@"
)

cd "$WORK"
run_named interpolate "$PY" "$WORK/interpolate.py" \
  "$FR3/outputs/formatter-sft3-d-0.8b-drop0-restart1/final" \
  "$FR3/outputs/formatter-sft3-d-0.8b-drop0075-restart1/final" "$ALPHA" "$MODEL"

run_named eval "$PY" "$REPO/train/formatter/eval_transformers.py" \
  --model "$MODEL" --glossary "$NOVEL/glossary-v1.jsonl" "$NOVEL/glossary-v2.jsonl" \
  --out-dir "$OUT/multiasr" --batch-size 32 \
  --glossary-run val-segment-merge "$VAL/formatter-glossary.jsonl" \
  --glossary-run test-novel-segment-merge "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --job-multiasr val-segment-merge "$VAL_MANIFEST" \
    "$VAL/first-pass.jsonl" "$VAL/segment-merge.jsonl" "$VAL/qwen06-hypothesis.jsonl" - \
  --job-multiasr test-novel-segment-merge "$NOVEL/test-novel.jsonl" \
    "$NOVEL/a-plain.jsonl" "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
    "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" "$NOVEL/exclude-v2-83.txt"

mkdir -p "$OUT/reports"
run_named report-val "$PY" -m voiceime.eval.report \
  --manifest "$VAL_MANIFEST" --runs "$OUT/multiasr/val-segment-merge.jsonl" \
  > "$OUT/reports/val.report.txt"
run_named report-test-novel "$PY" -m voiceime.eval.report \
  --manifest "$NOVEL/test-novel.jsonl" --runs "$OUT/multiasr/test-novel-segment-merge.jsonl" \
  > "$OUT/reports/test-novel.report.txt"
run_named audit "$PY" "$REPO/runs/formatter-sft3/audit_d_eval.py" \
  --results-dir "$OUT/multiasr" \
  --val-manifest "$VAL_MANIFEST" --val-first "$VAL/first-pass.jsonl" \
  --val-combined "$VAL/segment-merge.jsonl" --val-qwen "$VAL/qwen06-hypothesis.jsonl" \
  --val-glossary "$VAL/formatter-glossary.jsonl" \
  --test-novel-manifest "$NOVEL/test-novel.jsonl" --test-novel-first "$NOVEL/a-plain.jsonl" \
  --test-novel-combined "$MULTIASR/haas-plus-qwen06-test-novel-segment-merge.jsonl" \
  --test-novel-qwen "$MULTIASR/multiasr-test-novel-qwen06-firstpass.jsonl" \
  --test-novel-glossary "$MULTIASR/formatter-glossary-qwen06-test-novel.jsonl" \
  --output "$OUT/audit.json"
