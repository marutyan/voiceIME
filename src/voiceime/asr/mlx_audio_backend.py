"""mlx-audioでASRを動かす方式。

`MlxAudioLLMTranscriber`は、音声encoderとLLMのdecoderを組み合わせたASR（Qwen3-ASR、Granite Speech）を動かす。
encoder、prefill（音声と指示をLLMへ入れる段）、生成の時間を分けて測るため、各モデルの`generate`と同じ手順を
mlx-audioの内部の関数で組み直している。内部の関数を使うので、mlx-audioの版を`pyproject.toml`で固定する。
用語集は、各モデルの用語の渡し方（Qwen3-ASRはsystem message、Granite Speechは指示文の`Keywords:`）で渡す。

`MlxAudioGenerateTranscriber`は、速度の参考に測るだけのモデル（Nemotron、Voxtral Realtime）を、
mlx-audioの`generate`のまま動かす。時間の内訳は取らず、用語集も使わない。
"""

from __future__ import annotations

import time
from typing import Literal

import mlx.core as mx
import numpy as np
from mlx_audio.lm.generate import generate_step
from mlx_audio.lm.sample_utils import make_sampler
from mlx_audio.stt import load
from mlx_audio.stt.models.granite_speech.granite_speech import _resolve_prompt
from mlx_audio.stt.utils import merge_hotwords

from voiceime.asr.base import Term, Transcription

AudioLLMKind = Literal["qwen3-asr", "granite-speech"]

# 1発話で生成するtokenの上限。10秒の発話は100 token未満なので、繰り返しに陥った場合だけ打ち切る値にする。
MAX_TOKENS = 512


class MlxAudioLLMTranscriber:
    """mlx-audioで読めるQwen3-ASRかGranite Speechの重みで、温度0（greedy）で書き起こす。"""

    def __init__(self, model_path: str, kind: AudioLLMKind) -> None:
        # Qwen3-ASRの`load`は本体を`_model`に包んで返す。`generate_step`は本体の`__call__`の引数を見るため、本体を使う。
        loaded = load(model_path)
        self.model = getattr(loaded, "_model", loaded)
        self.kind = kind
        self.sampler = make_sampler(0.0)

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """log-mel、encoder、prefill、生成の時間を分けて測りながら書き起こす。"""
        surfaces = [term.surface for term in glossary] if glossary else None
        start = time.perf_counter()
        if self.kind == "qwen3-asr":
            features, mask, n_audio_tokens = self.model._preprocess_audio(audio)
            # 言語を指定すると、出力の先頭の言語名の部分を指示側へ入れ、本文だけを生成させる。
            prompt_ids = self.model._build_prompt(
                n_audio_tokens, "Japanese", merge_hotwords(None, surfaces)
            )[0]
            eos_ids = self.model._eos_token_ids()
        else:
            features, n_audio_tokens = self.model._extract_features(mx.array(audio, dtype=mx.float32))
            # 書き起こし（翻訳ではない）を日本語の指定で行う。用語は指示文の末尾に`Keywords: ...`として入る。
            # 句読点と大文字小文字を付ける指示（punctuate）を使う。付けないと英字がすべて小文字になり、他の候補と条件が揃わない。
            instruction = _resolve_prompt("asr", None, None, source_language="ja", hotwords=surfaces, punctuate=True)
            prompt_ids = self.model._build_prompt(n_audio_tokens, instruction)
            eos_ids = {self.model._tokenizer.eos_token_id}
        mx.eval(features)
        logmel_end = time.perf_counter()

        if self.kind == "qwen3-asr":
            audio_features = self.model.get_audio_features(features, mask)
        else:
            audio_features = self.model.get_audio_features(features)
        # Qwen3-ASRは(1, token数)、Granite Speechは(token数,)のtoken列を受け取る。
        # shape: (1, 指示と音声のtoken数, LLMの隠れ次元)
        ids_for_embeds = prompt_ids[None] if self.kind == "qwen3-asr" else prompt_ids
        inputs_embeds = self.model._build_inputs_embeds(ids_for_embeds, audio_features)
        mx.eval(inputs_embeds)
        encoder_end = time.perf_counter()

        tokens: list[int] = []
        first_token_time = None
        for token, _ in generate_step(
            prompt=prompt_ids,
            input_embeddings=inputs_embeds[0],
            model=self.model,
            max_tokens=MAX_TOKENS,
            sampler=self.sampler,
        ):
            if first_token_time is None:
                first_token_time = time.perf_counter()
            if int(token) in eos_ids:
                break
            tokens.append(int(token))
        decode_end = time.perf_counter()
        first_token_time = first_token_time or decode_end

        text = self.model._tokenizer.decode(tokens, skip_special_tokens=True)
        return Transcription(
            text=text.strip(),
            details={
                "logmel_s": logmel_end - start,
                "encoder_s": encoder_end - logmel_end,
                "prefill_s": first_token_time - encoder_end,
                "generate_s": decode_end - first_token_time,
                "n_prompt_tokens": float(prompt_ids.size),
                "n_tokens": float(len(tokens)),
            },
        )


class MlxAudioGenerateTranscriber:
    """mlx-audioで読めるモデルを、そのモデルの`generate`（既定の設定）で書き起こす。"""

    def __init__(self, model_path: str, generate_kwargs: dict) -> None:
        self.model = load(model_path)
        self.generate_kwargs = generate_kwargs

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """1発話を書き起こす。`glossary`は使わない。"""
        result = self.model.generate(mx.array(audio, dtype=mx.float32), **self.generate_kwargs)
        return Transcription(text=result.text.strip())
