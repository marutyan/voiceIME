#!/bin/bash
# facultyで、このプロジェクトのGPUの処理を順番待ちで実行する常駐役。
# エージェントが考えたり確認したりしている間もGPUが空かないよう、空いたGPUへ次の処理を間を置かずに渡す。
#
# 使い方：
#   処理は実行できるシェルスクリプトとして ~/voiceime-queue/pending/ に置く。
#   ファイル名は <優先度2桁>-<名前>.sh（例：10-fr3-train.sh）。数字の小さいものから実行する。
#   スクリプトの中では CUDA_VISIBLE_DEVICES がこの常駐役により設定済み（1枚）。自分で変えない。
#   結果は ~/voiceime-queue/done/（終了コード0）か failed/ に、ログ（.log）と使用率の要約（.util）と一緒に移る。
#
# 守ること：GPU0（他人が使用）は使わない。他のプロセスが載っているGPUには割り当てない（相乗りしない）。
# 1枚に1つの処理だけを割り当てる。止めるときは ~/voiceime-queue/STOP を作る（実行中の処理は最後まで走る）。
set -u
Q="$HOME/voiceime-queue"
mkdir -p "$Q"/{pending,running,done,failed}
# このプロジェクトで使ってよいGPU（GPU0は他人が使っている）。
GPUS=(1 2 3)
declare -A JOB_PID JOB_NAME

gpu_busy() {
  # GPU上に何かの計算プロセス（他人、他の担当の直接実行を含む）があれば使用中とみなす。
  local uuid
  uuid=$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader | awk -F', ' -v g="$1" '$1==g{print $2}')
  nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$uuid"
}

start_job() {
  local g=$1 f=$2 name
  name=$(basename "$f" .sh)
  mv "$f" "$Q/running/$name.sh"
  (
    cd "$Q/running" || exit 1
    start=$(date +%s)
    # 30秒ごとにこのGPUの使用率を記録し、終了後に平均を書く。
    ( while true; do nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i "$g" >> "$name.utilraw"; sleep 30; done ) &
    sampler=$!
    CUDA_VISIBLE_DEVICES=$g bash "$name.sh" > "$name.log" 2>&1
    rc=$?
    kill $sampler 2>/dev/null
    avg=$(awk '{s+=$1;n++} END{if(n) printf "%.1f", s/n; else print "NA"}' "$name.utilraw" 2>/dev/null)
    echo "gpu=$g rc=$rc seconds=$(( $(date +%s) - start )) mean_util=$avg samples=$(wc -l < "$name.utilraw" 2>/dev/null)" > "$name.util"
    dest=$([ $rc -eq 0 ] && echo done || echo failed)
    mv "$name.sh" "$name.log" "$name.util" "$Q/$dest/" 2>/dev/null
    rm -f "$name.utilraw"
    echo "$(date '+%F %T') $name gpu=$g rc=$rc mean_util=$avg" >> "$Q/history.log"
  ) &
  JOB_PID[$g]=$!
  JOB_NAME[$g]=$name
  echo "$(date '+%F %T') start $name on gpu=$g" >> "$Q/history.log"
}

while [ ! -e "$Q/STOP" ]; do
  for g in "${GPUS[@]}"; do
    pid=${JOB_PID[$g]:-}
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then continue; fi
    JOB_PID[$g]=""
    next=$(ls "$Q/pending"/*.sh 2>/dev/null | sort | head -n 1)
    [ -z "$next" ] && break
    gpu_busy "$g" && continue
    start_job "$g" "$next"
  done
  sleep 15
done
