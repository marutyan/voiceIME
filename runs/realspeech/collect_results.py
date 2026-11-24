#!/usr/bin/env python3
"""facultyの実験完了を待ち、集計・30例・結果表を手元へ保存する。"""

import json
import subprocess
from pathlib import Path

# 音声・重み・全行の推論結果にはアクセスせず、ここに挙げた実験集計だけを転送する。
REMOTE = r"""
import json
import subprocess
import time
from pathlib import Path

root = Path.home() / "voiceime-work-real"
log = root / "logs/pipeline-rsi.log"
pid = int((root / "logs/pipeline.pid").read_text())
queue = Path.home() / "voiceime-queue"
while "全評価完了" not in log.read_text():
    state = subprocess.run(["ps", "-p", str(pid), "-o", "stat=,args="], capture_output=True, text=True)
    if state.returncode or state.stdout.strip().startswith("Z") or "bash scripts/run_pipeline.sh" not in state.stdout:
        if "全評価完了" in log.read_text():
            break
        raise SystemExit(log.read_text())
    time.sleep(60)
processes = subprocess.check_output([
    "nvidia-smi", "-i", "1,2,3", "--query-compute-apps=process_name", "--format=csv,noheader",
], text=True)
assert "voiceime-real-" not in processes
for state in ("pending", "running"):
    assert not list((queue / state).glob("*-real-*.sh")), state
paths = {
    name: root / "stats" / name for name in (
        "extraction.json", "cer-filter.json", "targets.json", "examples.jsonl",
        "REAL-0.8B.json", "RSI-0.8B-eval.json", "REAL-0.8B-eval.json",
    )
}
paths["train-summary.json"] = root / "outputs/REAL-0.8B/train_summary.json"
files = {name: path.read_text() for name, path in paths.items()}
files["queue-summary.txt"] = "\n".join(
    f"{path.name}: {path.read_text().strip()}" for path in sorted((queue / "done").glob("*-real-*.util"))
) + "\n"
payload = json.dumps(files, ensure_ascii=False)
assert len(payload.encode()) < 1_000_000
print(payload)
"""


def render(files):
    """取得・除外内訳、比較結果、モデルの場所を一つの表題の下に記録する。"""
    audio = json.loads(files["extraction.json"])
    filt = json.loads(files["cer-filter.json"])
    gold = json.loads(files["targets.json"])
    mix = json.loads(files["REAL-0.8B.json"])
    train = json.loads(files["train-summary.json"])
    examples = [json.loads(line) for line in files["examples.jsonl"].splitlines()]
    assert len(examples) == min(30, gold["available_rows"])
    assert mix["real_rows"] == train["real_rows"]
    assert train["original_rows"] == mix["original_rows"] and train["swap_rows"] == mix["swap_rows"]
    rows = []
    for tag in ("RSI-0.8B", "REAL-0.8B"):
        values = json.loads(files[f"{tag}-eval.json"])
        for split in ("val", "test-novel", "pub-eval"):
            for mode, label in (("raw", "なし"), ("restore", "あり")):
                metrics = values[split][mode]
                cer, terms = metrics["cer"], metrics["terms"]
                rows.append(
                    f"| {tag} | {split} | {label} | {cer['rate']:.2%} | {cer['deletions']:,} | "
                    f"{terms['all_exact']:,}/{terms['all_total']:,} |"
                )
    return "\n".join([
        "## 最終結果",
        "",
        f"取得は {audio['valid']:,}/{audio['selected']:,} 区間、{audio['valid_videos']:,}動画、"
        f"WAV {audio['wav_bytes'] / 1e9:.2f} GB。取得できなかった区間は {audio['failed']:,} 件。",
        "",
        f"ASR後は {filt['kept']:,}/{filt['recognized']:,} 件を採用した。両方がCER 15%以下 "
        f"{filt['both_pass']:,} 件、Haasのみ {filt['haas_only']:,} 件、Qwenのみ {filt['qwen_only']:,} 件。"
        f"除外は両方が15%超 {filt['both_cer_above_15_percent']:,} 件、両方空 "
        f"{filt['both_asr_empty']:,} 件、正規化後の字幕が空 {filt['caption_empty_after_normalization']:,} 件。",
        "",
        f"教師文はRSI出力採用 {gold.get('rsi', 0):,} 件、ASRから句読点を移植 "
        f"{gold.get('punctuation_copied', 0):,} 件、字幕を保持 {gold.get('caption_unchanged', 0):,} 件。"
        f"英字の正解用語は {gold['english_term_occurrences']:,} 回。"
        f"字幕にないフィラー語形がASRにある区間は {gold['asr_extra_filler_form_rows']:,} 件。"
        "正解文の例は [examples.jsonl](../../runs/realspeech/examples.jsonl)。",
        "",
        f"合成 {mix['original_rows']:,} 行、差し替え {mix['swap_rows']:,} 行、"
        f"実音声 {mix['real_rows']:,} 行。実音声の比率は {mix['real_fraction']:.2%}。"
        f"最良はstep {train['best_step']:,}、最終はstep {train['last_step']:,}。",
        "",
        "| モデル | 集合 | 読みの復元 | CER | 削除 | 厳密用語正答 |",
        "| --- | --- | --- | ---: | ---: | ---: |",
        *rows,
        "",
        "pub-evalは同じ字幕を使った相対比較。本人50件はPMがMacで測る。",
        "",
        "評価した重みはfacultyの `~/voiceime-work-real/outputs/REAL-0.8B/best`。"
        "最後の重みは同じディレクトリの `final`。GPU1〜3に実験プロセスが残っていないことを確認した。",
        "",
    ])


def main():
    """ファイルの転送を一度で済ませ、検証に通った内容だけを記録する。"""
    destination = Path(__file__).resolve().parent
    docs = destination.parents[1] / "docs/experiments/2026-11-23-real-speech.md"
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ControlPath=none", "-o", "ServerAliveInterval=60",
         "faculty", "python3", "-"],
        input=REMOTE, capture_output=True, text=True,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    assert len(result.stdout.encode()) < 1_000_000
    files = json.loads(result.stdout)
    markdown = render(files)
    for name, content in files.items():
        assert "/" not in name and not name.startswith(".")
        (destination / name).write_text(content)
    prior = docs.read_text()
    # 集計を取り直しても、結果に追記した分析は保持する。
    if "\n## 最終結果\n" not in prior:
        docs.write_text(f"{prior.rstrip()}\n\n{markdown}")
    print(markdown)


if __name__ == "__main__":
    main()
