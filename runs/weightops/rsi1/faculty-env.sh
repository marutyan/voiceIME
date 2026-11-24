# facultyの学習・評価で条件Dと同じPython環境を使う。
WORK="$HOME/voiceime-work-wops"
FR3="$HOME/voiceime-work-fr3"
RSI="$WORK/rsi1"
REPO="$RSI/source"
D_INPUT="$FR3/inputs/d-multiasr-20261123"
PY="$FR3/kernels-venv/bin/python"
export PYTHONHOME="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
export PYTHONPATH="$REPO/src:$REPO/train/formatter:$RSI:$WORK:$FR3/python-deps:$FR3/kernels-venv/lib/python3.12/site-packages:$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
export HF_HOME="$WORK/hf-cache" XDG_CACHE_HOME="$WORK/cache"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TORCH_HOME="$WORK/cache/torch" TRITON_CACHE_DIR="$WORK/cache/triton"
