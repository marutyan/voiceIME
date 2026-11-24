#!/usr/bin/env bash
# 取得を再試行し、増えた区間だけを補充ASRへ渡す。
set -euo pipefail
REAL="$HOME/voiceime-work-real"
QUEUE="$HOME/voiceime-queue"
cd "$REAL"
export PYTHONPATH="$REAL/source/src" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
python="$HOME/voiceime-work-pubdata/.venv/bin/python"
"$python" scripts/recover_clips.py
"$python" scripts/prepare.py asr-recovery
if [[ -s asr-inputs/shard-03.jsonl ]]; then
  job=81-real-asr-03
  if ! compgen -G "$QUEUE/*/$job.sh" >/dev/null; then
    cp scripts/asr_job.sh "scripts/$job.sh"
    chmod +x "scripts/$job.sh"
    mv "scripts/$job.sh" "$QUEUE/pending/"
  fi
  until [[ -e "$QUEUE/done/$job.util" ]]; do
    if [[ -e "$QUEUE/failed/$job.util" ]]; then
      cat "$QUEUE/failed/$job.util" >&2
      exit 1
    fi
    sleep 60
  done
fi
date -Is > logs/recovery-complete
