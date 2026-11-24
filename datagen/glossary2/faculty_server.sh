#!/usr/bin/env bash
# GPUサーバ faculty（H100 96GB）で教師LLM（Gemma 4 31B-it、bf16）のvLLMサーバーを起動する。
# 実行場所：faculty の ~/voiceime-work（faculty_setup.sh で .venv を作った後）。
# 使い方：GPUS=1,2,3 bash faculty_server.sh   （使う直前に nvidia-smi で空きを確かめ、他人のGPUを含めない）
# GPUごとに別のvLLMを立てるデータ並列にする（31Bはbf16で1枚に載るため、テンソル並列より速い）。
# クライアント（datagen/text/colab_client.py）は port 8000 へ送るため、vLLM内蔵のデータ並列（--data-parallel-size）で1つの口にまとめる。
# bf16の重み（約62GB）のままではKVキャッシュが1枚あたり約2.6万トークンしか取れず、同時に8件ほどしか処理できなかったため、
# 重みをFP8へ動的に量子化し（v1の教師と同じ）、KVキャッシュもFP8にして同時に処理できる件数を増やす。
# 2026-11-21の生成では、見直し1回目の937件と候補の2回目の512件はbf16の重みとKVキャッシュで、残りはFP8で処理した。
set -euo pipefail
: "${GPUS:?GPUS（例：1,2,3）を指定する}"
cd ~/voiceime-work
export HF_HOME="$HOME/voiceime-work/hf"
# facultyにはnvccが無く、FlashInferのサンプラーは初回にカーネルをJITでビルドしようとして失敗するため、vLLM標準のサンプラーを使う。
export VLLM_USE_FLASHINFER_SAMPLER=0
N_GPUS=$(echo "$GPUS" | tr ',' '\n' | wc -l)

CUDA_VISIBLE_DEVICES="$GPUS" nohup .venv/bin/vllm serve google/gemma-4-31B-it \
  --served-model-name teacher \
  --dtype bfloat16 \
  --quantization fp8 \
  --kv-cache-dtype fp8 \
  --data-parallel-size "$N_GPUS" \
  --max-model-len 12288 \
  --max-num-seqs 256 \
  --gpu-memory-utilization 0.94 \
  --limit-mm-per-prompt '{"image": 0, "audio": 0}' \
  --enable-prefix-caching \
  --port 8000 > vllm_server.log 2>&1 < /dev/null &
echo "started vllm server pid=$! gpus=$GPUS"
