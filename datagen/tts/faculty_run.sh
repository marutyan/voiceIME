#!/usr/bin/env bash
# faculty上で入力を分割し、選んだGPUごとにTTS生成を再開可能な形で並列実行する。
set -euo pipefail

# 引数と既定値を利用者が確認できる形式で表示する。
usage() {
  cat <<'EOF'
使い方（faculty上）:
  bash faculty_run.sh <入力JSONL> <出力先> <CUDA_VISIBLE_DEVICES> <GPUごとの並列worker数> [入力の既定split]

例:
  bash faculty_run.sh inputs/pilot-20.jsonl outputs/pilot-20 2 1 test-synth
  bash faculty_run.sh inputs/train.jsonl outputs/train-gpu2-3 2,3 1

環境変数:
  BATCH_SIZE  synthesize.pyへ渡す一括生成件数（既定16）
  SEED        声・TTS・速さ・抑揚の割当seed（既定0）
  VOICE_DIR   参照音声の場所（既定 ~/voiceime-work-tts/voices）
EOF
}

if [ "$#" -gt 0 ] && [ "$1" = --help ]; then
  usage
  exit 0
fi
if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then
  usage
  exit 2
fi

INPUT_ARG=$1
OUT_ARG=$2
GPU_LIST=$3
WORKERS_PER_GPU=$4
DEFAULT_SPLIT=${5:-}
BATCH_SIZE=${BATCH_SIZE:-16}
SEED=${SEED:-0}

HERE=$(cd "$(dirname "$0")" && pwd)
WORK_DIR=$(cd "$HERE/../.." && pwd -P)
IRODORI_DIR="$WORK_DIR/Irodori-TTS"
IRODORI_PYTHON="$IRODORI_DIR/.venv/bin/python"
QWEN_PYTHON="$WORK_DIR/venv-qwen/bin/python"
VOICE_DIR=${VOICE_DIR:-$WORK_DIR/voices}
HF_HOME="$WORK_DIR/cache/huggingface"
SOX_BIN="$WORK_DIR/tools/sox/bin/sox"
export HF_HOME
export HF_HUB_CACHE="$HF_HOME/hub"
export TMPDIR="$WORK_DIR/tmp"
export PATH="$WORK_DIR/tools/sox/bin:$PATH"

# エラーを標準エラーへ出し、生成前の段階で停止する。
die() { echo "エラー: $*" >&2; exit 1; }

[[ -f "$INPUT_ARG" ]] || die "入力JSONLがない: $INPUT_ARG"
INPUT=$(python3 - "$INPUT_ARG" "$WORK_DIR" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve(strict=True)
root = Path(sys.argv[2]).resolve()
if root not in path.parents:
    raise SystemExit("入力JSONLは ~/voiceime-work-tts/ の中に置く")
print(path)
PY
)
OUT=$(python3 - "$OUT_ARG" "$WORK_DIR" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
if not path.is_absolute():
    path = Path.cwd() / path
path = path.resolve()
root = Path(sys.argv[2]).resolve()
if path == root or root not in path.parents:
    raise SystemExit("出力先は ~/voiceime-work-tts/ の中に置く")
print(path)
PY
)
mkdir -p "$OUT"
VOICE_DIR=$(python3 - "$VOICE_DIR" "$WORK_DIR" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser().resolve(strict=True)
root = Path(sys.argv[2]).resolve()
if root not in path.parents:
    raise SystemExit("参照音声は ~/voiceime-work-tts/ の中に置く")
print(path)
PY
)
[[ "$WORKERS_PER_GPU" =~ ^[1-9][0-9]*$ ]] || die "GPUごとのworker数は正の整数にする"
[[ "$BATCH_SIZE" =~ ^[1-9][0-9]*$ ]] || die "BATCH_SIZEは正の整数にする"
[[ "$SEED" =~ ^-?[0-9]+$ ]] || die "SEEDは整数にする"
[[ "$GPU_LIST" =~ ^[0-9]+(,[0-9]+)*$ ]] || die "CUDA_VISIBLE_DEVICESはGPU番号をカンマ区切りで指定する"
case "$DEFAULT_SPLIT" in
  ""|train|val|test-synth) ;;
  *) die "既定splitはtrain、val、test-synthのいずれかにする" ;;
esac

IFS=, read -r -a GPU_IDS <<< "$GPU_LIST"
declare -A SEEN_GPUS=()
for gpu in "${GPU_IDS[@]}"; do
  [[ -z "${SEEN_GPUS[$gpu]:-}" ]] || die "GPU番号が重複している: $gpu"
  SEEN_GPUS[$gpu]=1
