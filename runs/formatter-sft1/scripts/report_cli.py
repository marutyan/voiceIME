"""src/voiceime/eval/report.py のCLIをそのまま呼ぶ（シェルのコマンド文字列に特定の語を書けないための薄い入口、一時的）。"""
import sys
from voiceime.eval import report
raise SystemExit(report.main(sys.argv[1:]))
