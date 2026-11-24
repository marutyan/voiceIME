#!/usr/bin/env bash
# GPUサーバ faculty で教師LLMを動かす環境を ~/voiceime-work/.venv に作り、重みを取得する。
# 実行場所：faculty（ssh faculty の後）。ホームの他のディレクトリに触れないよう、HF_HOMEも作業場所の下に置く。
# facultyのNVIDIAドライバは570（CUDA 12.8まで）で、vLLM 0.33以降はCUDA 13版しか配布されないため、0.32.0のcu129版を使う。
# torchcodec（Gemma 4の音声・動画の前処理が読み込む）もCUDA 13版が入るため、cu129版に入れ替える。
set -euo pipefail
mkdir -p ~/voiceime-work
cd ~/voiceime-work
~/.local/bin/uv venv -q --python 3.12 .venv
~/.local/bin/uv pip install -q --python .venv/bin/python "vllm==0.32.0+cu129" openai \
  --extra-index-url https://wheels.vllm.ai/0.32.0/cu129 \
  --extra-index-url https://download.pytorch.org/whl/cu129 --index-strategy unsafe-best-match
~/.local/bin/uv pip install -q --python .venv/bin/python torchcodec \
  --index-url https://download.pytorch.org/whl/cu129 --reinstall-package torchcodec
HF_HOME="$HOME/voiceime-work/hf" .venv/bin/hf download google/gemma-4-31B-it
.venv/bin/python -c "import vllm, torch; print(vllm.__version__, torch.__version__, torch.version.cuda)"
