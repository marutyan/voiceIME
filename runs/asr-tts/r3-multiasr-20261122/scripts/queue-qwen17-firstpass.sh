#!/usr/bin/env bash
set -euo pipefail
ASR=/home/maru/voiceime-work-asr
ROOT=$ASR/r3-multiasr-20261122
QWEN=/home/maru/voiceime-work-qwenasr/Qwen3-ASR
PY=/home/maru/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv/bin/voiceime-r3multi-qwen17-firstpass
if [[ -z "${CUDA_VISIBLE_DEVICES:-}" || "$CUDA_VISIBLE_DEVICES" == *,* || "$CUDA_VISIBLE_DEVICES" == "0" ]]; then
  echo "queueからGPU1〜3のいずれか1枚が割り当てられていない: ${CUDA_VISIBLE_DEVICES:-unset}" >&2
  exit 2
fi
export PYTHONPATH="$ROOT/main-code/src:$QWEN${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1
exec "$PY" "$ROOT/scripts/multiasr_runner.py" run --model qwen17
