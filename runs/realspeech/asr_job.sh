#!/usr/bin/env bash
set -euo pipefail
source "$HOME/voiceime-work-real/scripts/asr_env.sh"
gpu="${CUDA_VISIBLE_DEVICES:?キューからGPUの割当が必要}"
[[ "$gpu" =~ ^[1-3]$ ]]
nvidia-smi -i "$gpu" --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
case "${0##*/}" in
  81-real-pub-eval.sh)
    exec -a voiceime-real-pub-eval "$ASR_PY" -S "$REAL/scripts/asr.py" \
      "$HOME/voiceime-work-pubdata/final-manifest/pub-eval.jsonl" "$REAL/asr/pub-eval" --dataset pub-eval
    ;;
  81-real-asr-*.sh)
    shard="${0##*-}"
    shard="${shard%.sh}"
    exec -a "voiceime-real-asr-$shard" "$ASR_PY" -S "$REAL/scripts/asr.py" \
      "$REAL/asr-inputs/shard-$shard.jsonl" "$REAL/asr/train-$shard" --dataset train --shard "$((10#$shard))"
    ;;
  *) exit 2 ;;
esac
