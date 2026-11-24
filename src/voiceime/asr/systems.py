"""比べるASRの候補を名前で登録し、名前から`Transcriber`を作る。

候補を足すときは`MODELS`へ1行足す。重みの取得元（Hugging Faceのrepoか、変換済みのlocal directory）もここに置き、
結果の記録（`run.py`のmeta）からどの重みを使ったか追えるようにする。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from voiceime.asr.base import Transcriber

# 変換・量子化した重みの置き場所。Gitに入れない大きなファイルのため、本体のrepositoryの`models/`の下へ置く。
LOCAL_MODEL_DIR = "/Users/marutyan/PrivateDev/voiceIME/models/asr"

Backend = Literal[
    "mlx-whisper", "parakeet-mlx", "sherpa-onnx", "mlx-audio-llm", "mlx-audio", "haas-mlx", "speechcpp"
]

# 発話ごとの用語集のヒントを渡せる実装。これ以外の実装に`--glossary`を付けると、条件を取り違えないよう止める。
GLOSSARY_BACKENDS = ("mlx-whisper", "mlx-audio-llm", "speechcpp")


@dataclass(frozen=True)
class ModelSpec:
    """1つの候補の実装の種類と重みの取得元。

    `files`はsherpa-onnxのencoder、decoder、joinerのファイル名。`option`は実装ごとの追加の指定で、
    mlx-audio-llmではモデルの種類（qwen3-asrかgranite-speech）、mlx-audioでは`generate`へ渡す言語の指定、
    haas-mlxではencoderの型（bfloat16かfloat32）に使う。
    """

    backend: Backend
    source: str
    files: tuple[str, str, str] | None = None
    option: str | None = None


MODELS: dict[str, ModelSpec] = {
    # OpenAIのWhisper。fp16はmlx-communityの変換済みの重み、q8とq4はそれを`convert.py quantize`で量子化したもの。
    # 重みを消した候補（kotoba-whisper、WhisperKit、large-v3のq4）は登録から外した。
    "whisper-large-v3": ModelSpec("mlx-whisper", "mlx-community/whisper-large-v3-mlx"),
    "whisper-large-v3-q8": ModelSpec("mlx-whisper", f"{LOCAL_MODEL_DIR}/whisper-large-v3-q8"),
    "whisper-large-v3-turbo": ModelSpec("mlx-whisper", "mlx-community/whisper-large-v3-turbo"),
    "whisper-large-v3-turbo-q8": ModelSpec("mlx-whisper", f"{LOCAL_MODEL_DIR}/whisper-large-v3-turbo-q8"),
    "whisper-large-v3-turbo-q4": ModelSpec("mlx-whisper", f"{LOCAL_MODEL_DIR}/whisper-large-v3-turbo-q4"),
    # NVIDIAのParakeetの日本語版（TDT-CTC、0.6B）をMLXへ変換した重み。
    "parakeet-tdt_ctc-0.6b-ja": ModelSpec("parakeet-mlx", "mlx-community/parakeet-tdt_ctc-0.6b-ja"),
    # ReazonSpeechのk2版（Zipformer transducer）。日本語版と、日英を学習した版。
    "reazonspeech-k2-v2": ModelSpec(
        "sherpa-onnx",
        "reazon-research/reazonspeech-k2-v2",
        ("encoder-epoch-99-avg-1.onnx", "decoder-epoch-99-avg-1.onnx", "joiner-epoch-99-avg-1.onnx"),
    ),
    "reazonspeech-k2-v2-int8": ModelSpec(
        "sherpa-onnx",
        "reazon-research/reazonspeech-k2-v2",
        ("encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.int8.onnx", "joiner-epoch-99-avg-1.int8.onnx"),
    ),
    "reazonspeech-k2-v2-ja-en": ModelSpec(
        "sherpa-onnx",
        "csukuangfj/reazonspeech-k2-v2-ja-en",
        ("encoder-epoch-35-avg-1.onnx", "decoder-epoch-35-avg-1.onnx", "joiner-epoch-35-avg-1.onnx"),
    ),
    # Qwen3-ASR（mlx-community版）。日本語は4bitで大きく劣化するという報告があるため、bf16と8bitを主に測る。
    **{
        f"qwen3-asr-{size}-{precision}": ModelSpec(
            "mlx-audio-llm", f"mlx-community/Qwen3-ASR-{size.upper()}-{precision}", option="qwen3-asr"
        )
        for size in ("0.6b", "1.7b")
        for precision in ("bf16", "8bit", "4bit")
    },
    # Qwen3-ASR 0.6Bを、用語を含む合成音声と実音声の書き起こしで追加学習し、8bitへ変換した重み（2 epoch、lr 3e-5）。
    "qwen3-asr-0.6b-asrft-b-8bit": ModelSpec(
        "mlx-audio-llm", f"{LOCAL_MODEL_DIR}/qwen3-asr-0.6b-asrft-b/mlx-8bit", option="qwen3-asr"
    ),
    # IBM Granite Speech 5.0 2B（IBMの重みをmlx-audioがそのまま読む。bf16）。
    "granite-speech-5.0-2b": ModelSpec("mlx-audio-llm", "ibm-granite/granite-speech-5.0-2b", option="granite-speech"),
    # 速度の参考。Nemotronは日本語の指定に`ja-JP`を渡す（`ja`だけでは`ja-JA`と`ja-JP`の両方に当たり、mlx-audioが止める）。
    # Voxtral Realtimeは言語を自動で判定する。
    "nemotron-3.5-asr-streaming-0.6b": ModelSpec(
        "mlx-audio", "mlx-community/nemotron-3.5-asr-streaming-0.6b", option="ja-JP"
    ),
    "voxtral-mini-4b-realtime-2602-4bit": ModelSpec("mlx-audio", "mlx-community/Voxtral-Mini-4B-Realtime-2602-4bit"),
    # Haas-ja-v1.0。公式の`.nemo`を`haas_backend.py convert`で変換したMLX版（encoderはbf16、予測ネットワークはfloat32）と、
    # speech.cppのGGUF版（sakasegawa/Haas-ja-v1.0-GGUF、commit 6b965d5）。
    "haas-ja-v1.0-mlx": ModelSpec("haas-mlx", f"{LOCAL_MODEL_DIR}/haas-ja-v1.0-mlx", option="bfloat16"),
    "haas-ja-v1.0-mlx-fp32": ModelSpec("haas-mlx", f"{LOCAL_MODEL_DIR}/haas-ja-v1.0-mlx", option="float32"),
    **{
        f"haas-ja-v1.0-speechcpp-{quant.lower()}": ModelSpec(
            "speechcpp", f"{LOCAL_MODEL_DIR}/haas-ja-v1.0-gguf/Haas-616M-ja-v1.0-{quant}.gguf"
        )
        for quant in ("F16", "Q8_0", "Q4_K")
    },
}


def asr_hint_format(spec: ModelSpec) -> str:
    """用語のヒントの書式。speech.cpp（Haas）は`表記=読み`、他は表記だけを使う。"""
    return "surface-reading" if spec.backend == "speechcpp" else "surface"


def build_transcriber(spec: ModelSpec, decode_mode: str) -> Transcriber:
    """候補の定義から`Transcriber`を作る（モデルの読み込みを含む）。"""
    if spec.backend == "mlx-whisper":
        from voiceime.asr.mlx_whisper_backend import MLXWhisperTranscriber

        return MLXWhisperTranscriber(spec.source, decode_mode)  # type: ignore[arg-type]
    if spec.backend == "parakeet-mlx":
        from voiceime.asr.parakeet_backend import ParakeetTranscriber

        return ParakeetTranscriber(spec.source)
    if spec.backend == "sherpa-onnx":
        from voiceime.asr.sherpa_backend import SherpaTransducerTranscriber

        assert spec.files is not None
        return SherpaTransducerTranscriber(spec.source, *spec.files)
    if spec.backend == "mlx-audio-llm":
        from voiceime.asr.mlx_audio_backend import MlxAudioLLMTranscriber

        return MlxAudioLLMTranscriber(spec.source, spec.option)  # type: ignore[arg-type]
    if spec.backend == "mlx-audio":
        from voiceime.asr.mlx_audio_backend import MlxAudioGenerateTranscriber

        return MlxAudioGenerateTranscriber(spec.source, {"language": spec.option} if spec.option else {})
    if spec.backend == "haas-mlx":
        import mlx.core as mx

        from voiceime.asr.haas_backend import HaasTranscriber

        return HaasTranscriber(spec.source, getattr(mx, spec.option))
    if spec.backend == "speechcpp":
        from voiceime.asr.speechcpp_backend import SpeechCppWorkerTranscriber

        return SpeechCppWorkerTranscriber(spec.source)
    raise ValueError(f"{spec.backend}は`Transcriber`を作らない")
