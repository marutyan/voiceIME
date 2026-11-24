"""発話の長さとASRの時間（encoderと全体）の関係を描く。Whisperのencoderが長さによらず一定かを確かめる。

元データ：runs/asr-latency-recheck-dev-saya各系の`*.jsonl`（`details.encoder_s`と`latency_s`）とdev-sayの音声の長さ。
実行：uv run --with matplotlib --with soundfile python plot_latency_vs_duration.py <runs_dir> <out.png>
"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import soundfile as sf

plt.rcParams["font.family"] = "Hiragino Sans"
RUNS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
MANIFEST = Path("/Users/marutyan/PrivateDev/voiceIME/data/dev-say/manifest.jsonl")
# 描く系と表示名、色（Okabe-Itoの色覚に配慮した配色）。
SYSTEMS = [
    ("whisper-large-v3-turbo.greedy+glossary", "Whisper large-v3-turbo＋用語集 (MLX)", "#0072B2"),
    ("qwen3-asr-1.7b-8bit+glossary", "Qwen3-ASR 1.7B 8bit＋用語集 (MLX)", "#E69F00"),
    ("qwen3-asr-0.6b-8bit", "Qwen3-ASR 0.6B 8bit (MLX)", "#F0E442"),
    ("parakeet-tdt_ctc-0.6b-ja", "Parakeet TDT-CTC 0.6B ja (MLX)", "#D55E00"),
    ("haas-ja-v1.0-mlx", "Haas-ja-v1.0 (MLXへの移植, bf16)", "#009E73"),
    ("haas-ja-v1.0-speechcpp-q8_0+glossary", "Haas-ja-v1.0 Q8_0＋用語集 (speech.cpp)", "#CC79A7"),
]

records = [json.loads(line) for line in MANIFEST.read_text().splitlines()]
duration = {r["id"]: sf.info(str(MANIFEST.parent / r["audio_path"])).duration for r in records}

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharex=True)
for name, label, color in SYSTEMS:
    rows = [json.loads(line) for line in (RUNS / f"{name}.jsonl").read_text().splitlines()]
    xs = [duration[r["id"]] for r in rows]
    axes[1].scatter(xs, [r["latency_s"] for r in rows], s=14, color=color, label=label)
    if all("encoder_s" in r.get("details", {}) for r in rows):
        axes[0].scatter(xs, [r["details"]["encoder_s"] for r in rows], s=14, color=color, label=label)
for ax in axes:
    ax.axhline(0.4, color="gray", linestyle="--", linewidth=1)
    ax.set_xlabel("発話の長さ（秒）")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
axes[0].set_ylabel("encoderの時間（秒）")
axes[0].set_title("encoder：Whisperは長さによらず約0.6秒、他は長さに比例", fontsize=10)
axes[1].set_ylabel("ASR全体の遅延（秒）")
axes[1].set_title("ASR全体（破線は目安の0.4秒）", fontsize=10)
axes[1].legend(fontsize=7, loc="upper left")
fig.tight_layout()
fig.savefig(OUT, dpi=150)
print("saved", OUT)
