#!/usr/bin/env bash
# facultyのCPU側で段階間の検証を行い、残りのGPU処理はキューへ登録する。
set -euo pipefail

ASR="$HOME/voiceime-work-asr/r3-multiasr-train-20261123"
TTS="$HOME/voiceime-work-tts"
TTS_OUT="$TTS/outputs/r3-audio-topup-20261123"
SCRIPTS="$ASR/scripts/topup44971"
QUEUE="$HOME/voiceime-queue"
PIPELINE="$HOME/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv/bin/voiceime-r3audio-asr-pipeline"
TTS_PYTHON="$TTS/Irodori-TTS/.venv/bin/python"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# 終了ファイルと使用率が揃うまで待ち、失敗時は次の段階に入らない。
wait_jobs() {
  while :; do
    local finished=0 job
    for job in "$@"; do
      if [[ -f "$QUEUE/failed/$job.util" ]]; then
        tail -n 20 "$QUEUE/failed/$job.log" >&2
        return 1
      fi
      if [[ -f "$QUEUE/done/$job.util" ]]; then
        finished=$((finished + 1))
      fi
    done
    if (( finished == $# )); then return; fi
    sleep 60
  done
}

# 入力が揃った番号を、キューの担当と優先順位を保って登録する。
submit_asr() {
  local shard="$1" leaf temp state
  printf -v leaf '90-r3audio-asr-topup44971-shard-%02d.sh' "$shard"
  for state in done failed running pending; do
    if [[ -e "$QUEUE/$state/$leaf" ]]; then return; fi
  done
  temp=$(mktemp "$QUEUE/.r3audio-XXXXXX")
  {
    echo '#!/usr/bin/env bash'
    printf 'exec -a voiceime-r3audio-asr-launcher /bin/bash %q %q\n' "$SCRIPTS/queue_asr_shard.sh" "$shard"
  } >"$temp"
  bash -n "$temp"
  chmod 700 "$temp"
  mv -T "$temp" "$QUEUE/pending/$leaf"
}

case "${1:?preview or remaining required}" in
  preview)
    wait_jobs 90-r3audio-asr-topup44971-shard-{00,01,02}
    export PYTHONPATH="$ASR/main-code-topup-20261123/src:$SCRIPTS"
    summary="$ASR/outputs/preview-topup44971-summary.json"
    if [[ ! -s "$summary" ]]; then
      "$PIPELINE" "$SCRIPTS/topup_pipeline.py" publish-preview >"$summary.$$.tmp"
      mv -T "$summary.$$.tmp" "$summary"
    fi
    python3 "$SCRIPTS/update_fr3_readme.py" preview
    ;;
  remaining)
    wait_jobs 80-r3audio-tts-rescue-topup44971-shard-{00,02} "${@:2}"
    date --iso-8601=seconds
    missing_arg=()
    if [[ -n "${TOPUP_CONFIRMED_MISSING:-}" ]]; then
      missing_arg=(--confirmed-missing "$TOPUP_CONFIRMED_MISSING")
    fi
    PYTHONPATH="$TTS/datagen/tts:$TTS/Irodori-TTS" "$TTS_PYTHON" "$SCRIPTS/aggregate_tts_topup.py" \
      --work "$TTS_OUT" --inputs "$TTS/inputs/r3-audio-topup44971-20261123" \
      --prep-metadata "$TTS_OUT/preparation.json" "${missing_arg[@]}"
    export PYTHONPATH="$ASR/main-code-topup-20261123/src:$SCRIPTS"
    "$PIPELINE" "$SCRIPTS/topup_pipeline.py" prepare remaining
    for shard in 3 4 5; do submit_asr "$shard"; done
    ;;
  final)
    wait_jobs 90-r3audio-asr-topup44971-shard-{00,01,02,03,04,05}
    date --iso-8601=seconds
    export PYTHONPATH="$ASR/main-code-topup-20261123/src:$SCRIPTS"
    "$PIPELINE" "$SCRIPTS/topup_pipeline.py" finalize
    count=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["topup_rows"])' "$TTS_OUT/generation-metadata.json")
    python3 "$SCRIPTS/update_fr3_readme.py" final --metadata "$ASR/outputs/metadata-topup$count.json"
    ;;
  *) echo "unknown stage" >&2; exit 2 ;;
esac
