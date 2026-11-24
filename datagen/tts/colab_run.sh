#!/bin/bash
# 手元のMacで実行する。ColabのGPUで参照音声と合成音声を作り、出力を少しずつ手元へ持ち帰る。
# 途中で止まった場合（手元のスクリプト、ColabのVMのどちらでも）は、同じ引数で再実行すると続きから作る。
# 手元に持ち帰った parts/*.jsonl をColabへ送り直し、記録済みの行を飛ばすため。
#
# 使い方: datagen/tts/colab_run.sh <入力JSONL> <作業用の出力先（手元）> [入力に split が無いときの値]
# 環境変数:
#   COLAB_CONFIG  colab CLI のセッション状態ファイル（担当ごとに分ける）
#   SESSION       セッション名（既定 tts-gen）
#   GPU           既定 L4
#   BATCH_SIZE    一括生成の件数（既定 16）
#   POLL_SEC      持ち帰りの間隔（秒、既定 300）
#   VOICE_DIR     参照音声の置き場所（既定 <出力先>/voices）。本番ではpilotで作った声を指定する
#   SPLIT_OUT     指定すると、最後に <SPLIT_OUT>/<split>/ へ集合ごとのmanifestと音声を書く
#   RUN_NAME      Colab上の作業場所の名前（既定 出力先のフォルダ名）。実行ごとに分け、別の実行の記録を混ぜない
#   KEEP_SESSION  1 なら正常終了の後もセッションを止めない（異常終了では必ず止める）
#   COLAB_TIMEOUT colab CLI の1回の呼び出しの上限（秒、既定 180）。CLIが接続の段階で止まることがあるため
#   MAX_MIN       開始からの上限時間（分、既定 480）。超えたら持ち帰ってセッションを止める。費用の上限から決める
#   STALL_MIN     記録が増えない時間の上限（分、既定 30）。超えたら停滞とみなして持ち帰り、セッションを止める
#   MAX_FAILS     Colabの呼び出しが続けて失敗してよい回数（既定 6）。超えたらセッションを止める
set -euo pipefail

INPUT=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
mkdir -p "$2"
OUT=$(cd "$2" && pwd)
DEFAULT_SPLIT=${3:-}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
SESSION=${SESSION:-tts-gen}
GPU=${GPU:-L4}
BATCH_SIZE=${BATCH_SIZE:-16}
POLL_SEC=${POLL_SEC:-300}
VOICE_DIR=${VOICE_DIR:-$OUT/voices}
RUN_NAME=${RUN_NAME:-$(basename "$OUT")}
MAX_MIN=${MAX_MIN:-480}
STALL_MIN=${STALL_MIN:-30}
MAX_FAILS=${MAX_FAILS:-6}
# colab CLI は接続の段階で戻らなくなることがあるため、timeout があれば上限を付けて呼ぶ。
if command -v timeout > /dev/null; then
  COLAB=(timeout "${COLAB_TIMEOUT:-180}" colab ${COLAB_CONFIG:+--config "$COLAB_CONFIG"})
else
  echo "timeout コマンドが無い。colab CLI が止まったときに戻れないため中止する（brew install coreutils）" >&2
  exit 1
fi
R=/content/tts            # Colab上の作業場所（参照音声とコードは実行間で共有する）
RR=$R/runs/$RUN_NAME      # この実行の入力、記録、音声、状態
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
SPLIT_ARG=${DEFAULT_SPLIT:+--default-split $DEFAULT_SPLIT}

# Colab上でシェルのコマンドを実行し、出力を表示する。
remote() {
  local q
  q=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1")
  printf '%s\n' "import subprocess; r = subprocess.run($q, shell=True, capture_output=True, timeout=120); print(r.stdout.decode(errors='replace')[-4000:]); print(r.stderr.decode(errors='replace')[-2000:])" \
    | "${COLAB[@]}" exec -s "$SESSION" 2>/dev/null
}

