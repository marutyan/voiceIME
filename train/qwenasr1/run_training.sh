#!/usr/bin/env bash
set -u

# 学習とcheckpointは、この実験専用directoryの中だけに保存する。
EXP_ROOT=/home/maru/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e
PYTHON="$EXP_ROOT/.venv/bin/python"
TRAINER_SCRIPT=${TRAINER_SCRIPT:-$EXP_ROOT/scripts/qwen3_asr_sft.py}
RUN_NAME=${1:?run name is required}
TRAIN_FILE=${2:?train file is required}
EVAL_FILE=${3:?eval file is required}
OUTPUT_DIR=${4:?output directory is required}
BATCH_SIZE=${5:?batch size is required}
GRAD_ACC=${6:?gradient accumulation is required}
SAVE_STEPS=${7:?save interval is required}
SAVE_TOTAL_LIMIT=${8:?checkpoint limit is required}
GPU=${9:?physical GPU id is required}
MODEL_PATH=${10:?base model path is required}
LR=${LR:-2e-5}
EPOCHS=${EPOCHS:-1}
LOG_STEPS=${LOG_STEPS:-10}
WARMUP_RATIO=${WARMUP_RATIO:-0.02}
MAX_STEPS=${MAX_STEPS:--1}
MAX_GRAD_NORM=${MAX_GRAD_NORM:-1.0}
LR_SCHEDULER_TYPE=${LR_SCHEDULER_TYPE:-linear}
SAVE_STRATEGY=${SAVE_STRATEGY:-steps}
SAVE_FINAL_MODEL=${SAVE_FINAL_MODEL:-1}
NUM_WORKERS=${NUM_WORKERS:-2}
PREFETCH_FACTOR=${PREFETCH_FACTOR:-2}
FREEZE_AUDIO_ENCODER=${FREEZE_AUDIO_ENCODER:-0}

if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  printf 'invalid run name: %s\n' "$RUN_NAME" >&2
  exit 2
fi
case "$TRAIN_FILE" in "$EXP_ROOT"/data/prepared/*) ;; *) exit 2 ;; esac
case "$EVAL_FILE" in "$EXP_ROOT"/data/prepared/*) ;; *) exit 2 ;; esac
case "$OUTPUT_DIR" in "$EXP_ROOT"/output/*) ;; *) exit 2 ;; esac
case "$MODEL_PATH" in "$EXP_ROOT"/cache/*) ;; *) exit 2 ;; esac
case "$TRAINER_SCRIPT" in "$EXP_ROOT"/scripts/*) ;; *) exit 2 ;; esac
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'output directory already exists: %s\n' "$OUTPUT_DIR" >&2
  exit 2
fi

export CUDA_VISIBLE_DEVICES="$GPU"
export HF_HOME="$EXP_ROOT/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export HF_DATASETS_CACHE="$HF_HOME/datasets"
export XDG_CACHE_HOME="$EXP_ROOT/cache/xdg"
export UV_CACHE_DIR="$EXP_ROOT/cache/uv"
export TORCH_HOME="$EXP_ROOT/cache/torch"
export TMPDIR="$EXP_ROOT/tmp"
export CUDA_CACHE_PATH="$EXP_ROOT/cache/cuda"
export TRITON_CACHE_DIR="$EXP_ROOT/cache/triton"
export PYTHONPYCACHEPREFIX="$EXP_ROOT/cache/pycache"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_TELEMETRY=1

mkdir -p "$EXP_ROOT/logs" "$EXP_ROOT/cache/torch" "$EXP_ROOT/cache/pycache"
date -Is > "$EXP_ROOT/logs/$RUN_NAME.start"
date +%s > "$EXP_ROOT/logs/$RUN_NAME.start_epoch"
printf 'run=%s physical_gpu=%s\n' "$RUN_NAME" "$GPU"

"$PYTHON" "$TRAINER_SCRIPT" \
  --model_path "$MODEL_PATH" \
  --train_file "$TRAIN_FILE" \
  --eval_file "$EVAL_FILE" \
  --output_dir "$OUTPUT_DIR" \
  --batch_size "$BATCH_SIZE" \
  --grad_acc "$GRAD_ACC" \
  --lr "$LR" \
  --epochs "$EPOCHS" \
  --log_steps "$LOG_STEPS" \
  --lr_scheduler_type "$LR_SCHEDULER_TYPE" \
  --warmup_ratio "$WARMUP_RATIO" \
  --max_steps "$MAX_STEPS" \
  --max_grad_norm "$MAX_GRAD_NORM" \
  --save_final_model "$SAVE_FINAL_MODEL" \
  --freeze_audio_encoder "$FREEZE_AUDIO_ENCODER" \
  --save_strategy "$SAVE_STRATEGY" \
  --save_steps "$SAVE_STEPS" \
  --save_total_limit "$SAVE_TOTAL_LIMIT" \
  --num_workers "$NUM_WORKERS" \
  --pin_memory 1 \
  --persistent_workers 1 \
  --prefetch_factor "$PREFETCH_FACTOR"
STATUS=$?

date -Is > "$EXP_ROOT/logs/$RUN_NAME.end"
date +%s > "$EXP_ROOT/logs/$RUN_NAME.end_epoch"
printf '%s\n' "$STATUS" > "$EXP_ROOT/logs/$RUN_NAME.exit"
exit "$STATUS"
