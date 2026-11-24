#!/usr/bin/env bash
set -euo pipefail

ASR=/home/maru/voiceime-work-asr
ROOT=$ASR/r3-multiasr-20261122
QWEN=/home/maru/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e
PY=$QWEN/.venv/bin/voiceime-r3multi-whisper-firstpass-cpu

export PYTHONPATH="$ROOT/main-code/src:/home/maru/voiceime-work-qwenasr/Qwen3-ASR${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=16 MKL_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16

exec "$PY" "$ROOT/scripts/multiasr_runner.py" run --model whisper --device cpu --cpu-threads 16
