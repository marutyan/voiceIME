"""音声の無い文章データ（val）の推論結果を、src/voiceime/eval/report.py の集計でまとめる（一時的、commitしない）。

report.py のCLIはmanifestの音声の長さを読むため、音声の無いvalでは使えない。集計の関数はそのまま使い、
音声の長さの代わりに`est_seconds`（文字数÷6の推定）を長さの区分に渡す。
使い方: python score_text.py <manifest> <out.json> <run.jsonl>...
"""
import json
import sys
from pathlib import Path

from voiceime.eval import report as R

manifest = Path(sys.argv[1])
out = Path(sys.argv[2])
rows = R._read_jsonl(manifest)
durations = {r["id"]: float(r["est_seconds"]) for r in rows}
results = []
for p in sys.argv[3:]:
    run_rows = R._read_jsonl(Path(p))
    results.append(R._evaluate_group(Path(p), run_rows[0]["system"], "e2e", run_rows, rows, durations))
print(R._markdown_table(results))
out.write_text(json.dumps({"manifest": str(manifest), "duration_source": "est_seconds", "results": results},
                          ensure_ascii=False, indent=2))
