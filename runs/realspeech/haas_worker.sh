#!/usr/bin/env bash
# speech.cppをGPUキューの割当で起動する。
set -euo pipefail
exec -a voiceime-real-haas "$HOME/voiceime-work-asr/speech.cpp/build-cuda-toolkit/speech" "$@"
