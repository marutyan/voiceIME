#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
CURRENT="$WORK/inputs/term-select-metal2"
LATENCY="$WORK/runs/formatter-sft3/batch1-latency-mainselector21-20261123"
PY="$WORK/kernels-venv/bin/python"
KERNEL_SITE="$WORK/kernels-venv/lib/python3.12/site-packages"
TORCH_SITE="$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
MODEL_08B="$WORK/outputs/formatter-sft3-b-drop0-seed1-mainselector21-20261122/final"
MODEL_2B="$WORK/outputs/formatter-sft3-b-2b-drop0-mainselector21-20261122/final"

GPU_ID="${CUDA_VISIBLE_DEVICES:?queue must assign one GPU}"
[[ "$GPU_ID" != *,* ]] || { echo "queue assigned multiple GPUs: $GPU_ID" >&2; exit 2; }
nvidia-smi --id="$GPU_ID" --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader
for path in "$REPO" "$MODEL_08B/config.json" "$MODEL_2B/config.json" \
  "$CURRENT/glossary.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" \
  "$WORK/inputs/manifest-val-no-audio.jsonl"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done
test ! -e "$LATENCY" || { echo "latency output already exists: $LATENCY" >&2; exit 2; }

cd "$REPO"
export HF_HOME="$WORK/hf-cache"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$REPO/src:$WORK/python-deps:$KERNEL_SITE:$TORCH_SITE"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
mkdir -p "$LATENCY/0.8B" "$LATENCY/2B"

run_named() {
  local process_name="$1"
  shift
  (exec -a "$process_name" "$@")
}

run_named voiceime-formatter-r3-drop0-latency-0.8b "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL_08B" --glossary "$CURRENT/glossary.jsonl" \
  --out-dir "$LATENCY/0.8B" --batch-size 1 \
  --job-both val-batch1 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" -

run_named voiceime-formatter-r3-drop0-latency-2b "$PY" train/formatter/eval_transformers.py \
  --model "$MODEL_2B" --use-model-loader \
  --glossary "$CURRENT/glossary.jsonl" \
  --out-dir "$LATENCY/2B" --batch-size 1 \
  --job-both val-batch1 "$WORK/inputs/manifest-val-no-audio.jsonl" "$CURRENT/val-plain.jsonl" "$CURRENT/val-asr.jsonl" -

"$PY" - "$LATENCY" <<'PY'
import json
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
summary = {}
for name in ("0.8B", "2B"):
    path = root / name / "val-batch1.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or any(row.get("batch_size") != 1 for row in rows):
        raise SystemExit(f"{name}: batch size was not 1 for every row")
    values = [row["format_latency_s"] for row in rows]
    summary[name] = {
        "n": len(values),
        "median_format_latency_s": statistics.median(values),
        "mean_format_latency_s": statistics.mean(values),
        "p90_format_latency_s": sorted(values)[int(0.9 * (len(values) - 1))],
    }
output = root / "summary.json"
output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
