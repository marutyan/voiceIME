#!/usr/bin/env bash
# 教師がGPUを返した後に次のジョブを登録し、接続が切れても順序を保つ。
set -euo pipefail
q="$HOME/voiceime-queue"
work="$HOME/voiceime-work-custom"
exec 9>"$work/sequence.lock"
flock -n 9

wait_job() {
    local name="$1"
    while [[ ! -f "$q/done/$name.util" && ! -f "$q/failed/$name.util" ]]; do
        sleep 15
    done
    if [[ -f "$q/failed/$name.util" ]]; then
        cat "$q/failed/$name.util" >&2
        return 1
    fi
    cat "$q/done/$name.util"
}

wait_job "${1:-70-custom-teacher}"
name="${2:-70-custom-pipeline}"
test -s "$work/glossary-custom-readings.jsonl"
test ! -e "$q/STOP"
if [[ ! -e "$q/pending/$name.sh" && ! -e "$q/running/$name.sh" &&
      ! -e "$q/done/$name.util" && ! -e "$q/failed/$name.util" ]]; then
    nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv
    install -m 755 "$work/70-custom-pipeline.sh" "$q/staging/$name.sh"
    mv "$q/staging/$name.sh" "$q/pending/$name.sh"
fi
status=0
wait_job "$name" || status=$?
nvidia-smi
if pgrep -af '^[^ ]*voiceime-custom-|^[^ ]*python[^ ]* [^ ]*voiceime-custom-' ; then
    echo "慣習読みジョブのプロセスが残っています" >&2
    exit 3
fi
exit "$status"