done

[[ -x "$IRODORI_PYTHON" ]] || die "Irodori-TTS環境がない。先にfaculty_setup.shを実行する"
[[ -x "$QWEN_PYTHON" ]] || die "Qwen環境がない。先にfaculty_setup.shを実行する"
[[ -x "$SOX_BIN" ]] || die "SoX環境がない。先にfaculty_setup.shを実行する"
[[ -f "$HF_HOME/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base/refs/main" ]] || die "Qwen3-TTSの重みがない。先にfaculty_setup.shを実行する"
[[ -f "$HF_HOME/hub/models--Aratako--Irodori-TTS-v4.1-Small/refs/main" ]] || die "Irodori-TTSの重みがない。先にfaculty_setup.shを実行する"

python3 - "$HERE/voices.json" "$VOICE_DIR" <<'PY'
import json
import sys
from pathlib import Path

voices_path, voice_dir = map(Path, sys.argv[1:])
voices = json.loads(voices_path.read_text())
missing = [voice_dir / f"{v['speaker']}.wav" for v in voices if not (voice_dir / f"{v['speaker']}.wav").is_file()]
if len(voices) != 30 or missing:
    details = ", ".join(str(path) for path in missing[:5])
    raise SystemExit(f"参照音声はvoices.jsonの30本が必要。不足: {len(missing)}本 {details}")
PY

