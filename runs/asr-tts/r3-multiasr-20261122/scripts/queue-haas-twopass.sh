#!/usr/bin/env bash
set -euo pipefail
ASR=/home/maru/voiceime-work-asr
ROOT=$ASR/r3-multiasr-20261122
PYTHON=$ASR/.venv/bin/python
RUNNER=$ASR/.venv/bin/voiceime-r3multi-haas-twopass
if [[ -z "${CUDA_VISIBLE_DEVICES:-}" || "$CUDA_VISIBLE_DEVICES" == *,* || "$CUDA_VISIBLE_DEVICES" == "0" ]]; then
  echo "queueからGPU1〜3のいずれか1枚が割り当てられていない: ${CUDA_VISIBLE_DEVICES:-unset}" >&2
  exit 2
fi
export PYTHONPATH="$ROOT/main-code/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
BEST_MODEL=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["model_key"])' "$ROOT/outputs/best-model.json")
exec "$RUNNER" "$ROOT/scripts/multiasr_runner.py" twopass --best-model "$BEST_MODEL" --workers 18 --threads 3
