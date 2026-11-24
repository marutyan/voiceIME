"""speech.cpp（ggmlのC++実装、Metal）の`speech worker`で、GGUF形式のHaas-ja-v1.0などを動かす方式。

workerはモデルを1回だけ読み込んで常駐し、標準入出力のJSON Linesで1発話ずつ認識する。
音声は16bitのPCMをbase64で送り、遅延はPython側で送信から結果の受信までを測る（プロセス間の受け渡しを含む）。
Haasでは用語集を`keywords`（1行1語の`表記=読み`）で渡せる。

`speech`は https://github.com/nyosegawa/speech.cpp をcommit 8d18924（0.11.0）、ggmlをcommit 79b50d2で
`cmake -B build && cmake --build build --config Release`（Metal）して作り、`SPEECH_CLI`へ置いた。
"""

from __future__ import annotations

import base64
import itertools
import json
import subprocess
from pathlib import Path

import numpy as np

from voiceime.asr.base import SAMPLE_RATE, Term, Transcription

# ローカルでビルドしたspeech.cppの実行ファイル。グローバルにはインストールしない。
SPEECH_CLI = Path("/Users/marutyan/PrivateDev/voiceIME/models/asr/speech.cpp/bin/speech")

# 表記に含まれると`keywords`の書式（1行1語、`表記=読み,読み`）を壊す文字。含む語は渡さない。
KEYWORD_FORBIDDEN = (",", "、", "\n", "\r", "=", "\t")


def format_keywords(glossary: list[Term]) -> str:
    """用語集をspeech.cppの`keywords`の書式（1行1語の`表記=読み`）にする。"""
    lines = [
        f"{term.surface}={term.reading}"
        for term in glossary
        if not any(char in term.surface or char in term.reading for char in KEYWORD_FORBIDDEN)
    ]
    return "\n".join(lines)


class SpeechCppWorkerTranscriber:
    """`speech worker`を起動して常駐させ、1発話ずつ認識させる。"""

    def __init__(self, model_path: str, threads: int | None = None) -> None:
        """`threads`はworkerが使うCPUのthread数。Noneならspeech.cppの既定（高性能コアの数）。"""
        command = [str(SPEECH_CLI), "worker", model_path]
        if threads is not None:
            command += ["--threads", str(threads)]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        ready = self._read_message()
        if ready["type"] != "ready":
            raise RuntimeError(f"speech workerが起動しない：{ready}")
        self.ready = ready
        self._ids = itertools.count()

    def _read_message(self) -> dict:
        """workerの標準出力から1行（JSON）を読む。終了していれば誤りとして止める。"""
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("speech workerが終了した")
        return json.loads(line)

    def _send(self, message: dict) -> None:
        """workerの標準入力へ1行（JSON）を書く。"""
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """1発話を送り、終了の知らせ（`end`）の`text`を返す。`glossary`があれば`keywords`として渡す。"""
        request_id = f"u{next(self._ids)}"
        # workerはPCMを`x / 32768`で読むため、同じ尺度で16bitへ丸める。
        pcm = np.clip(np.round(audio * 32768.0), -32768, 32767).astype("<i2").tobytes()
        self._send({"type": "chunk", "id": request_id, "seq": 0, "pcm": base64.b64encode(pcm).decode("ascii")})
        request = {"type": "transcribe", "id": request_id, "sample_rate": SAMPLE_RATE}
        if glossary:
            request["keywords"] = format_keywords(glossary)
        self._send(request)
        while True:
            message = self._read_message()
            if message.get("id") != request_id or message["type"] == "progress":
                continue
            if message["type"] != "end":
                raise RuntimeError(f"speech workerが認識に失敗した：{message}")
            return Transcription(text=message["text"])

    def close(self) -> None:
        """標準入力を閉じてworkerを終了させる。"""
        self.process.stdin.close()
        self.process.wait(timeout=30)
