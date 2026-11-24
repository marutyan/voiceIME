#!/usr/bin/env bash
# faculty上でColabと同じ固定版のTTS環境とモデル重みを用意する。
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WORK_DIR=$(cd "$HERE/../.." && pwd)
IRODORI_DIR="$WORK_DIR/Irodori-TTS"
QWEN_ENV="$WORK_DIR/venv-qwen"
HF_HOME="$WORK_DIR/cache/huggingface"
TORCH_INDEX=https://download.pytorch.org/whl/cu128
# Colab側と揃えるTTSの版。SoXだけはfacultyに無いため、作業場所内へ固定版を置く。
IRODORI_COMMIT=f01c08cd40c0afa62a862439a5de12f6dcf62054
QWEN_TTS_VERSION=0.1.1
SOX_VERSION=14.4.2
SOX_SHA256=b45f598643ffbd8e363ff24d61166ccec4836fea6d3888881b8df53e3bb55f6c

mkdir -p "$WORK_DIR/cache/uv" "$HF_HOME" "$WORK_DIR/voices" "$WORK_DIR/inputs" "$WORK_DIR/outputs" \
  "$WORK_DIR/tmp" "$WORK_DIR/sources" "$WORK_DIR/build" "$WORK_DIR/tools/sox"
export UV_CACHE_DIR="$WORK_DIR/cache/uv"
export HF_HOME
export HF_HUB_CACHE="$HF_HOME/hub"
export TMPDIR="$WORK_DIR/tmp"
SOX_PREFIX="$WORK_DIR/tools/sox"
SOX_ARCHIVE="$WORK_DIR/sources/sox-$SOX_VERSION.tar.gz"

command -v uv >/dev/null || { echo "uv が見つからない" >&2; exit 1; }

if [ ! -x "$SOX_PREFIX/bin/sox" ]; then
  if [ ! -f "$SOX_ARCHIVE" ]; then
    curl --fail --location --retry 2 --connect-timeout 5 --max-time 60 \
      --output "$SOX_ARCHIVE" "https://downloads.sourceforge.net/project/sox/sox/$SOX_VERSION/sox-$SOX_VERSION.tar.gz"
  fi
  printf '%s  %s\n' "$SOX_SHA256" "$SOX_ARCHIVE" | sha256sum --check -
  SOX_SOURCE="$WORK_DIR/build/sox-$SOX_VERSION"
  if [ ! -x "$SOX_SOURCE/configure" ]; then
    tar -xzf "$SOX_ARCHIVE" -C "$WORK_DIR/build"
  fi
  (
    cd "$SOX_SOURCE"
    ./configure --prefix="$SOX_PREFIX" --disable-shared
    make -j2
    make install
  )
fi
export PATH="$SOX_PREFIX/bin:$PATH"

if [ ! -d "$IRODORI_DIR/.git" ]; then
  if [ -e "$IRODORI_DIR" ]; then
    echo "$IRODORI_DIR はGitリポジトリではないため、上書きせず中止する" >&2
    exit 1
  fi
  git clone https://github.com/Aratako/Irodori-TTS.git "$IRODORI_DIR"
fi
if [ -n "$(git -C "$IRODORI_DIR" status --porcelain)" ]; then
  echo "Irodori-TTSに未コミットの変更があるため、上書きせず中止する" >&2
  exit 1
fi
git -C "$IRODORI_DIR" checkout -q "$IRODORI_COMMIT"
(cd "$IRODORI_DIR" && uv sync --extra cu128)

if [ ! -x "$QWEN_ENV/bin/python" ]; then
  uv venv "$QWEN_ENV" --python 3.12
fi
"$QWEN_ENV/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'
uv pip install --python "$QWEN_ENV/bin/python" torch==2.11.0 torchaudio==2.11.0 --index-url "$TORCH_INDEX"
uv pip install --python "$QWEN_ENV/bin/python" "qwen-tts==$QWEN_TTS_VERSION" soundfile

MODEL_REVISIONS="$WORK_DIR/model-revisions.tsv"
: > "$MODEL_REVISIONS"
while read -r model revision; do
  [ -n "$model" ] || continue
  uvx --from huggingface_hub hf download "$model" --revision "$revision" >/dev/null
  cache_name=$(printf '%s' "$model" | sed 's|/|--|g')
  repo_cache="$HF_HUB_CACHE/models--$cache_name"
  [ -d "$repo_cache/snapshots/$revision" ] || { echo "$model のsnapshotがない: $revision" >&2; exit 1; }
  mkdir -p "$repo_cache/refs"
  printf '%s' "$revision" > "$repo_cache/refs/main"
  printf '%s\t%s\n' "$model" "$revision" >> "$MODEL_REVISIONS"
done <<'MODEL_REVISIONS'
Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign 5ecdb67327fd37bb2e042aab12ff7391903235d3
Qwen/Qwen3-TTS-12Hz-1.7B-Base fd4b254389122332181a7c3db7f27e918eec64e3
Aratako/Irodori-TTS-v4.1-Small 2b28324dc263ed5e6638b3cf3dd94c82ead07b4b
Aratako/Semantic-DACVAE-Japanese-32dim 47376ee24834d7a05a48ebabfe3cde29b3c5e214
MODEL_REVISIONS

{
  printf 'irodori_commit\t%s\n' "$(git -C "$IRODORI_DIR" rev-parse HEAD)"
  printf 'qwen_tts\t%s\n' "$QWEN_TTS_VERSION"
  printf 'torch\t%s\n' "$("$QWEN_ENV/bin/python" -c 'import torch; print(torch.__version__)')"
  printf 'sox\t%s\n' "$("$SOX_PREFIX/bin/sox" --version)"
  printf 'uv\t%s\n' "$(uv --version)"
} > "$WORK_DIR/setup-versions.tsv"
uv pip freeze --python "$IRODORI_DIR/.venv/bin/python" > "$WORK_DIR/irodori-environment.txt"
uv pip freeze --python "$QWEN_ENV/bin/python" > "$WORK_DIR/qwen-environment.txt"

echo "SETUP_OK"
echo "環境: $IRODORI_DIR/.venv と $QWEN_ENV"
echo "SoX: $("$SOX_PREFIX/bin/sox" --version)"
echo "モデルのrevision: $MODEL_REVISIONS"
echo "参照音声: $WORK_DIR/voices（手元の data/pilot-tts/voices から30本を配置する）"
