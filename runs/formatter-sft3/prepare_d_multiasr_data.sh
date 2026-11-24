#!/usr/bin/env bash
set -euo pipefail

WORK="$HOME/voiceime-work-fr3"
REPO="$WORK/repo"
INPUT="$WORK/inputs/sft3-20261122"
D_INPUT="$WORK/inputs/d-multiasr-20261123"
ASR_ROOT="$HOME/voiceime-work-asr/r3-multiasr-train-20261123"
ASR_BASE="$HOME/voiceime-work-asr"
MAIN_SRC="$ASR_ROOT/main-code/src"
ASR_SITE="$ASR_BASE/.venv/lib/python3.12/site-packages"
QWEN="$WORK/runs/formatter-sft3/d-multiasr-legacy-20261123/qwen06-firstpass-shard-99.jsonl"
PY="$WORK/kernels-venv/bin/python"
PYTHON_BASE="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
EXCLUSIONS="$ASR_BASE/r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"

for path in "$REPO" "$PY" "$INPUT/train-sft3.jsonl" "$WORK/inputs/val-select.jsonl" \
  "$INPUT/haas-train-clean.jsonl" "$INPUT/haas2p-train-clean.jsonl" \
  "$WORK/inputs/c-asr-20261122/b-oldtrain-segment-merge.jsonl" "$QWEN" \
  "$ASR_ROOT/outputs/train-available-12000.jsonl" "$ASR_ROOT/outputs/val-1000.jsonl" \
  "$ASR_BASE/data/glossary/glossary.jsonl" "$ASR_BASE/data/glossary/glossary-v2.jsonl" \
  "$EXCLUSIONS" "$MAIN_SRC"; do
  test -e "$path" || { echo "missing required path: $path" >&2; exit 2; }
done

mkdir -p "$D_INPUT"
for path in "$D_INPUT/legacy" "$D_INPUT/train-runs" "$D_INPUT/val-runs"; do
  if [[ -e "$path" ]] && [[ -n "$(find "$path" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "refusing to overwrite prepared data: $path" >&2
    exit 2
  fi
done

export PYTHONHOME="$PYTHON_BASE"
export PYTHONPATH="$ASR_SITE"
export PYTHONUNBUFFERED=1

"$PY" "$REPO/runs/formatter-sft3/prepare_legacy_multiasr.py" \
  --main-src "$MAIN_SRC" \
  --haas-first "$INPUT/haas-train-clean.jsonl" \
  --haas-second "$INPUT/haas2p-train-clean.jsonl" \
  --segment-merge "$WORK/inputs/c-asr-20261122/b-oldtrain-segment-merge.jsonl" \
  --qwen "$QWEN" \
  --glossary-v1 "$ASR_BASE/data/glossary/glossary.jsonl" \
  --glossary-v2 "$ASR_BASE/data/glossary/glossary-v2.jsonl" \
  --exclusions "$EXCLUSIONS" \
  --output-dir "$D_INPUT/legacy"

"$PY" "$REPO/runs/formatter-sft3/prepare_multiasr_runs.py" \
  --source "$ASR_ROOT/outputs/train-available-12000.jsonl" \
  --source "$D_INPUT/legacy/legacy-combined.jsonl" \
  --out-dir "$D_INPUT/train-runs"

"$PY" "$REPO/runs/formatter-sft3/prepare_multiasr_runs.py" \
  --source "$ASR_ROOT/outputs/val-1000.jsonl" \
  --out-dir "$D_INPUT/val-runs"

"$PY" "$REPO/runs/formatter-sft3/audit_d_training_data.py" \
  --train "$INPUT/train-sft3.jsonl" \
  --train-runs "$D_INPUT/train-runs" \
  --val "$WORK/inputs/val-select.jsonl" \
  --val-runs "$D_INPUT/val-runs" \
  --glossary "$D_INPUT/legacy/training-glossary.jsonl" \
  --exclusions "$EXCLUSIONS" \
  --novel-terms "$INPUT/novel-terms.txt" \
  --output "$D_INPUT/audit.json"
