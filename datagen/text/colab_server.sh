#!/usr/bin/env bash
# Colab（A100 40GB 1枚）上で教師LLMのvLLMサーバーを起動する。
# 実行場所：Colab VMの上（手元から `colab exec` 経由で bash に渡す）。
# bf16の重み（約52GB）は40GBに載らないため、重みをFP8へ動的に量子化して載せる。
# 画像入力は使わないため、画像の入力枠を0にしてメモリを空ける。
# KVキャッシュはbf16のまま使う（A100はFP8のKVキャッシュに対応しない）。
set -euo pipefail

MODEL="${MODEL:-google/gemma-4-26B-A4B-it}"
LOG=/content/vllm_server.log

pip install -q "vllm==0.34.0" > /content/pip_install.log 2>&1

nohup vllm serve "$MODEL" \
  --served-model-name teacher \
  --quantization fp8 \
  --max-model-len 10240 \
  --max-num-seqs 256 \
  --gpu-memory-utilization 0.94 \
  --limit-mm-per-prompt '{"image": 0}' \
  --enable-prefix-caching \
  --port 8000 > "$LOG" 2>&1 &
echo "started vllm server pid=$!"
