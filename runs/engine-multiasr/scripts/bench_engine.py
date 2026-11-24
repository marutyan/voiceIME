"""音声入力エンジン（`python -m voiceime.engine`）のCLIを端から端まで計測するスクリプト。

`--aux-asr` 無し（既定）と有り（例：`qwen3-asr-0.6b-8bit`）を、1本ずつ順に実機Metal上で動かし、
キーを離してから整形後までの遅延（`total_latency_s`）、ASR遅延、整形遅延、
および `voiceime.eval.report` で評価できる JSONL（e2e / asr）と実行メタ情報を保存する。

実行場所：手元のMac（Metalが使える環境、リポジトリ直下）：
    HF_HUB_OFFLINE=1 uv run python runs/engine-multiasr/scripts/bench_engine.py --label baseline
    HF_HUB_OFFLINE=1 uv run python runs/engine-multiasr/scripts/bench_engine.py --aux-asr qwen3-asr-0.6b-8bit --label aux-qwen3-0.6b-8bit
    uv run python -m voiceime.eval.report \
        --manifest /private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-scripted-after.jsonl \
        --runs runs/engine-multiasr/baseline-e2e.jsonl runs/engine-multiasr/aux-qwen3-0.6b-8bit-e2e.jsonl \
               runs/engine-multiasr/baseline-asr.jsonl runs/engine-multiasr/aux-qwen3-0.6b-8bit-asr.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from voiceime.asr.run import git_commit, read_manifest, sample_load, top_processes
from voiceime.asr.systems import MODELS

# メイン作業ツリーの既定パス（worktree内にmodels/dataが無い場合でもそのまま参照できる）。
MAIN_REPO = Path("/Users/marutyan/PrivateDev/voiceIME")
DEFAULT_MANIFEST = Path(
    "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/"
    "3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-scripted-after.jsonl"
)
DEFAULT_FORMATTER = MAIN_REPO / "models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit"
DEFAULT_GLOSSARY = MAIN_REPO / "data/text/glossary.jsonl"
DEFAULT_ASR = "haas-ja-v1.0-speechcpp-q8_0"
DEFAULT_OUT_DIR = Path("runs/engine-multiasr")


def _send(proc: subprocess.Popen[str], message: dict) -> None:
    """エンジンの標準入力へJSON Linesの1件を送り、即座にフラッシュする。"""
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def _read_event(proc: subprocess.Popen[str], stderr_path: Path) -> dict:
    """エンジンの標準出力から次のJSONイベントを読む。EOFなら例外を出す。"""
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError(
            f"エンジンが予期せず終了しました（returncode={proc.poll()}, stderr={stderr_path}）"
        )
    return json.loads(line)


def _run_utterance(
    proc: subprocess.Popen[str],
    session_id: str,
    wav_path: Path,
    stderr_path: Path,
) -> dict:
    """1発話（start→segment→finish）を送り、resultイベントを返す。"""
    _send(proc, {"type": "start", "session_id": session_id})
    _send(proc, {"type": "segment", "session_id": session_id, "seq": 0, "wav_path": str(wav_path)})
    _send(proc, {"type": "finish", "session_id": session_id, "mode": "formatted"})
    while True:
        event = _read_event(proc, stderr_path)
        event_type = event.get("type")
        if event_type == "partial":
            continue
        if event_type == "result" and event.get("session_id") == session_id:
            return event
        raise RuntimeError(f"想定外のイベントを受け取りました: {event}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """計測対象のモデル・manifest・出力先を引数から読む。"""
    parser = argparse.ArgumentParser(description="voiceime.engineの端から端までの遅延と精度を測る")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--asr", default=DEFAULT_ASR, choices=sorted(MODELS))
    parser.add_argument("--aux-asr", default=None, choices=sorted(MODELS))
    parser.add_argument("--formatter", type=str, default=str(DEFAULT_FORMATTER))
    parser.add_argument("--formatter-input", default="text", choices=("text", "d"))
    parser.add_argument("--formatter-max-glossary", type=int, default=20)
    parser.add_argument("--glossary-alt-readings", type=Path, default=None)
    parser.add_argument("--glossary", type=Path, nargs="+", default=[DEFAULT_GLOSSARY])
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--label", default=None, help="出力ファイルとsystem名に使うラベル")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """エンジンを子プロセスで起動してmanifestの全発話を順に処理し、JSONLとmetaを保存する。"""
    args = parse_args(argv)
    label = args.label or (f"aux-{args.aux_asr}" if args.aux_asr else "baseline")
    records = read_manifest(args.manifest)
    manifest_dir = args.manifest.parent
    args.out_dir.mkdir(parents=True, exist_ok=True)

    e2e_path = args.out_dir / f"{label}-e2e.jsonl"
    asr_path = args.out_dir / f"{label}-asr.jsonl"
    history_path = args.out_dir / f"{label}.history.jsonl"
    stderr_path = args.out_dir / f"{label}.stderr.log"
    meta_path = args.out_dir / f"{label}.meta.json"
    if history_path.exists():
        history_path.unlink()

    command = [
        sys.executable,
        "-m",
        "voiceime.engine",
        "--asr",
        args.asr,
        "--formatter",
        args.formatter,
        "--glossary",
        *(str(path) for path in args.glossary),
        "--history",
        str(history_path),
    ]
    command += ["--aux-asr", args.aux_asr or "none"]
    command += ["--formatter-input", args.formatter_input]
    command += ["--formatter-max-glossary", str(args.formatter_max_glossary)]
    if args.glossary_alt_readings:
        command += ["--glossary-alt-readings", str(args.glossary_alt_readings)]

    # 重みの新規ダウンロードを防ぐため、子プロセスでも常にオフライン指定を強制する。
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    meta: dict = {
        "label": label,
        "command": command,
        "manifest": str(args.manifest),
        "n_records": len(records),
        "asr": args.asr,
        "aux_asr": args.aux_asr,
        "formatter": args.formatter,
        "glossary": [str(path) for path in args.glossary],
        "warmup": args.warmup,
        "git_commit": git_commit(),
        "machine": platform.platform(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "top_processes_before": top_processes(),
        "load_before_start": sample_load(),
    }

    e2e_rows: list[dict] = []
    asr_rows: list[dict] = []
    utterance_loads: list[dict] = []

    with open(stderr_path, "w", encoding="utf-8") as stderr_file:
        started = time.perf_counter()
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            env=env,
        )
        try:
            ready = _read_event(proc, stderr_path)
            if ready.get("type") != "ready":
                raise RuntimeError(f"ready前に想定外のイベントを受け取りました: {ready}")
            meta["ready_event"] = ready
            meta["startup_s"] = time.perf_counter() - started

            warm_wav = manifest_dir / records[0]["audio_path"]
            for i in range(args.warmup):
                _run_utterance(proc, f"warmup-{i}", warm_wav, stderr_path)

            for record in records:
                wav_path = manifest_dir / record["audio_path"]
                utterance_loads.append({"id": record["id"], **sample_load()})
                result = _run_utterance(proc, record["id"], wav_path, stderr_path)
                e2e_rows.append(
                    {
                        "id": record["id"],
                        "system": label,
                        "stage": "e2e",
                        "hyp": result["text"],
                        "latency_s": result["total_latency_s"],
                        "asr_latency_s": result["asr_latency_s"],
                        "format_latency_s": result["format_latency_s"],
                        "format_ok": result["format_ok"],
                        "raw_text": result["raw_text"],
                    }
                )
                asr_rows.append(
                    {
                        "id": record["id"],
                        "system": label,
                        "stage": "asr",
                        "hyp": result["raw_text"],
                        "latency_s": result["asr_latency_s"],
                    }
                )
            _send(proc, {"type": "shutdown"})
            proc.wait(timeout=30)
        except BaseException:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise

    with open(e2e_path, "w", encoding="utf-8") as out:
        for row in e2e_rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(asr_path, "w", encoding="utf-8") as out:
        for row in asr_rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    stderr_text = stderr_path.read_text(encoding="utf-8")
    aux_warning_count = stderr_text.count("補助ASRの")
    format_fallback_count = sum(1 for row in e2e_rows if not row["format_ok"])
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta["top_processes_after"] = top_processes()
    meta["format_fallback_count"] = format_fallback_count
    meta["aux_warning_count"] = aux_warning_count
    meta["utterance_loads"] = utterance_loads
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"{label}: {len(e2e_rows)}件完了（起動 {meta['startup_s']:.2f}s, "
        f"format_ok=False: {format_fallback_count}件, 補助ASR警告: {aux_warning_count}件）",
        flush=True,
    )


if __name__ == "__main__":
    main()
