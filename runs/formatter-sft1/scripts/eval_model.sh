#!/usr/bin/env bash
# 学習後のMLX 4bitモデルをval200で評価し、10秒の発話の整形時間を測る（作業ツリーの直下で実行）。
#   eval_model.sh <系の名前> <MLXのモデル>
set -euo pipefail
NAME=$1
MODEL=$2
S=/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/formatter
R=/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft1
G=/Users/marutyan/PrivateDev/voiceIME/data/text/glossary.jsonl
heavy() { ps -A -o %cpu=,command= | awk '$1 > 20 && $0 !~ /WindowServer|voiceime.formatter|latency-10s/ {printf "%s %s; ", $1, substr($2,1,70)}'; }
echo "before run: $(date +%H:%M:%S) $(heavy)" > "$R/$NAME.load.txt"
uv run python -m voiceime.formatter.run --manifest "$R/input-val200.jsonl" --asr-run "$R/val-asrsim.jsonl" \
  --glossary "$G" --model "$MODEL" --prefix-cache --system "$NAME" --out "$R/$NAME.jsonl" 2>&1 | grep -v Fetching | tail -14
echo "after run: $(date +%H:%M:%S) $(heavy)" >> "$R/$NAME.load.txt"
uv run python "$R/latency-10s-estimate.py" "$NAME" "$MODEL" "$G" 2>/dev/null | tail -1 > "$R/$NAME.latency10s.json"
echo "after latency: $(date +%H:%M:%S) $(heavy)" >> "$R/$NAME.load.txt"
cat "$R/$NAME.latency10s.json" "$R/$NAME.load.txt"
