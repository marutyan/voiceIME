#!/usr/bin/env bash
# dev-userの読み上げ50件で、PMと同じ方法（Haas two-passの実出力、指示文のKVキャッシュあり）で整形して出力を書く（作業ツリーの直下で実行）。
#   devuser_eval.sh <系の名前> <MLXのモデル>
set -euo pipefail
O=/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft1/devuser
uv run python -m voiceime.formatter.run \
  --manifest /private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-scripted.jsonl \
  --asr-run /Users/marutyan/PrivateDev/voiceIME/runs/asr-dev-user/haas-ja-v1.0-speechcpp-q8_0+twopass.jsonl \
  --glossary /Users/marutyan/PrivateDev/voiceIME/data/text/glossary.jsonl --model "$2" --prefix-cache --system "haas2p+$1" --out "$O/$1.jsonl" 2>&1 \
  | grep -E '"(format_latency_median_s|format_latency_p90_s|latency_median_s|peak_memory_gb|truncated)"'
