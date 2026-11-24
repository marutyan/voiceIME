#!/bin/bash
# 課題1：本人の読み上げ50件（manifestの先頭50行がdev-user-s000〜s049）を、各ASRのヒント無しの1回目で1つずつ順に書き起こす。
# 遅延と負荷は`voiceime.asr.run`がそのまま記録する（各発話の直前のGPU使用率・負荷、前後の上位process）。
# 実行場所：手元のMac、リポジトリの直下で `bash runs/multiasr-metal/scripts/run_single.sh`
set -euo pipefail
cd /Users/marutyan/PrivateDev/voiceIME
# 新しい重みを取りに行かないよう、Hugging Faceはcacheだけを使う。
export HF_HUB_OFFLINE=1
OUT=runs/multiasr-metal/single
MODELS=(
  haas-ja-v1.0-speechcpp-q8_0
  qwen3-asr-0.6b-bf16 qwen3-asr-0.6b-8bit qwen3-asr-0.6b-4bit
  qwen3-asr-1.7b-bf16 qwen3-asr-1.7b-8bit qwen3-asr-1.7b-4bit
  whisper-large-v3-turbo whisper-large-v3-turbo-q8 whisper-large-v3-turbo-q4
)
for model in "${MODELS[@]}"; do
  echo "== $model $(date +%H:%M:%S)"
  uv run python -m voiceime.asr.run --manifest data/dev-user/manifest.jsonl --system "$model" \
    --decode greedy --limit 50 --warmup 2 --out "$OUT/$model.jsonl"
done
echo "== done $(date +%H:%M:%S)"
