"""`voiceime.asr.batch`の再開と仕上げ（欠けの検出、重複の除去）の確認。ASRは動かさない。"""

import json
import wave
from pathlib import Path

import pytest

from voiceime.asr import batch as asr_batch
from voiceime.asr.base import Term, Transcription
from voiceime.asr.batch import done_ids, finalize, parse_args


def _write(path, rows, tail=""):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows) + tail, encoding="utf-8")


def test_done_ids_ignores_broken_last_line(tmp_path):
    path = tmp_path / "out.jsonl"
    _write(path, [{"id": "a", "hyp": "x"}], tail='{"id": "b", "hy')
    assert done_ids(path) == {"a"}
    assert done_ids(tmp_path / "missing.jsonl") == set()


def test_finalize_orders_by_manifest_and_keeps_last_duplicate(tmp_path):
    path = tmp_path / "out.jsonl"
    _write(path, [{"id": "b", "hyp": "古い"}, {"id": "a", "hyp": "1"}, {"id": "b", "hyp": "新しい"}])
    finalize(path, ["a", "b"])
    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == [
        {"id": "a", "hyp": "1"},
        {"id": "b", "hyp": "新しい"},
    ]


def test_finalize_stops_when_utterances_are_missing(tmp_path):
    path = tmp_path / "out.jsonl"
    _write(path, [{"id": "a", "hyp": "1"}])
    with pytest.raises(RuntimeError, match="1件が欠けている"):
        finalize(path, ["a", "b"])


def test_batch_parse_args_and_exclude_terms(tmp_path, monkeypatch):
    """voiceime.asr.batchの--exclude-termsで除外した語がtwo-passヒントに出ない。"""
    args = parse_args(
        [
            "--manifest",
            "m.jsonl",
            "--system",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--glossary-file",
            "g.jsonl",
            "--exclude-terms",
            "unseen.txt",
            "--out-plain",
            "p.jsonl",
            "--out-two-pass",
            "tp.jsonl",
        ]
    )
    assert args.exclude_terms == Path("unseen.txt")

    wav_path = tmp_path / "u1.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(bytes(3200))

    manifest = tmp_path / "manifest.jsonl"
    _write(manifest, [{"id": "u1", "audio_path": "u1.wav"}])
    glossary_file = tmp_path / "glossary.jsonl"
    _write(
        glossary_file,
        [
            {"surface": "PyTorch", "readings": ["パイトーチ"]},
            {"surface": "Dataset", "readings": ["データセット"]},
        ],
    )
    exclude_file = tmp_path / "exclude.txt"
    exclude_file.write_text("Dataset\n", encoding="utf-8")

    received_hints: list[list[Term] | None] = []

    class _FakeTranscriber:
        def transcribe(self, _audio, glossary=None):
            received_hints.append(glossary)
            if glossary is None:
                return Transcription("パイトーチのデータセット")
            return Transcription("PyTorchのデータセット")

    monkeypatch.setattr(asr_batch, "build_transcriber", lambda _spec, _decode: _FakeTranscriber())

    out_plain = tmp_path / "plain.jsonl"
    out_two_pass = tmp_path / "two_pass.jsonl"
    asr_batch.main(
        [
            "--manifest",
            str(manifest),
            "--system",
            "whisper-large-v3-turbo",
            "--glossary-file",
            str(glossary_file),
            "--exclude-terms",
            str(exclude_file),
            "--out-plain",
            str(out_plain),
            "--out-two-pass",
            str(out_two_pass),
        ]
    )

    assert received_hints == [None, [Term("PyTorch", "パイトーチ")]]
    two_pass_rows = [json.loads(line) for line in out_two_pass.read_text(encoding="utf-8").splitlines()]
    assert two_pass_rows[0]["hyp"] == "PyTorchのデータセット"
