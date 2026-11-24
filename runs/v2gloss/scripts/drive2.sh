#!/bin/bash
# 前の担当が止まった後の続き：用語集の第2版の5条件の整形だけを実行する（手元のMac、本体のmain）。
set -euo pipefail
cd /Users/marutyan/PrivateDev/voiceIME
R=runs/v2gloss
M=data/dev-user/manifest.jsonl
FMT=models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit
V2=data/text/glossary-v2.jsonl
EX=data/text/glossary-v2-excluded.txt
echo "# --- 再開（整形の残り5条件） $(date '+%F %T') ---" >> $R/load-during.log
( while true; do echo "$(date '+%F %T') gpu=$(ioreg -r -d 1 -w 0 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | cut -d= -f2) $(sysctl -n vm.loadavg) swap=$(sysctl -n vm.swapusage | awk '{print $6}') top=$(ps -Ao pcpu,comm -r | sed -n 2,4p | awk '{printf "%s:%s;", $1, $2}')"; sleep 10; done ) >> $R/load-during.log &
SAMPLER=$!
trap "kill $SAMPLER" EXIT
rm -f $R/e2e-v2-t16-s75+sft2-qwen.jsonl
for l in v2-t16-s75 v2-t8-s75 v2-t16-s90 v2-t8-s90 v2-t16-s100; do
  echo "== FMT $l $(date '+%T')"
  uv run python -m voiceime.formatter.run --manifest $M --asr-run $R/asr-$l.jsonl --model $FMT \
    --system $l+sft2-qwen --out $R/e2e-$l+sft2-qwen.jsonl --prefix-cache --glossary $V2 --exclude-terms $EX
done
echo "== done $(date '+%T')"
