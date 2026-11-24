#!/bin/bash
# facultyの学習出力（重みと途中経過の保存）を研究室のNASへ移し、facultyのディスクを空ける。
# facultyからNASへは直接届かないため、手元のMacで中継する（tarを流すだけで、Macのディスクには置かない）。
# 写した後に、ファイルの一覧と大きさがfacultyとNASで一致することを確かめてから、faculty側を消す。
#
# 使い方（手元のMacで実行）：move_to_nas.sh <facultyのホーム以下の相対パス> [keep-final]
#   keep-final を付けると、評価で使う最終の重み（final/）だけfacultyに残す。
set -euo pipefail
REL="$1"; KEEP="${2:-}"
NAS_HOST=user-udon
NAS_ROOT=/share/share/marutani15/voiceIME/faculty
SRC="\$HOME/$REL"
DST="$NAS_ROOT/$REL"

# ファイルごとの「大きさ 相対パス」を並べた一覧。両側で同じ文字列になれば、写しは揃っている。
LIST='find . -type f -exec stat -c "%s %n" {} + | LC_ALL=C sort'

# 直近3時間に書き換えがあれば、動いているジョブが使っているとみなして触らない。
if [ -n "$(ssh faculty "find $SRC -type f -mmin -180 | head -n 1")" ]; then
  echo "SKIP(使用中の可能性) $REL"; exit 0
fi
ssh "$NAS_HOST" "mkdir -p '$DST'"
ssh faculty "cd $SRC && tar cf - ." | ssh "$NAS_HOST" "cd '$DST' && tar xf -"
A=$(ssh faculty "cd $SRC && $LIST" | md5)
B=$(ssh "$NAS_HOST" "cd '$DST' && $LIST" | md5)
if [ "$A" != "$B" ]; then echo "MISMATCH $REL（faculty側は消さない）"; exit 1; fi
if [ "$KEEP" = keep-final ]; then
  ssh faculty "cd $SRC && find . -mindepth 1 -maxdepth 1 ! -name final ! -name '*.json' -exec rm -rf {} +"
else
  ssh faculty "rm -rf $SRC"
fi
echo "MOVED $REL $(date '+%F %T')"
