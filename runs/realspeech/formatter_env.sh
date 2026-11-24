# facultyで条件DのPython環境を再利用し、書き込み先を実音声実験の領域に限る。
REAL="$HOME/voiceime-work-real"
FR3="$HOME/voiceime-work-fr3"
D_INPUT="$FR3/inputs/d-multiasr-20261123"
NOVEL="$FR3/inputs/test-novel-20261122"
WOPS="$HOME/voiceime-work-wops"
MULTIASR="$HOME/voiceime-work-asr/r3-multiasr-20261122/outputs"
RSI="$WOPS/outputs/RSI-0.8B/best"
FIX="$WOPS/fix2"
SYNTHETIC="$FIX/data/train-fixed.jsonl"
AUGMENTATION="$FIX/data/augmentation-fixed.jsonl"
PUB_EVAL="$HOME/voiceime-work-pubdata/final-manifest/pub-eval.jsonl"
CODE="$REAL/source/train/formatter"
PY="$FR3/kernels-venv/bin/python"
export PYTHONHOME="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu"
export PYTHONPATH="$REAL/source/src:$CODE:$REAL/scripts:$WOPS/rsi1:$FR3/python-deps:$FR3/kernels-venv/lib/python3.12/site-packages:$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME="$REAL/cache/huggingface" XDG_CACHE_HOME="$REAL/cache"
export TORCH_HOME="$REAL/cache/torch" TRITON_CACHE_DIR="$REAL/cache/triton"
