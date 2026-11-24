#!/bin/bash
# 用語集の第2版の評価をまとめて実行する（手元のMac、本体のmainで）。
set -euo pipefail
cd /Users/marutyan/PrivateDev/voiceIME
S=/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/metal-v2gloss
R=runs/v2gloss
mkdir -p $R
M=data/dev-user/manifest.jsonl
FMT=models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit
V1=data/text/glossary.jsonl
V2=data/text/glossary-v2.jsonl
EX=data/text/glossary-v2-excluded.txt
# 10秒おきに負荷を記録する
( while true; do echo "$(date '+%F %T') gpu=$(ioreg -r -d 1 -w 0 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | cut -d= -f2) $(sysctl -n vm.loadavg) swap=$(sysctl -n vm.swapusage | awk '{print $6}') top=$(ps -Ao pcpu,comm -r | sed -n 2,4p | awk '{printf "%s:%s;", $1, $2}')"; sleep 10; done ) > $R/load-during.log &
SAMPLER=$!
trap "kill $SAMPLER" EXIT

asr() { # label glossary max_terms max_chars min_score [exclude]
  local label=$1 g=$2 t=$3 c=$4 s=$5; shift 5
  echo "== ASR $label $(date '+%T')"
  uv run python $S/run_variant.py --label $label --max-terms $t --max-chars $c --min-score $s -- \
    --manifest $M --system haas-ja-v1.0-speechcpp-q8_0 --glossary-file $g "$@" --out $R/asr-$label.jsonl
}
fmt() { # label glossary [exclude]
  local label=$1 g=$2; shift 2
  echo "== FMT $label $(date '+%T')"
  uv run python -m voiceime.formatter.run --manifest $M --asr-run $R/asr-$label.jsonl --model $FMT \
    --system $label+sft2-qwen --out $R/e2e-$label+sft2-qwen.jsonl --prefix-cache --glossary $g "$@"
}
asr v1-t16-s75 $V1 16 240 75
asr v2-t16-s75 $V2 16 240 75 --exclude-terms $EX
asr v2-t8-s75  $V2 8 120 75 --exclude-terms $EX
asr v2-t16-s90 $V2 16 240 90 --exclude-terms $EX
asr v2-t8-s90  $V2 8 120 90 --exclude-terms $EX
asr v2-t16-s100 $V2 16 240 100 --exclude-terms $EX
fmt v1-t16-s75 $V1
for l in v2-t16-s75 v2-t8-s75 v2-t16-s90 v2-t8-s90 v2-t16-s100; do fmt $l $V2 --exclude-terms $EX; done
echo "== done $(date '+%T')"