# 記録（parts）とログを持ち帰り、記録にあるのに手元に無い音声と参照音声だけを取ってくる。
# 時刻ではなく手元の不足分で決めるため、どこで止まっても取りこぼさない。
sync_back() {
  remote "cd $RR/out && tar czf $RR/sync_meta.tgz parts logs env 2>/dev/null; true" > /dev/null || return 1
  "${COLAB[@]}" download -s "$SESSION" "$RR/sync_meta.tgz" "$WORK/sync_meta.tgz" > /dev/null 2>&1 || return 1
  tar xzf "$WORK/sync_meta.tgz" -C "$OUT"
  python3 - "$OUT" "$VOICE_DIR" "$HERE/voices.json" > "$WORK/need.txt" <<'PY'
import json, pathlib, sys
out, vdir, vjson = map(pathlib.Path, sys.argv[1:4])
for part in sorted((out / "parts").glob("*.jsonl")):
    if part.name.endswith(".failed.jsonl"):
        continue
    for line in part.read_text().splitlines():
        try:
            i = json.loads(line)["manifest"]["id"]
        except (ValueError, KeyError):
            continue
        if not (out / "audio" / f"{i}.wav").exists():
            print(f"runs/RUN/out/audio/{i}.wav")
for v in json.loads(vjson.read_text()):
    if not (vdir / f"{v['speaker']}.wav").exists():
        print(f"voices/{v['speaker']}.wav")
PY
  sed -i '' "s|^runs/RUN/|runs/$RUN_NAME/|" "$WORK/need.txt"
  if [ -s "$WORK/need.txt" ]; then
    "${COLAB[@]}" upload -s "$SESSION" "$WORK/need.txt" "$R/need.txt" > /dev/null 2>&1 || return 1
    remote "cd $R && while read f; do [ -f \"\$f\" ] && echo \"\$f\"; done < need.txt > need_ok.txt; tar czf sync_files.tgz -T need_ok.txt" > /dev/null || return 1
    "${COLAB[@]}" download -s "$SESSION" "$R/sync_files.tgz" "$WORK/sync_files.tgz" > /dev/null 2>&1 || return 1
    rm -rf "$WORK/x" && mkdir -p "$WORK/x" "$OUT/audio" "$VOICE_DIR"
    tar xzf "$WORK/sync_files.tgz" -C "$WORK/x"
    [ -d "$WORK/x/runs/$RUN_NAME/out/audio" ] && find "$WORK/x/runs/$RUN_NAME/out/audio" -name '*.wav' -exec mv {} "$OUT/audio/" \;
    [ -d "$WORK/x/voices" ] && find "$WORK/x/voices" -name '*.wav' -exec mv {} "$VOICE_DIR/" \;
  fi
  echo "[$(date +%H:%M:%S)] 持ち帰り: 音声 $(find "$OUT/audio" -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')件"
}

# セッションを止める。止められたかを sessions で確かめ、残っていれば知らせる。
stop_session() {
  "${COLAB[@]}" stop -s "$SESSION" || true
  if "${COLAB[@]}" sessions 2>&1 | grep -q "^\[$SESSION\]"; then
    echo "警告: セッション $SESSION が残っている。手で colab stop を実行する" >&2
  fi
}

# 異常時は、持ち帰れるものを持ち帰ってからセッションを止めて終える（課金が続くのを防ぐため）。
abort_run() {
  echo "中止: $1" >&2
  sync_back || true
  stop_session
  exit 1
}

