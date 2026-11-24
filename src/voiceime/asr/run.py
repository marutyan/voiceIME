"""manifestの全発話をASRの1候補で書き起こし、結果と遅延を`docs/PLAN.md`の推論結果の形式で保存する。

実行例（手元のMac、作業ツリーで）：
    uv run python -m voiceime.asr.run --manifest /Users/marutyan/PrivateDev/voiceIME/data/dev-say/manifest.jsonl \
        --system whisper-large-v3-turbo --decode greedy --glossary \
        --out /Users/marutyan/PrivateDev/voiceIME/runs/asr-baseline-dev-say/whisper-large-v3-turbo.greedy+glossary.jsonl

遅延は、音声を読み込み終えた時点から文字が返るまでの時間で、モデルの読み込みとwarm-upは含めない。
他の重い処理が同時に動くと遅延がぶれるため、各発話の直前にGPUの使用率とCPUの負荷を記録し、`<out>.meta.json`へ残す。
集計（中央値など）は評価の担当の`voiceime.eval`で行い、ここでは計算しない。
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import resource
import subprocess
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from voiceime.asr.base import Transcriber, Transcription, load_audio, terms_from_manifest
from voiceime.asr.systems import GLOSSARY_BACKENDS, MODELS, ModelSpec, asr_hint_format, build_transcriber
from voiceime.engine import transcribe_with_hints
from voiceime.formatter.glossary import exclude_glossary, load_glossary, load_term_list

# 結果の`stage`。ASR単体の出力であることを示す（`docs/PLAN.md`の推論結果の形式）。
STAGE = "asr"


def read_manifest(path: Path) -> list[dict]:
    """manifest（1行1発話のJSONL）を読む。"""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def system_name(model: str, spec: ModelSpec, decode_mode: str, use_glossary: bool, two_pass: bool) -> str:
    """結果の`system`に書く名前を作る。デコードの設定と用語集の渡し方を名前に含め、条件の違う結果を混同しないようにする。"""
    name = model
    if spec.backend == "mlx-whisper" and decode_mode == "greedy":
        name += ".greedy"
    if use_glossary:
        name += "+glossary"
    if two_pass:
        name += "+twopass"
    return name


def make_recognizer(
    transcriber: Transcriber,
    spec: ModelSpec,
    use_glossary: bool,
    glossary_file: list | None,
    exclude_terms: Iterable[str] | None = None,
) -> Callable[[np.ndarray, dict], Transcription]:
    """1発話の認識の仕方を決める。

    - `glossary_file`あり：アプリ（`voiceime.engine`）と同じtwo-pass。1回目の結果から用語集の語を選び、認識し直す。
    - `use_glossary`：manifestのその発話の`glossary`をそのまま渡す。
    - どちらも無し：用語のヒント無し。
    `exclude_terms`を指定すると、該当する語はどちらの方式でもASRへのヒントから除く。
    """
    if glossary_file is not None:
        hint_format = asr_hint_format(spec)
        filtered_glossary = exclude_glossary(glossary_file, exclude_terms)
        return lambda audio, record: transcribe_with_hints(
            transcriber, audio, filtered_glossary, "two-pass", hint_format
        )
    if use_glossary:
        excluded = set(exclude_terms or ())

        def recognize_with_row_glossary(audio: np.ndarray, record: dict) -> Transcription:
            terms = [
                term
                for term in terms_from_manifest(record["glossary"])
                if term.surface not in excluded
            ]
            return transcriber.transcribe(audio, terms or None)

        return recognize_with_row_glossary
    return lambda audio, record: transcriber.transcribe(audio, None)


def sample_load() -> dict[str, float | None]:
    """いまのGPUの使用率（%）、CPUの1分平均の負荷、swapの使用量（GB）を返す。

    他の処理が計測へ干渉していたかを後で確かめるために使う。GPUの使用率は直前の自分の推論も含む平均値のため、
    発話ごとの値は目安にとどまる。swapの使用量が増えていれば、メモリ不足で遅延が大きく崩れている。
    """
    ioreg = subprocess.run(
        ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"], capture_output=True, text=True
    ).stdout
    match = re.search(r'"Device Utilization %"=(\d+)', ioreg)
    load1 = float(subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True).stdout.split()[1])
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    swap_used = re.search(r"used = ([\d.]+)M", swap)
    return {
        "gpu_util_pct": float(match.group(1)) if match else None,
        "load1": load1,
        "swap_used_gb": float(swap_used.group(1)) / 1024 if swap_used else None,
    }


def top_processes(n: int = 8) -> list[str]:
    """CPU使用率の高いprocessを上位`n`件返す。計測の前後に、同時に動いていた重い処理を記録するために使う。"""
    out = subprocess.run(["ps", "-Ao", "pid,pcpu,rss,comm", "-r"], capture_output=True, text=True).stdout
    return [line.strip() for line in out.splitlines()[1 : n + 1]]


def git_commit() -> str:
    """このファイルがある作業ツリーのcommitを返す。結果がどの版のコードで作られたかを記録する。"""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent
    )
    return result.stdout.strip()


def run_transcriber(
    recognize: Callable[[np.ndarray, dict], Transcription],
    records: list[dict],
    manifest_dir: Path,
    system: str,
    warmup: int,
    out,
) -> list[dict]:
    """warm-upの後に全発話を順に書き起こし、1発話ずつ`out`へ書く。各発話の直前の負荷の記録を返す。"""
    first_audio = load_audio(manifest_dir / records[0]["audio_path"])
    for _ in range(warmup):
        recognize(first_audio, records[0])

    load_samples = []
    for record in records:
        audio = load_audio(manifest_dir / record["audio_path"])
        load_samples.append({"id": record["id"], **sample_load()})
        start = time.perf_counter()
        result = recognize(audio, record)
        latency = time.perf_counter() - start
        row = {"id": record["id"], "system": system, "stage": STAGE, "hyp": result.text, "latency_s": latency}
        if result.details:
            row["details"] = result.details
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()
    return load_samples


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を読む。"""
    parser = argparse.ArgumentParser(description="manifestの全発話をASRの1候補で書き起こす")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--system", required=True, choices=sorted(MODELS), help="`systems.MODELS`の名前")
    parser.add_argument(
        "--decode",
        choices=["transcribe", "greedy"],
        default="transcribe",
        help="Whisper系のデコード設定。transcribe：既定（タイムスタンプと温度のやり直しあり）、greedy：どちらも無し",
    )
    parser.add_argument("--glossary", action="store_true", help="各発話の用語集を、モデルの用語の入れ口（Whisperのプロンプトなど）へ渡す")
    parser.add_argument(
        "--glossary-file",
        type=Path,
        nargs="+",
        default=None,
        help="用語集のJSONL（複数可）。指定するとアプリと同じtwo-passで、1回目の結果に近い語を選んで認識し直す",
    )
    parser.add_argument(
        "--exclude-terms",
        type=Path,
        default=None,
        help="用語集から除く用語の一覧ファイル（1行1語）。指定した語はASRへのヒントへ渡さない",
    )
    parser.add_argument("--out", type=Path, required=True, help="結果のJSONL。同じ名前の`.meta.json`も書く")
    parser.add_argument("--limit", type=int, default=None, help="先頭から何件だけ動かすか（動作確認用）")
    parser.add_argument("--warmup", type=int, default=1, help="計測の前に先頭の発話を何回書き起こすか")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """引数に従ってASRを実行し、推論結果のJSONLとメタ情報を保存する。"""
    args = parse_args(argv)

    spec = MODELS[args.system]
    if (args.glossary or args.glossary_file) and spec.backend not in GLOSSARY_BACKENDS:
        raise SystemExit(f"{args.system}は用語集のヒントに対応していない")
    if args.glossary and args.glossary_file:
        raise SystemExit("--glossaryと--glossary-fileは同時に使わない")
    excluded_terms = load_term_list(args.exclude_terms) if args.exclude_terms else None
    glossary_file = (
        load_glossary(*args.glossary_file, exclude_terms=excluded_terms)
        if args.glossary_file
        else None
    )
    records = read_manifest(args.manifest)[: args.limit]
    manifest_dir = args.manifest.parent
    system = system_name(args.system, spec, args.decode, args.glossary, glossary_file is not None)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    meta: dict = {
        "system": system,
        "model": args.system,
        "backend": spec.backend,
        "source": spec.source,
        "decode": args.decode,
        "glossary": args.glossary,
        "glossary_file": [str(path) for path in args.glossary_file] if args.glossary_file else None,
        "exclude_terms": str(args.exclude_terms) if args.exclude_terms else None,
        "manifest": str(args.manifest),
        "n_utterances": len(records),
        "warmup": args.warmup,
        "git_commit": git_commit(),
        "machine": platform.platform(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "top_processes_before": top_processes(),
        # 自分のモデルを読み込む前の負荷。GPUの使用率がここで高ければ、他の処理がGPUを使っていた。
        "load_before_model": sample_load(),
    }
    load_start = time.perf_counter()
    with open(args.out, "w", encoding="utf-8") as out:
        import mlx.core as mx

        mx.reset_peak_memory()
        transcriber = build_transcriber(spec, args.decode)
        meta["model_load_s"] = time.perf_counter() - load_start
        recognize = make_recognizer(transcriber, spec, args.glossary, glossary_file, excluded_terms)
        meta["load_samples"] = run_transcriber(recognize, records, manifest_dir, system, args.warmup, out)
        # MLXが確保したGPUメモリの最大値。ONNX RuntimeなどMLXを使わない方式では0に近くなる。
        meta["mlx_peak_memory_gb"] = mx.get_peak_memory() / 1e9
        # macOSの`ru_maxrss`の単位はbyte。
        meta["max_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
        # 別のプロセスで動く方式（speech.cppのworker）は、終了させてからその最大の常駐メモリを記録する。
        if hasattr(transcriber, "close"):
            transcriber.close()
            meta["child_max_rss_gb"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1e9
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta["top_processes_after"] = top_processes()
    meta_path = args.out.with_name(args.out.name.removesuffix(".jsonl") + ".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(records)}件を{args.out}へ書いた")


if __name__ == "__main__":
    main()
