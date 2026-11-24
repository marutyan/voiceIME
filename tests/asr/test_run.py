"""`voiceime.asr.run`の引数と`--exclude-terms`によるASRヒント除外の確認。"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from types import ModuleType

import numpy as np

from voiceime.asr import run as asr_run
from voiceime.asr.base import Term, Transcription
from voiceime.asr.systems import MODELS
from voiceime.formatter.glossary import GlossaryEntry


class _RecordingTranscriber:
    """呼び出し時に渡された用語ヒントを記録し、順番に固定文を返す偽ASR。"""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls: list[list[Term] | None] = []

    def transcribe(self, _audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        self.calls.append(glossary)
        text = self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]
        return Transcription(text)


def test_make_recognizer_excludes_terms_in_two_pass_mode() -> None:
    """two-passモードで除外語をASRヒントへ渡さず、除外語しか無い発話は再認識しない。"""
    spec = MODELS["haas-ja-v1.0-speechcpp-q8_0"]
    glossary = [
        GlossaryEntry("PyTorch", ("パイトーチ",)),
        GlossaryEntry("Dataset", ("データセット",)),
    ]
    audio = np.zeros(1600, dtype=np.float32)

    asr = _RecordingTranscriber(["パイトーチのデータセット", "PyTorchのデータセット"])
    recognize = asr_run.make_recognizer(asr, spec, False, glossary, exclude_terms={"Dataset"})
    result = recognize(audio, {})
    assert result.text == "PyTorchのデータセット"
    assert asr.calls == [None, [Term("PyTorch", "パイトーチ")]]

    asr_only_excluded = _RecordingTranscriber(["データセットを使う"])
    recognize_only_excluded = asr_run.make_recognizer(
        asr_only_excluded, spec, False, glossary, exclude_terms={"Dataset"}
    )
    assert recognize_only_excluded(audio, {}).text == "データセットを使う"
    assert asr_only_excluded.calls == [None]


def test_make_recognizer_excludes_terms_in_row_glossary_mode() -> None:
    """行ごとの--glossaryモードでも除外語をASRヒントから外し、全除外時はNoneを渡す。"""
    spec = MODELS["whisper-large-v3-turbo"]
    audio = np.zeros(1600, dtype=np.float32)
    record = {
        "glossary": [
            {"surface": "PyTorch", "readings": ["パイトーチ"]},
            {"surface": "Dataset", "readings": ["データセット"]},
        ]
    }

    asr = _RecordingTranscriber(["PyTorchとデータセット"])
    recognize = asr_run.make_recognizer(asr, spec, True, None, exclude_terms={"Dataset"})
    recognize(audio, record)
    assert asr.calls == [[Term("PyTorch", "パイトーチ")]]

    asr_all_excluded = _RecordingTranscriber(["パイトーチとデータセット"])
    recognize_none = asr_run.make_recognizer(
        asr_all_excluded, spec, True, None, exclude_terms={"PyTorch", "Dataset"}
    )
    recognize_none(audio, record)
    assert asr_all_excluded.calls == [None]


def test_asr_run_main_applies_exclude_terms_and_records_meta(tmp_path, monkeypatch) -> None:
    """voiceime.asr.runのCLIで--exclude-termsが効き、.meta.jsonにも記録される。"""
    wav_path = tmp_path / "u1.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(bytes(3200))

    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "id": "u1",
                "audio_path": "u1.wav",
                "glossary": [
                    {"surface": "PyTorch", "readings": ["パイトーチ"]},
                    {"surface": "Dataset", "readings": ["データセット"]},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    glossary_file = tmp_path / "glossary.jsonl"
    glossary_file.write_text(
        json.dumps({"surface": "PyTorch", "readings": ["パイトーチ"]}, ensure_ascii=False) + "\n"
        + json.dumps({"surface": "Dataset", "readings": ["データセット"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    exclude_file = tmp_path / "exclude.txt"
    exclude_file.write_text("Dataset\n", encoding="utf-8")

    fake_asr = _RecordingTranscriber(["パイトーチのデータセット", "PyTorchのデータセット"])
    fake_mlx = ModuleType("mlx")
    fake_mlx.__path__ = []
    fake_mx = ModuleType("mlx.core")
    fake_mx.reset_peak_memory = lambda: None
    fake_mx.get_peak_memory = lambda: 0
    fake_mlx.core = fake_mx
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mx)
    monkeypatch.setattr(asr_run, "build_transcriber", lambda _spec, _decode: fake_asr)
    monkeypatch.setattr(asr_run, "sample_load", lambda: {"gpu_util_pct": 0.0, "load1": 0.0, "swap_used_gb": 0.0})
    monkeypatch.setattr(asr_run, "top_processes", lambda: [])

    out_path = tmp_path / "out.jsonl"
    asr_run.main(
        [
            "--manifest",
            str(manifest),
            "--system",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--glossary-file",
            str(glossary_file),
            "--exclude-terms",
            str(exclude_file),
            "--warmup",
            "0",
            "--out",
            str(out_path),
        ]
    )

    assert fake_asr.calls == [None, [Term("PyTorch", "パイトーチ")]]
    meta = json.loads((tmp_path / "out.meta.json").read_text(encoding="utf-8"))
    assert meta["exclude_terms"] == str(exclude_file)
    assert asr_run.parse_args(
        [
            "--manifest",
            str(manifest),
            "--system",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--exclude-terms",
            str(exclude_file),
            "--out",
            str(out_path),
        ]
    ).exclude_terms == Path(exclude_file)
