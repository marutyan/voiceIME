"""大量の音声を、アプリと同じtwo-passで認識し、学習データ用にヒント無しとtwo-passの結果を両方保存する。

整形用LLMの学習の入力を、実際のASRの出力にするために使う。遅延は測らないため、speech.cppのworkerを
複数起動して並列に処理する。途中で止まっても、出力に既にある発話を飛ばして再開できる。
最後に、manifestの全発話がちょうど1件ずつ出力にあることを確かめ、重複（再開時の書き直し）を除いて書き直す。

実行例（手元のMac、作業ツリーで）：
    uv run python -m voiceime.asr.batch --manifest /Users/marutyan/PrivateDev/voiceIME/data/tts/val/manifest.jsonl \
        --system haas-ja-v1.0-speechcpp-q8_0 --glossary-file /Users/marutyan/PrivateDev/voiceIME/data/text/glossary.jsonl \
        --out-plain runs/asr-tts/haas-val.jsonl --out-two-pass runs/asr-tts/haas2p-val.jsonl --workers 3 --threads 2
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from pathlib import Path

from voiceime.asr.base import load_audio
from voiceime.asr.run import read_manifest
from voiceime.asr.systems import MODELS, asr_hint_format, build_transcriber
from voiceime.engine import TWO_PASS_POLICIES, transcribe_two_pass
from voiceime.formatter.glossary import load_glossary, load_term_list

# 結果の`stage`。ASR単体の出力であることを示す（`docs/PLAN.md`の推論結果の形式）。
STAGE = "asr"


class TimedTranscriber:
    """呼び出しごとの認識時間を記録する包み。two-passの1回目と全体の時間を分けて残すために使う。

    並列に動かしているため、時間は他のworkerの影響を受けた参考値である。
    """

    def __init__(self, transcriber) -> None:
        self.transcriber = transcriber
        self.durations: list[float] = []

    def transcribe(self, audio, glossary=None):
        start = time.perf_counter()
        result = self.transcriber.transcribe(audio, glossary)
        self.durations.append(time.perf_counter() - start)
        return result


def done_ids(path: Path) -> set[str]:
    """出力に既にある発話のid。途中で書きかけの最後の行（JSONとして読めない行）は無視する。"""
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ids.add(json.loads(line)["id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


def finalize(path: Path, ids_in_order: list[str]) -> None:
    """出力を、manifestの順に1件ずつ（同じidは後から書いた行を採る）並べ直す。欠けている発話があれば止める。"""
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[row["id"]] = row
    missing = [i for i in ids_in_order if i not in rows]
    if missing:
        raise RuntimeError(f"{path}に{len(missing)}件が欠けている（例：{missing[:3]}）")
    with open(path, "w", encoding="utf-8") as f:
        for i in ids_in_order:
            f.write(json.dumps(rows[i], ensure_ascii=False) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を読む。"""
    parser = argparse.ArgumentParser(description="manifestの全発話をtwo-passで認識し、ヒント無しとtwo-passの結果を保存する")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--system", required=True, choices=sorted(MODELS))
    parser.add_argument("--glossary-file", type=Path, nargs="+", required=True, help="two-passで語を選ぶ用語集（複数可）")
    parser.add_argument(
        "--exclude-terms",
        type=Path,
        default=None,
        help="用語集から除く用語の一覧ファイル（1行1語）。指定した語はtwo-passのヒントへ渡さない",
    )
    parser.add_argument("--out-plain", type=Path, required=True, help="ヒント無し（two-passの1回目）の結果のJSONL")
    parser.add_argument("--out-two-pass", type=Path, required=True, help="two-passの最終結果のJSONL")
    parser.add_argument(
        "--two-pass-policy",
        choices=TWO_PASS_POLICIES,
        default="always",
        help="two-passの2回目の採り方（エンジンと同じ選択肢）",
    )
    parser.add_argument("--workers", type=int, default=1, help="並列に動かすASRの数（speech.cppのときだけ2以上にできる）")
    parser.add_argument("--threads", type=int, default=None, help="speech.cppのworker1つが使うCPUのthread数")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """manifestの全発話を並列に認識し、ヒント無しとtwo-passの結果を保存する。"""
    args = parse_args(argv)

    spec = MODELS[args.system]
    if args.workers > 1 and spec.backend != "speechcpp":
        raise SystemExit("並列に動かせるのはspeech.cppの方式だけ（MLXの方式は1プロセスで1つずつ動かす）")
    excluded_terms = load_term_list(args.exclude_terms) if args.exclude_terms else None
    glossary = load_glossary(*args.glossary_file, exclude_terms=excluded_terms)
    hint_format = asr_hint_format(spec)
    records = read_manifest(args.manifest)
    manifest_dir = args.manifest.parent
    plain_system, two_pass_system = args.system, f"{args.system}+twopass"

    # 両方の出力にある発話だけを済みとみなす。片方だけの発話はやり直し、重複は最後に除く。
    finished = done_ids(args.out_plain) & done_ids(args.out_two_pass)
    todo: queue.Queue = queue.Queue()
    for record in records:
        if record["id"] not in finished:
            todo.put(record)
    total = todo.qsize()
    print(f"{len(records)}件中{len(finished)}件は済み、{total}件を認識する", flush=True)

    for path in (args.out_plain, args.out_two_pass):
        path.parent.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()
    progress = {"done": 0, "errors": []}
    started = time.perf_counter()

    def work(out_plain, out_two_pass) -> None:
        """1つのASRで、待ち行列が空になるまで発話を認識し、2つの出力へ同時に書く。"""
        if spec.backend == "speechcpp":
            from voiceime.asr.speechcpp_backend import SpeechCppWorkerTranscriber

            transcriber = SpeechCppWorkerTranscriber(spec.source, threads=args.threads)
        else:
            transcriber = build_transcriber(spec, "greedy")
        timed = TimedTranscriber(transcriber)
        try:
            while True:
                try:
                    record = todo.get_nowait()
                except queue.Empty:
                    return
                audio = load_audio(manifest_dir / record["audio_path"])
                timed.durations.clear()
                first, final = transcribe_two_pass(
                    timed, audio, glossary, hint_format, two_pass_policy=args.two_pass_policy
                )
                first_latency, latency = timed.durations[0], sum(timed.durations)
                rows = (
                    {"id": record["id"], "system": plain_system, "stage": STAGE, "hyp": first.text,
                     "latency_s": first_latency},
                    {"id": record["id"], "system": two_pass_system, "stage": STAGE, "hyp": final.text,
                     "latency_s": latency},
                )
                with write_lock:
                    out_plain.write(json.dumps(rows[0], ensure_ascii=False) + "\n")
                    out_plain.flush()
                    out_two_pass.write(json.dumps(rows[1], ensure_ascii=False) + "\n")
                    out_two_pass.flush()
                    progress["done"] += 1
                    if progress["done"] % 200 == 0:
                        elapsed = time.perf_counter() - started
                        print(f"{progress['done']}/{total}件（{elapsed:.0f}秒）", flush=True)
        except Exception as error:  # 1つのworkerの失敗を記録し、最後にまとめて誤りとして止める
            progress["errors"].append(repr(error))
            raise
        finally:
            close = getattr(transcriber, "close", None)
            if callable(close):
                close()

    with open(args.out_plain, "a", encoding="utf-8") as out_plain, open(args.out_two_pass, "a", encoding="utf-8") as out_two_pass:
        threads = [threading.Thread(target=work, args=(out_plain, out_two_pass)) for _ in range(args.workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    if progress["errors"]:
        raise SystemExit(f"認識に失敗したworkerがある：{progress['errors']}")

    ids = [record["id"] for record in records]
    finalize(args.out_plain, ids)
    finalize(args.out_two_pass, ids)
    print(f"全{len(ids)}件を{args.out_plain}と{args.out_two_pass}に書いた（{time.perf_counter() - started:.0f}秒）")


if __name__ == "__main__":
    main()
