#!/usr/bin/env bash
# 学習後の3モデルの10秒の発話の整形時間を、他の重い処理が止まるのを最大5分待ってから測り直す（作業ツリーの直下で実行）。
set -uo pipefail
R=/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft1
G=/Users/marutyan/PrivateDev/voiceIME/data/text/glossary.jsonl
OUT=$R/latency-10s-recheck.jsonl
: > "$OUT"
heavy() { ps -A -o %cpu=,command= | awk '$1 > 20 && $0 !~ /WindowServer|latency-10s/ {printf "%s %s; ", $1, substr($2,1,70)}'; }
for name in sft1-qwen3.5-0.8b-full sft1-lfm2.5-1.2b-jp-full sft1-gemma-4-e2b-lora; do
  q=0; t=0
  while [ $q -lt 3 ] && [ $t -lt 60 ]; do
    if [ -z "$(heavy)" ]; then q=$((q + 1)); else q=0; fi
    t=$((t + 1)); sleep 5
  done
  before="$(date +%H:%M:%S) $(heavy)"
  line=$(uv run python "$R/latency-10s-estimate.py" "$name" "/Users/marutyan/PrivateDev/voiceIME/models/formatter/$name/mlx-4bit" "$G" 2>/dev/null | tail -1)
  after="$(date +%H:%M:%S) $(heavy)"
  python3 -c "import json,sys; d=json.loads(sys.argv[1]); d['heavy_before']=sys.argv[2]; d['heavy_after']=sys.argv[3]; print(json.dumps(d, ensure_ascii=False))" "$line" "$before" "$after" >> "$OUT"
done
python3 -c "
import json
for l in open('$OUT'):
    d=json.loads(l); print(d['model'], d['cached_est_latency_10s_s'], d['full_est_latency_10s_s'], d['cached_decode_tps'], d['peak_memory_gb'], '|', d['heavy_before'][:90], '|', d['heavy_after'][:90])"
