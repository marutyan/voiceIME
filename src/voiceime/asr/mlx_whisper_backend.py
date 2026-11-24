"""mlx-whisperでWhisper系のモデル（OpenAIのWhisper、kotoba-whisperなど）を動かす方式。

デコードの設定は2種類を持つ。
- `transcribe`：`mlx_whisper.transcribe`の既定（タイムスタンプあり、温度を上げたやり直しあり）。
- `greedy`：30秒の窓1つだけを、タイムスタンプなし、温度0、やり直しなしで解く。
  encoderとdecoderの時間を分けて測れるよう、encoderを自分で呼んでから`decode`へ特徴量を渡す。
"""

from __future__ import annotations

import time
from typing import Literal

import mlx.core as mx
import numpy as np
from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim
from mlx_whisper.decoding import DecodingOptions, decode
from mlx_whisper.transcribe import ModelHolder, transcribe

from voiceime.asr.base import Term, Transcription, glossary_prompt

# 書き起こす言語。kotoba-whisper-bilingualでも、日本語の書き起こしはこの指定で行う。
LANGUAGE = "ja"

DecodeMode = Literal["transcribe", "greedy"]


class MLXWhisperTranscriber:
    """MLX形式のWhisperの重み（ローカルのdirectoryかHugging Faceのrepo）で書き起こす。"""

    def __init__(self, model_path: str, decode_mode: DecodeMode) -> None:
        self.model_path = model_path
        self.decode_mode = decode_mode
        # `mlx_whisper.transcribe`が内部で使うキャッシュへ読み込み、両方の設定で同じモデルを共有する。
        self.model = ModelHolder.get_model(model_path, mx.float16)

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """設定に応じて書き起こす。`greedy`ではlog-mel、encoder、decoderの時間を`details`に入れる。"""
        prompt = glossary_prompt(glossary)
        if self.decode_mode == "transcribe":
            result = transcribe(
                audio, path_or_hf_repo=self.model_path, language=LANGUAGE, initial_prompt=prompt, verbose=None
            )
            return Transcription(text=result["text"])
        return self._transcribe_greedy(audio, prompt)

    def _transcribe_greedy(self, audio: np.ndarray, prompt: str | None) -> Transcription:
        """30秒の窓1つで、encoderとdecoderを分けて時間を測りながら解く。30秒を超える音声は扱わない。"""
        start = time.perf_counter()
        # `mlx_whisper.transcribe`と同じく、末尾に30秒の無音を足してlog-melを計算し、発話の部分だけを切り出す。
        mel = log_mel_spectrogram(audio, n_mels=self.model.dims.n_mels, padding=N_SAMPLES)
        content_frames = mel.shape[-2] - N_FRAMES
        if content_frames > N_FRAMES:
            raise ValueError(f"greedyの設定は30秒以下の音声だけを扱う（{content_frames / 100:.1f}秒）")
        # shape: (N_FRAMES=3000, n_mels)。発話が短くても3000フレームへ0で埋めるため、encoderの計算量は一定になる。
        segment = pad_or_trim(mel[:content_frames], N_FRAMES, axis=-2).astype(mx.float16)
        mx.eval(segment)
        mel_end = time.perf_counter()

        # shape: (1, n_audio_ctx=1500, n_audio_state)
        features = self.model.encoder(segment[None])
        mx.eval(features)
        encoder_end = time.perf_counter()

        options = DecodingOptions(
            task="transcribe",
            language=LANGUAGE,
            temperature=0.0,
            without_timestamps=True,
            prompt=prompt,
            fp16=True,
        )
        result = decode(self.model, features[0], options)
        decoder_end = time.perf_counter()
        return Transcription(
            text=result.text,
            details={
                "logmel_s": mel_end - start,
                "encoder_s": encoder_end - mel_end,
                "decoder_s": decoder_end - encoder_end,
                "n_tokens": float(len(result.tokens)),
            },
        )
