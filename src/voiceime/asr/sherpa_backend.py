"""sherpa-onnxで、ReazonSpeechのk2版（Zipformerのencoderとtransducerのdecoder）を動かす方式。

入力を30秒へ埋めないため、計算量が発話の長さに比例する。CPUのONNX Runtimeで動かし、用語集のヒントは使わない。
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import sherpa_onnx
from huggingface_hub import snapshot_download

from voiceime.asr.base import SAMPLE_RATE, Term, Transcription

# ONNX Runtimeに使わせるCPUのthread数。M3 Proの高性能コア6つのうち、他の処理の分を残して4つにする。
NUM_THREADS = 4


class SherpaTransducerTranscriber:
    """Hugging Faceのrepoにあるencoder、decoder、joinerのONNXとtokensを読み、greedyで書き起こす。"""

    def __init__(self, repo: str, encoder: str, decoder: str, joiner: str) -> None:
        src = Path(snapshot_download(repo, allow_patterns=[encoder, decoder, joiner, "tokens.txt"]))
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(src / encoder),
            decoder=str(src / decoder),
            joiner=str(src / joiner),
            tokens=str(src / "tokens.txt"),
            num_threads=NUM_THREADS,
            sample_rate=SAMPLE_RATE,
            decoding_method="greedy_search",
            provider="cpu",
        )

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """1発話を一括で認識する。`glossary`は使わない。"""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, audio)
        start = time.perf_counter()
        self.recognizer.decode_stream(stream)
        decode_end = time.perf_counter()
        return Transcription(text=stream.result.text, details={"decode_s": decode_end - start})
