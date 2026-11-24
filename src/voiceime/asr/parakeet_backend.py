"""parakeet-mlxでNVIDIAのParakeet（FastConformerのencoderとTDTのdecoder）を動かす方式。

Whisperと違い入力を30秒へ埋めないため、encoderの計算量が発話の長さに比例する。用語集のヒントは使わない。
"""

from __future__ import annotations

import time

import mlx.core as mx
import numpy as np
from parakeet_mlx import DecodingConfig, from_pretrained
from parakeet_mlx.audio import get_logmel
from parakeet_mlx.alignment import sentences_to_result, tokens_to_sentences

from voiceime.asr.base import Term, Transcription


class ParakeetTranscriber:
    """Parakeetの重み（MLX形式のrepoかdirectory）を読み、既定のgreedyで書き起こす。"""

    def __init__(self, model_path: str) -> None:
        # parakeet-mlxの既定に合わせてbfloat16で読む。
        self.model = from_pretrained(model_path, dtype=mx.bfloat16)
        self.config = DecodingConfig()

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """log-mel、encoder、decoderの時間を分けて測りながら書き起こす。`glossary`は使わない。"""
        start = time.perf_counter()
        # shape: (1, フレーム数, n_mels)。`model.transcribe`と同じくfloat32の波形から作る（parakeet-mlxの音声読み込みもfloat32を返す）。
        mel = get_logmel(mx.array(audio, dtype=mx.float32), self.model.preprocessor_config)
        mx.eval(mel)
        mel_end = time.perf_counter()

        # features shape: (1, 間引き後のフレーム数, d_model)
        features, lengths = self.model.encoder(mel)
        mx.eval(features, lengths)
        encoder_end = time.perf_counter()

        hypotheses, _ = self.model.decode(features, lengths, config=self.config)
        result = sentences_to_result(tokens_to_sentences(hypotheses[0], self.config.sentence))
        decoder_end = time.perf_counter()
        return Transcription(
            text=result.text,
            details={
                "logmel_s": mel_end - start,
                "encoder_s": encoder_end - mel_end,
                "decoder_s": decoder_end - encoder_end,
            },
        )
