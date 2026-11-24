#!/bin/bash
# 切り分け：ASRと整形の用語集の版を入れ替えた2条件（手元のMac、本体のmain）。
set -euo pipefail
cd /Users/marutyan/PrivateDev/voiceIME
R=runs/v2gloss
M=data/dev-user/manifest.jsonl
FMT=models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit
echo "# --- 切り分け（用語集の版の入れ替え） $(date '+%F %T') ---" >> $R/load-during.log
( while true; do echo "$(date '+%F %T') gpu=$(ioreg -r -d 1 -w 0 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | cut -d= -f2) $(sysctl -n vm.loadavg) swap=$(sysctl -n vm.swapusage | awk '{print $6}') top=$(ps -Ao pcpu,comm -r | sed -n 2,4p | awk '{printf "%s:%s;", $1, $2}')"; sleep 10; done ) >> $R/load-during.log &
SAMPLER=$!
trap "kill $SAMPLER" EXIT
echo "== FMT asr v1 / fmt v2 $(date '+%T')"
uv run python -m voiceime.formatter.run --manifest $M --asr-run $R/asr-v1-t16-s75.jsonl --model $FMT \
  --system v1-t16-s75+sft2-qwen-fmtv2 --out $R/e2e-v1-t16-s75+sft2-qwen-fmtv2.jsonl --prefix-cache \
  --glossary data/text/glossary-v2.jsonl --exclude-terms data/text/glossary-v2-excluded.txt
echo "== FMT asr v2 / fmt v1 $(date '+%T')"
uv run python -m voiceime.formatter.run --manifest $M --asr-run $R/asr-v2-t16-s75.jsonl --model $FMT \
  --system v2-t16-s75+sft2-qwen-fmtv1 --out $R/e2e-v2-t16-s75+sft2-qwen-fmtv1.jsonl --prefix-cache \
  --glossary data/text/glossary.jsonl
echo "== done $(date '+%T')"
