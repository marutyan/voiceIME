#!/bin/bash
# facultyで、このプロジェクトのプロセス（~/voiceime-work*）がGPUのVRAMを確保したまま
# 使用率0%の状態を20分続けたら止める。手元のMacがスリープや通信断で後片付けできない場合の保険。
# 他人のプロセスとGPU0には触れない。止めた記録は ~/voiceime-reaper.log に残す。
LIMIT=20
declare -A idle
while true; do
  while IFS=', ' read -r uuid pid mem; do
    [ -z "$pid" ] && continue
    owner=$(ps -o user= -p "$pid" 2>/dev/null | tr -d ' ')
    [ "$owner" != "$USER" ] && continue
    cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    case "$cmd" in *voiceime-work*|*VLLM*|*vllm*) ;; *) continue ;; esac
    idx=$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader | awk -F', ' -v u="$uuid" '$2==u{print $1}')
    [ "$idx" = 0 ] && continue
    util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i "$idx")
    if [ "${util:-0}" -lt 2 ]; then idle[$pid]=$(( ${idle[$pid]:-0} + 1 )); else idle[$pid]=0; fi
    if [ "${idle[$pid]}" -ge "$LIMIT" ]; then
      pgid=$(ps -o pgid= -p "$pid" | tr -d ' ')
      echo "$(date '+%F %T') kill pid=$pid pgid=$pgid gpu=$idx mem=$mem cmd=${cmd:0:150}" >> ~/voiceime-reaper.log
      kill -TERM -- -"$pgid" 2>/dev/null || kill -TERM "$pid"
      sleep 10; kill -KILL "$pid" 2>/dev/null
      idle[$pid]=0
    fi
  done < <(nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader)
  sleep 60
done
