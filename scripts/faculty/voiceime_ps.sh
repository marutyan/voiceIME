#!/bin/bash
# facultyで、このプロジェクトのGPUの処理をジョブ単位にまとめて一覧にする。
# workerを多数立てたジョブでも、GPUごと・プロセス名ごとに1行へ畳んで、何が動いているかを一目で分かるようにする。
#
# 使い方：~/voiceime-ps.sh（2秒ごとに更新するなら watch -n 2 ~/voiceime-ps.sh）
# プロセス名は担当が exec -a voiceime-<担当名>-<役割> で付けた名前（argsの先頭の語）で数える。
set -u
Q="$HOME/voiceime-queue"

echo "== GPU（使用率%、使用メモリMiB）"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader,nounits |
  awk -F', ' '{printf "GPU%s  util %3s%%  mem %6s MiB\n", $1, $2, $3}'

echo
echo "== GPU上のプロセス（GPUとプロセス名ごとにまとめる。自分以外のプロセスは他人として1行に数える）"
# GPUのuuidから番号への対応を作り、計算プロセスのpidごとにプロセス名を引いて数える。
declare -A IDX
while IFS=', ' read -r i u; do IDX[$u]=$i; done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader,nounits |
  while IFS=', ' read -r u pid mem; do
    owner=$(ps -o user= -p "$pid" 2>/dev/null)
    if [ "$owner" = "$USER" ]; then
      name=$(ps -o args= -p "$pid" | awk '{print $1}' | xargs basename)
    else
      name="(他人のプロセス)"
    fi
    echo "${IDX[$u]}|$name|$mem"
  done |
  awk -F'|' '{k="GPU" $1 "  " $2; n[k]++; m[k]+=$3} END{for (k in n) printf "%-50s x%-4d %7d MiB\n", k, n[k], m[k]}' | sort

echo
echo "== ジョブキュー"
echo "実行中: $(ls "$Q/running"/*.sh 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
echo "待ち  : $(ls "$Q/pending"/*.sh 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
echo "直近  :"; tail -n 3 "$Q/history.log" 2>/dev/null | sed 's/^/  /'
