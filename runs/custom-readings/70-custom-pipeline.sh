#!/usr/bin/env bash
# facultyのキューが割り当てたGPU 1枚で評価と学習材料の準備を順番に行う。
set -euo pipefail
gpu="${CUDA_VISIBLE_DEVICES:?キューからGPUを割り当ててください}"
[[ "$gpu" =~ ^[1-3]$ ]] || exit 2
uuid=$(nvidia-smi -i "$gpu" --query-gpu=uuid --format=csv,noheader)
nvidia-smi -i "$gpu" --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
occupied=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader)
if grep -Fxq "$uuid" <<< "$occupied"; then
    echo "割り当てられたGPUに別の計算プロセスがあります" >&2
    exit 2
fi

work="$HOME/voiceime-work-custom"
tts="$HOME/voiceime-work-tts"
fr3="$HOME/voiceime-work-fr3"
qwen="$HOME/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv/bin/python"
formatter="$fr3/kernels-venv/bin/python"
title_site="$HOME/voiceime-work/.venv/lib/python3.12/site-packages"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export PYTHONPATH="$work/code/src:$work/code/datagen/text"
cd "$work"

# 元のIrodori・Qwen TTSを順に読み込み、同じGPUを交互に使う。
run_tts() {
    local name="$1" out="$work/tts/$1"
    local tts_args=(--input "$work/$name-input.jsonl" --out "$out")
    if [[ ! -s "$out/manifest.jsonl" ]]; then
        mkdir -p "$out"
        export HF_HOME="$tts/cache/huggingface" HF_HUB_CACHE="$tts/cache/huggingface/hub"
        export PATH="$tts/tools/sox/bin:$PATH" TMPDIR="$tts/tmp"
        for engine in ja multi; do
            if [[ "$engine" = ja ]]; then
                tts_python="$tts/Irodori-TTS/.venv/bin/python"
                tts_path="$tts/datagen/tts:$tts/Irodori-TTS"
            else
                tts_python="$tts/venv-qwen/bin/python"
                tts_path="$tts/datagen/tts"
            fi
            PYTHONPATH="$tts_path" "$tts_python" "$work/voiceime-custom-tts.py" run \
                --engine "$engine" "${tts_args[@]}" --voices "$tts/datagen/tts/voices.json" \
                --voice-dir "$tts/voices" --batch-size 16 --seed 0 --retries 4
        done
        PYTHONPATH="$tts/datagen/tts:$tts/Irodori-TTS" "$tts/Irodori-TTS/.venv/bin/python" \
            "$work/voiceime-custom-tts.py" merge "${tts_args[@]}"
    fi
}

# 利用するPython環境の本体を保って、起動後にASRのプロセス名を設定する。
run_asr() {
    "$qwen" -c '
import runpy, sys
site, script, mode = sys.argv[1:]
sys.path.append(site)
from setproctitle import setproctitle
sys.path.pop()
setproctitle("voiceime-custom-asr")
sys.argv = [script, mode]
runpy.run_path(script, run_name="__main__")
' "$title_site" "$work/recognize.py" "$1"
}

if [[ ! -s evaluation-summary.json ]]; then
    if [[ ! -s eval-plan.json ]]; then
        python3 prepare.py eval
    fi
    for name in val-custom novel-custom; do
        if [[ -s "$name-input.jsonl" ]]; then
            run_tts "$name"
            if [[ -s "tts/$name/manifest.jsonl" ]]; then
                run_asr "$name"
            fi
        fi
    done
    PYTHONHOME="$HOME/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu" \
    PYTHONPATH="$PYTHONPATH:$fr3/python-deps:$fr3/kernels-venv/lib/python3.12/site-packages:$HOME/voiceime-work-f2b/.venv/lib/python3.12/site-packages:$title_site" \
        "$formatter" evaluate.py
fi

if [[ ! -s train-summary.json ]]; then
    if [[ ! -s train-plan.json ]]; then
        python3 prepare.py train
    fi
    if [[ -s train-custom-input.jsonl ]]; then
        run_tts train-custom
        if [[ -s tts/train-custom/manifest.jsonl ]]; then
            run_asr train-custom
        fi
    fi
    run_asr material
fi
nvidia-smi -i "$gpu" --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
