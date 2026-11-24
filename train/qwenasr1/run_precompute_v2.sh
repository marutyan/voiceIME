#!/usr/bin/env bash
set -euo pipefail

# v2のtrainと選択用validation音声をlog-melへ変換し、専用cacheへ保存する。
EXP_ROOT=/home/maru/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e
PYTHON="$EXP_ROOT/.venv/bin/python"
PRECOMPUTE="$EXP_ROOT/scripts/precompute_features.py"
BASE_MODEL=$(cat "$EXP_ROOT/base-model.path")
PREPARED="$EXP_ROOT/data/prepared/v2"
FEATURES="$EXP_ROOT/data/features/v2"
WORKERS=${WORKERS:-8}

if [[ -e "$PREPARED/train-featured.jsonl" || -e "$PREPARED/val-200-featured.jsonl" ]]; then
  printf 'feature manifest already exists under %s\n' "$PREPARED" >&2
  exit 2
fi

"$PYTHON" "$PRECOMPUTE" \
  --input-file "$PREPARED/train.jsonl" \
  --output-file "$PREPARED/train-featured.jsonl" \
  --cache-dir "$FEATURES/train" \
  --model-path "$BASE_MODEL" \
  --workers "$WORKERS"

"$PYTHON" "$PRECOMPUTE" \
  --input-file "$PREPARED/val-200.jsonl" \
  --output-file "$PREPARED/val-200-featured.jsonl" \
  --cache-dir "$FEATURES/val-200" \
  --model-path "$BASE_MODEL" \
  --workers "$WORKERS"
