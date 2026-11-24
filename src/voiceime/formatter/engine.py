"""mlx-lmで整形用LLMを動かす推論処理。

プロンプトは`voiceime.formatter.prompt`で作り、学習と同じ形式にする。
指示文の部分のKVキャッシュを事前に作って使い回す方式（`use_prefix_cache`）も選べる。
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass
from typing import Sequence

import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.models.cache import make_prompt_cache

from voiceime.formatter.glossary import GlossaryEntry
from voiceime.formatter.output_check import RepetitionChecker
from voiceime.formatter.restore import restore_listed_readings
from voiceime.formatter.style import apply_output_style
from voiceime.formatter.prompt import (
    GLOSSARY_HEADER,
    FormatterInput,
    formatter_output_reference_text,
    formatter_input_text,
    needs_special_tokens,
    render_prompt,
)

# 短文にも通常の整形分を確保し、長文では入力token数の1.5倍を上限にする。
# 整形後は入力とほぼ同じ長さなので、表記修正用に50%余裕を残して過剰生成を抑える。
MIN_MAX_TOKENS = 64
MAX_TOKENS_PER_INPUT_TOKEN = 1.5
# 思考出力に対応したモデルが`<think>`を出した場合に取り除くための正規表現。
THINK_PATTERN = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)


@dataclass
class FormatResult:
    """1件の整形結果と、遅延の内訳を見るための計測値。"""

    text: str
    elapsed_s: float
    prompt_tokens: int
    cached_tokens: int
    generation_tokens: int
    prompt_tps: float
    generation_tps: float
    peak_memory_gb: float
    finish_reason: str | None


class MlxFormatter:
    """MLXの整形用LLMを読み込み、ASRの出力と用語集から整形済みの文を作る。"""

    def __init__(self, model_path: str, use_prefix_cache: bool = False):
        self.model, self.tokenizer = load(model_path)
        self.use_prefix_cache = use_prefix_cache
        self._prefix_tokens: list[int] = []
        self._prefix_cache = None
        if use_prefix_cache:
            self._build_prefix_cache()

    def _encode(self, text: str) -> list[int]:
        """プロンプト文字列をtoken列にする。BOSの扱いはmlx-lmの`stream_generate`と同じにする。"""
        return self.tokenizer.encode(text, add_special_tokens=needs_special_tokens(self.tokenizer, text))

    def _build_prefix_cache(self) -> None:
        """全ての入力で共通の部分（指示文から用語集の見出しまで）を先に計算し、KVキャッシュとして持つ。

        境界のtoken化が後ろの文字とつながって変わる場合に備え、共通部分の最後の1 tokenはキャッシュに含めない。
        """
        sample = render_prompt(self.tokenizer, "", [])
        prefix_text = sample[: sample.index(GLOSSARY_HEADER) + len(GLOSSARY_HEADER)]
        self._prefix_tokens = self._encode(prefix_text)[:-1]
        self._prefix_cache = make_prompt_cache(self.model)
        self.model(mx.array(self._prefix_tokens)[None], cache=self._prefix_cache)
        mx.eval([c.state for c in self._prefix_cache])

    def format(self, asr_text: str | FormatterInput, glossary: Sequence[GlossaryEntry]) -> FormatResult:
        """1件を貪欲法で整形する。経過時間はプロンプトの作成から出力の確定までを測る。"""
        start = time.perf_counter()
        tokens = self._encode(render_prompt(self.tokenizer, asr_text, glossary))
        source_text = formatter_input_text(asr_text)
        cache = None
        cached = 0
        n = len(self._prefix_tokens)
        if self._prefix_cache is not None and n and tokens[:n] == self._prefix_tokens:
            # キャッシュは生成で書き換わるため、毎回複製して使う。
            cache = copy.deepcopy(self._prefix_cache)
            cached = n
            tokens = tokens[n:]
        output_reference = formatter_output_reference_text(asr_text)
        input_tokens = len(self.tokenizer.encode(output_reference, add_special_tokens=False))
        max_tokens = max(MIN_MAX_TOKENS, int(input_tokens * MAX_TOKENS_PER_INPUT_TOKEN))
        pieces: list[str] = []
        last = None
        stopped_for_repetition = False
        repetition_checker = RepetitionChecker(source_text)
        previous_partial_text = ""
        for response in stream_generate(
            self.model,
            self.tokenizer,
            mx.array(tokens),
            max_tokens=max_tokens,
            prompt_cache=cache,
        ):
            pieces.append(response.text)
            last = response
            partial_text = THINK_PATTERN.sub("", "".join(pieces)).strip()
            if repetition_checker.has_new_repetition_since(previous_partial_text, partial_text):
                stopped_for_repetition = True
                break
            previous_partial_text = partial_text
        text = apply_output_style(THINK_PATTERN.sub("", "".join(pieces)).strip())
        text = restore_listed_readings(text, glossary)
        elapsed = time.perf_counter() - start
        return FormatResult(
            text=text,
            elapsed_s=elapsed,
            prompt_tokens=len(tokens) + cached,
            cached_tokens=cached,
            generation_tokens=last.generation_tokens if last else 0,
            prompt_tps=last.prompt_tps if last else 0.0,
            generation_tps=last.generation_tps if last else 0.0,
            peak_memory_gb=mx.get_peak_memory() / 1e9,
            finish_reason="repetition" if stopped_for_repetition else (last.finish_reason if last else None),
        )