# 手元に持ち帰った記録の行数（成功と捨てた行の両方）。停滞の判定に使う。
progress_count() {
  { cat "$OUT"/parts/*.jsonl 2>/dev/null || true; } | wc -l | tr -d ' '
}

# SYNC_ONLY=1 なら、既存のセッションから記録と音声を一度だけ持ち帰って終える（GPUを替える前の回収用）。
if [ "${SYNC_ONLY:-0}" = 1 ]; then
  sync_back
  exit $?
fi

# 1. セッションを用意する（既にあれば使う）。
if ! "${COLAB[@]}" sessions 2>&1 | grep -q "^\[$SESSION\]"; then
  "${COLAB[@]}" new -s "$SESSION" --gpu "$GPU" || abort_run "セッションを作れなかった"
fi
T0=$(date +%s)

# 前回の生成がまだColab上で動いていれば、送り直しと起動を飛ばして持ち帰りだけを続ける。
JOB_STATE=$(remote "pgrep -f 'bash $RR/[j]ob.sh' > /dev/null && echo JOB_RUNNING || echo JOB_IDLE" || true)
if echo "$JOB_STATE" | grep -q JOB_RUNNING; then
  echo "Colab上で生成が動作中のため、持ち帰りだけを続ける"
elif ! echo "$JOB_STATE" | grep -q JOB_IDLE; then
  # 確認できないまま起動すると生成が二重に動くおそれがあるため、起動しない。
  abort_run "Colab上の生成の状態を確認できなかった"
else
  # 2. コード、入力、既存の参照音声と記録（再開用）をまとめて送る。
  mkdir -p "$WORK/up/runs/$RUN_NAME/code" "$WORK/up/runs/$RUN_NAME/out/parts" "$WORK/up/voices"
  cp "$HERE"/*.py "$HERE"/*.sh "$HERE/voices.json" "$WORK/up/runs/$RUN_NAME/code/"
  cp "$INPUT" "$WORK/up/runs/$RUN_NAME/input.jsonl"
  [ -d "$OUT/parts" ] && cp "$OUT"/parts/*.jsonl "$WORK/up/runs/$RUN_NAME/out/parts/" 2>/dev/null || true
  [ -d "$VOICE_DIR" ] && cp "$VOICE_DIR"/tts-voice-*.wav "$WORK/up/voices/" 2>/dev/null || true
  COPYFILE_DISABLE=1 tar --no-xattrs -czf "$WORK/up.tgz" -C "$WORK/up" .
  "${COLAB[@]}" upload -s "$SESSION" "$WORK/up.tgz" /content/tts_up.tgz > /dev/null || abort_run "送信に失敗した"
  remote "mkdir -p $R && tar xzf /content/tts_up.tgz -C $R && echo UP_OK" | grep -q UP_OK || abort_run "展開に失敗した"

  # 3. Colab上で、環境の準備、参照音声の作成、二つのTTSでの生成を裏で動かす。
  #    二つのTTSは同じGPUへ同時に載せる（L4の24GBに収まり、合計の処理が速くなるため）。
  cat > "$WORK/job.sh" <<EOF
#!/bin/bash
set -uo pipefail
mkdir -p $RR/out/logs $RR/out/env
cd $RR/code
bash setup_colab.sh >> $RR/out/logs/setup.log 2>&1 || { echo JOB_FAIL setup > $RR/status; exit 1; }
uv pip freeze --python /content/Irodori-TTS/.venv/bin/python > $RR/out/env/irodori.txt
uv pip freeze --python /content/venv-qwen/bin/python > $RR/out/env/qwen.txt
/content/venv-qwen/bin/python make_voices.py --voices voices.json --out $R/voices >> $RR/out/logs/voices.log 2>&1 || { echo JOB_FAIL voices > $RR/status; exit 1; }
COMMON="--input $RR/input.jsonl --voices voices.json --voice-dir $R/voices --out $RR/out --batch-size $BATCH_SIZE $SPLIT_ARG"
PYTHONPATH=/content/Irodori-TTS /content/Irodori-TTS/.venv/bin/python synthesize.py run --engine ja \$COMMON >> $RR/out/logs/ja.log 2>&1 &
P1=\$!
/content/venv-qwen/bin/python synthesize.py run --engine multi \$COMMON >> $RR/out/logs/multi.log 2>&1 &
P2=\$!
wait \$P1; S1=\$?; wait \$P2; S2=\$?
[ \$S1 -eq 0 ] && [ \$S2 -eq 0 ] && echo JOB_DONE > $RR/status || echo "JOB_FAIL ja=\$S1 multi=\$S2" > $RR/status
EOF
  "${COLAB[@]}" upload -s "$SESSION" "$WORK/job.sh" "$RR/job.sh" > /dev/null || abort_run "送信に失敗した"
  remote "rm -f $RR/status; nohup bash $RR/job.sh > $RR/job.out 2>&1 & echo STARTED" | grep -q STARTED || abort_run "起動に失敗した"
  echo "Colabで生成を開始した（セッション ${SESSION}、作業場所 ${RR}）"
fi

# 4. 終わるまで、一定間隔で出力を持ち帰る。時間、停滞、呼び出しの失敗のいずれかが上限を超えたら止める。
FAILS=0
LAST_COUNT=$(progress_count)
LAST_CHANGE=$(date +%s)
while true; do
  sleep "$POLL_SEC"
  STATUS=$(remote "cat $RR/status 2>/dev/null; tail -n 1 $RR/out/logs/ja.log $RR/out/logs/multi.log 2>/dev/null; echo POLL_OK" || true)
  if echo "$STATUS" | grep -q POLL_OK && sync_back; then
    FAILS=0
  else
    FAILS=$((FAILS + 1))
    echo "[$(date +%H:%M:%S)] Colabの呼び出しに失敗した（${FAILS}回連続）"
    [ "$FAILS" -ge "$MAX_FAILS" ] && abort_run "Colabの呼び出しが${FAILS}回続けて失敗した"
  fi
  echo "$STATUS" | grep -E "^\[(ja|multi)\]" | tail -2 || true
  if echo "$STATUS" | grep -q "JOB_DONE\|JOB_FAIL"; then
    echo "$STATUS" | grep "JOB_"
    break
  fi
  NOW=$(date +%s)
  COUNT=$(progress_count)
  if [ "$COUNT" != "$LAST_COUNT" ]; then
    LAST_COUNT=$COUNT
    LAST_CHANGE=$NOW
  elif [ $((NOW - LAST_CHANGE)) -ge $((STALL_MIN * 60)) ]; then
    abort_run "記録が${STALL_MIN}分増えていない"
  fi
  [ $((NOW - T0)) -ge $((MAX_MIN * 60)) ] && abort_run "${MAX_MIN}分を超えた"
done

# 5. 手元でmanifestをまとめ、セッションを止める。
uv run --project "$REPO" python "$HERE/synthesize.py" merge --input "$INPUT" --out "$OUT" $SPLIT_ARG \
  ${SPLIT_OUT:+--split-out "$SPLIT_OUT"}
echo "Colabの使用時間: $(( ($(date +%s) - T0) / 60 ))分"
if [ "${KEEP_SESSION:-0}" != 1 ] || ! echo "$STATUS" | grep -q JOB_DONE; then
  stop_session
fi
echo "$STATUS" | grep -q JOB_DONE
