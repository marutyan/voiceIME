#!/bin/bash
# 課題2：多言語ASRごとに、Haasのtwo-passとの順の実行・同時の実行と整形までの時間を測る（`parallel_pipeline.py`）。
# 実行場所：手元のMac、リポジトリの直下で `bash runs/multiasr-metal/scripts/run_parallel.sh`
set -euo pipefail
cd /Users/marutyan/PrivateDev/voiceIME
export HF_HUB_OFFLINE=1
MODELS=(qwen3-asr-0.6b-8bit qwen3-asr-0.6b-4bit qwen3-asr-1.7b-4bit qwen3-asr-1.7b-8bit whisper-large-v3-turbo-q8 whisper-large-v3-turbo)
for model in "${MODELS[@]}"; do
  [ -s "runs/multiasr-metal/parallel/$model.meta.json" ] && continue
  echo "== $model $(date +%H:%M:%S)"
  timeout 1800 uv run python runs/multiasr-metal/scripts/parallel_pipeline.py --multi "$model"
done
echo "== done $(date +%H:%M:%S)"
