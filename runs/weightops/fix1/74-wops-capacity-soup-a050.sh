#!/usr/bin/env bash
# 基準soup-a050を、PMの容量評価と同じ一覧（上限20/32/48）で評価し、FIX・RSIと同じ表に並べる。
set -euo pipefail
exec bash "$HOME/voiceime-work-wops/fix1/capacity-eval.sh" soup-a050 "$HOME/voiceime-work-wops/outputs/soup-a050"