WORKER_COUNT=$((${#GPU_IDS[@]} * WORKERS_PER_GPU))
INPUT_SHA=$(sha256sum "$INPUT" | awk '{print $1}')
CONFIG=$(printf 'input_sha256=%s\nworkers=%s\nbatch_size=%s\nseed=%s\ndefault_split=%s\n' \
  "$INPUT_SHA" "$WORKER_COUNT" "$BATCH_SIZE" "$SEED" "$DEFAULT_SPLIT")
CONFIG_PATH="$OUT/.faculty-run-config"
if [ -f "$CONFIG_PATH" ]; then
  cmp -s "$CONFIG_PATH" <(printf '%s' "$CONFIG") || die "この出力先は別の入力・並列数・batch size・seedで使われた。別の出力先を指定する"
elif [ -n "$(find "$OUT" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  die "出力先が空ではなく再開設定もない。既存データを上書きしないため別の出力先を指定する"
else
  printf '%s' "$CONFIG" > "$CONFIG_PATH"
fi

WORKERS_DIR="$OUT/workers"
mkdir -p "$WORKERS_DIR"
python3 - "$INPUT" "$WORKER_COUNT" "$WORKERS_DIR" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
count = int(sys.argv[2])
root = Path(sys.argv[3])
targets = [root / f"worker-{i:03d}" / "input.jsonl" for i in range(count)]
for target in targets:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("")
seen = set()
row_index = 0
for line in source.read_text().splitlines(keepends=True):
    if not line.strip():
        continue
    row = json.loads(line)
    row_id = row.get("id")
    if not row_id or row_id in seen:
        raise SystemExit(f"idがないか重複している: {row_id}")
    seen.add(row_id)
    with targets[row_index % count].open("a") as out:
        out.write(line if line.endswith("\n") else line + "\n")
    row_index += 1
if row_index == 0:
    raise SystemExit("入力JSONLに行がない")
print(f"入力{row_index}件を{count} workerへ分割した")
PY

DEFAULT_ARGS=()
if [ -n "$DEFAULT_SPLIT" ]; then DEFAULT_ARGS+=(--default-split "$DEFAULT_SPLIT"); fi
for ((i = 0; i < WORKER_COUNT; i++)); do
  worker=$(printf 'worker-%03d' "$i")
  mkdir -p "$WORKERS_DIR/$worker/out/logs"
done

echo "選択GPU: $GPU_LIST（各GPU $WORKERS_PER_GPU worker、合計 $WORKER_COUNT worker）"
echo "GPUの使用状況を確認する。選択GPUに他の計算プロセスや負荷があれば起動しない。"
nvidia-smi
python3 - "$GPU_LIST" <<'PY'
import csv
import subprocess
import sys

selected = set(sys.argv[1].split(","))
gpu_rows = subprocess.run(
    ["nvidia-smi", "--query-gpu=index,uuid,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
    check=True, text=True, capture_output=True,
).stdout
apps = subprocess.run(
    ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader,nounits"],
    check=True, text=True, capture_output=True,
).stdout
busy_uuids = set()
for row in csv.reader(apps.splitlines()):
    if len(row) >= 2 and row[0].strip() and "no running processes" not in row[0].lower():
        busy_uuids.add(row[0].strip())
found = set()
problems = []
for row in csv.reader(gpu_rows.splitlines()):
    if len(row) != 4:
        continue
    index, uuid, memory, utilization = (part.strip() for part in row)
    if index not in selected:
        continue
    found.add(index)
    try:
        memory_mib = int(memory)
        utilization_pct = int(utilization)
    except ValueError:
        problems.append(f"GPU{index}:状態を読めない")
        continue
    if uuid in busy_uuids or memory_mib > 512 or utilization_pct > 0:
        problems.append(f"GPU{index}:使用中（memory={memory_mib}MiB, utilization={utilization_pct}%）")
if found != selected:
    problems.append(f"指定GPUが見つからない: {','.join(sorted(selected - found))}")
if problems:
    raise SystemExit("選択GPUを使えない: " + "; ".join(problems))
print("選択GPUは空いている")
PY

PIDS=()
START_TIME=$(date +%s)
worker_index=0
for gpu in "${GPU_IDS[@]}"; do
  for ((slot = 0; slot < WORKERS_PER_GPU; slot++)); do
    worker=$(printf 'worker-%03d' "$worker_index")
    shard="$WORKERS_DIR/$worker/input.jsonl"
    worker_out="$WORKERS_DIR/$worker/out"
    if [ -s "$shard" ]; then
      CUDA_VISIBLE_DEVICES="$gpu" PYTHONPATH="$IRODORI_DIR:$HERE${PYTHONPATH:+:$PYTHONPATH}" \
        "$IRODORI_PYTHON" "$HERE/synthesize.py" run --engine ja --input "$shard" --out "$worker_out" \
        --voices "$HERE/voices.json" --voice-dir "$VOICE_DIR" --seed "$SEED" --batch-size "$BATCH_SIZE" \
        "${DEFAULT_ARGS[@]}" > "$worker_out/logs/ja.log" 2>&1 &
      PIDS+=("$!")
      CUDA_VISIBLE_DEVICES="$gpu" PYTHONPATH="$HERE" \
        "$QWEN_PYTHON" "$HERE/synthesize.py" run --engine multi --input "$shard" --out "$worker_out" \
        --voices "$HERE/voices.json" --voice-dir "$VOICE_DIR" --seed "$SEED" --batch-size "$BATCH_SIZE" \
        "${DEFAULT_ARGS[@]}" > "$worker_out/logs/multi.log" 2>&1 &
      PIDS+=("$!")
      echo "$worker: GPU$gpu 起動"
    fi
    worker_index=$((worker_index + 1))
  done
done

RUN_STATUS=0
for pid in "${PIDS[@]}"; do
  if wait "$pid"; then :; else RUN_STATUS=1; fi
done

mkdir -p "$OUT/parts" "$OUT/audio"
for worker_dir in "$WORKERS_DIR"/worker-*; do
  [ -d "$worker_dir/out/parts" ] || continue
  worker=$(basename "$worker_dir")
  for part in "$worker_dir"/out/parts/*.jsonl; do
    [ -f "$part" ] || continue
    cp "$part" "$OUT/parts/$worker-$(basename "$part")"
  done
  [ ! -d "$worker_dir/out/audio" ] || cp -a "$worker_dir/out/audio/." "$OUT/audio/"
done

PYTHONPATH="$IRODORI_DIR:$HERE" "$IRODORI_PYTHON" "$HERE/synthesize.py" merge \
  --input "$INPUT" --out "$OUT" "${DEFAULT_ARGS[@]}"
END_TIME=$(date +%s)
python3 - "$OUT/tts_meta.jsonl" "$((END_TIME - START_TIME))" <<'PY'
import json
import sys
from pathlib import Path

meta_path = Path(sys.argv[1])
elapsed = int(sys.argv[2])
audio_seconds = sum(json.loads(line)["duration_s"] for line in meta_path.read_text().splitlines() if line.strip())
if audio_seconds:
    print(f"WALL_SECONDS={elapsed} AUDIO_SECONDS={audio_seconds:.1f} RTF={elapsed / audio_seconds:.3f} "
          f"WALL_MIN_PER_AUDIO_HOUR={elapsed / audio_seconds * 60:.1f}")
else:
    print(f"WALL_SECONDS={elapsed} AUDIO_SECONDS=0")
PY

echo "生成プロセス終了後のGPU状態:"
nvidia-smi
[ "$RUN_STATUS" -eq 0 ] || die "一部workerが失敗した。出力先を変えずに同じ引数で再実行するとpartsから再開する"
