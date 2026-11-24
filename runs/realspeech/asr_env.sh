# 既存ASRの実行環境を読み取り専用で使う。
REAL="$HOME/voiceime-work-real"
ASR="$HOME/voiceime-work-asr/r3-multiasr-train-20261123"
ASR_VENV="$HOME/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv"
ASR_PY="$ASR_VENV/bin/python"
export PYTHONPATH="$ASR/main-code/src:$ASR/scripts:$ASR_VENV/lib/python3.12/site-packages:$HOME/voiceime-work-qwenasr/Qwen3-ASR"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export XDG_CACHE_HOME="$REAL/cache" HF_HOME="$REAL/cache/huggingface"
