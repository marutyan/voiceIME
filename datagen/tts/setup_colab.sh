#!/bin/bash
# Colab上で実行する。二つのTTSを別々の仮想環境へ入れ、重みを先に取得する。
# Irodori-TTSとQwen3-TTSは依存関係（transformers、torchの版）が異なるため、環境を分ける。
# 版は比較と試験生成（2026-11）に使ったものへ固定する。
set -euo pipefail

IRODORI_COMMIT=f01c08cd40c0afa62a862439a5de12f6dcf62054
QWEN_TTS_VERSION=0.1.1
TORCH_INDEX=https://download.pytorch.org/whl/cu128

if [ ! -d /content/Irodori-TTS ]; then
  git clone https://github.com/Aratako/Irodori-TTS.git /content/Irodori-TTS
fi
git -C /content/Irodori-TTS checkout -q "$IRODORI_COMMIT"
(cd /content/Irodori-TTS && uv sync --extra cu128)

if [ ! -x /content/venv-qwen/bin/python ]; then
  uv venv /content/venv-qwen --python 3.12
fi
# Colabでは VIRTUAL_ENV が効かずシステムのPythonへ入るため、--python で入れ先を明示する。
uv pip install --python /content/venv-qwen/bin/python torch==2.11.0 torchaudio==2.11.0 --index-url "$TORCH_INDEX"
uv pip install --python /content/venv-qwen/bin/python "qwen-tts==$QWEN_TTS_VERSION" soundfile

for m in Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign Qwen/Qwen3-TTS-12Hz-1.7B-Base \
         Aratako/Irodori-TTS-v4.1-Small Aratako/Semantic-DACVAE-Japanese-32dim; do
  uvx --from huggingface_hub hf download "$m" > /dev/null
done
echo SETUP_OK
