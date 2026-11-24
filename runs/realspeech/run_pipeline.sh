#!/usr/bin/env bash
# facultyで取得済み音声を順にASR、教師文作成、学習、評価へ渡す。
set -euo pipefail
REAL="$HOME/voiceime-work-real"
QUEUE="$HOME/voiceime-queue"
cd "$REAL"
export PYTHONPATH="$REAL/source/src" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
cpu_python="$HOME/voiceime-work-pubdata/.venv/bin/python"

# 書き終えた実験用ランチャーを、キューが読む場所へ一度だけ置く。
submit() {
  local name="$1" script="$2"
  if compgen -G "$QUEUE/*/$name.sh" >/dev/null; then
    return
  fi
  cp "scripts/$script.sh" "scripts/$name.sh"
  chmod +x "scripts/$name.sh"
  mv "scripts/$name.sh" "$QUEUE/pending/"
  printf '%s キュー登録 %s\n' "$(date -Is)" "$name"
}

# 成功したジョブだけを次の処理の入力にする。
wait_job() {
  local name="$1"
  while [[ ! -e "$QUEUE/done/$name.util" ]]; do
    if [[ -e "$QUEUE/failed/$name.util" ]]; then
      printf '%s キュー失敗 %s\n' "$(date -Is)" "$name" >&2
      return 1
    fi
    sleep 60
  done
  cat "$QUEUE/done/$name.util"
}

# pub-evalは、学習用音声の取得と学習を待たずに独立して進める。
(
  submit 81-real-pub-eval asr_job
  wait_job 81-real-pub-eval
  "$cpu_python" scripts/prepare.py pub-eval
  submit 82-real-rsi-eval formatter_job
  wait_job 82-real-rsi-eval
  "$cpu_python" scripts/score.py RSI-0.8B
) &
pub_pid=$!

asr_pids=()
for shard in 00 01 02; do
  (
    "$cpu_python" scripts/prepare.py asr --shard "$((10#$shard))"
    submit "81-real-asr-$shard" asr_job
    wait_job "81-real-asr-$shard"
  ) &
  asr_pids+=("$!")
done
for pid in "${asr_pids[@]}"; do
  wait "$pid"
done
"$cpu_python" scripts/prepare.py extraction
"$cpu_python" scripts/prepare.py teacher
"$cpu_python" scripts/prepare.py verify
submit 82-real-teacher formatter_job
wait_job 82-real-teacher
"$cpu_python" scripts/prepare.py training
submit 83-real-train formatter_job
wait_job 83-real-train
wait "$pub_pid"
submit 84-real-eval formatter_job
wait_job 84-real-eval
"$cpu_python" scripts/score.py REAL-0.8B
"$cpu_python" scripts/score.py RSI-0.8B
if nvidia-smi -i 1,2,3 --query-compute-apps=process_name --format=csv,noheader | grep -F 'voiceime-real-'; then
  printf '実験のGPUプロセスが残っています\n' >&2
  exit 1
fi
printf '%s 全評価完了\n' "$(date -Is)"
