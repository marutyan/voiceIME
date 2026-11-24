#!/usr/bin/env bash
# facultyのジョブキューで既存の教師モデルを起動し、用語集から別の読みを提案する。
set -euo pipefail
case "${CUDA_VISIBLE_DEVICES:-}" in
    1|2|3) ;;
    *) echo "キューからGPU1〜3のうち1枚を割り当ててください" >&2; exit 2 ;;
esac
gpu_uuid=$(nvidia-smi -i "$CUDA_VISIBLE_DEVICES" --query-gpu=uuid --format=csv,noheader)
occupied=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader)
if grep -Fxq "$gpu_uuid" <<< "$occupied"; then
    echo "割り当てられたGPUに別の計算プロセスがあります" >&2
    exit 2
fi

work="$HOME/voiceime-work-altread/20261124"
teacher="$HOME/voiceime-work"
dictionary="$HOME/voiceime-work-asr/data/glossary"
model="$teacher/hf/hub/models--google--gemma-4-31B-it/snapshots/842da3794eaa0b77d5f08bae87a17459d91ff475"
port=18385
cd "$work"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_PROCESS_NAME_PREFIX=voiceime-altread-teacher VLLM_NO_USAGE_STATS=1
export HF_HOME="$teacher/hf"
export VLLM_CACHE_ROOT="$work/vllm-cache"
export PYTHONDONTWRITEBYTECODE=1
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost

if [[ ! -s requests.jsonl ]]; then
    python3 teacher_requests.py --glossary "$dictionary/glossary.jsonl" "$dictionary/glossary-v2.jsonl" --output requests.jsonl
fi
if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    echo "教師モデル用のポートが使用中です" >&2
    exit 2
fi
setsid "$teacher/.venv/bin/python" -c '
import sys
from setproctitle import setproctitle
from vllm.entrypoints.cli.main import main
setproctitle("voiceime-altread-teacher")
sys.argv[0] = "vllm"
main()
' serve "$model" \
    --served-model-name altread-teacher --host 127.0.0.1 --port "$port" \
    --dtype bfloat16 --quantization fp8 --kv-cache-dtype fp8 \
    --max-model-len 4096 --max-num-seqs 96 --gpu-memory-utilization 0.9 \
    --limit-mm-per-prompt '{"image":0,"audio":0}' --enable-prefix-caching \
    > teacher-server.log 2>&1 &
server=$!
trap 'kill -TERM -- "-$server" 2>/dev/null || true; wait "$server" || true' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for ((attempt=0; attempt<180; attempt++)); do
    if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        break
    fi
    kill -0 "$server"
    sleep 2
done
curl -fsS "http://127.0.0.1:$port/health" >/dev/null
(
    exec "$teacher/.venv/bin/python" -c '
import asyncio
from pathlib import Path
from client import run
import sys
from setproctitle import setproctitle
setproctitle("voiceime-altread-client")
asyncio.run(run(Path("requests.jsonl"), Path("responses.jsonl"), sys.argv[1],
                "altread-teacher", concurrency=96, retries=2, timeout=240))
' "http://127.0.0.1:$port/v1"
)
