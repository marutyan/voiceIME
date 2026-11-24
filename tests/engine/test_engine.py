"""認識エンジンのプロトコルと検査処理を、小さな偽モデルで確認する。"""

from __future__ import annotations

import io
import json
import logging
import stat
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from voiceime.asr.base import Term, Transcription
from voiceime.engine import (
    RecognitionEngine,
    apply_confirmed_replacements,
    merge_two_pass_text,
    transcribe_two_pass,
)
from voiceime.formatter.glossary import DEFAULT_MAX_ENTRIES, GlossaryEntry, load_glossary
from voiceime.formatter.output_check import is_valid_output
from voiceime.formatter.prompt import FormatterInput


class FakeTranscriber:
    """音声配列の先頭値に対応した固定文を返し、必要なら遅延とログも出す。"""

    def __init__(
        self,
        texts: dict[int, str | list[str]] | None = None,
        print_log: bool = False,
        started_event: threading.Event | None = None,
        release_event: threading.Event | None = None,
        delay_s: float = 0.0,
    ):
        self.texts = texts or {}
        self.print_log = print_log
        self.started_event = started_event
        self.release_event = release_event
        self.delay_s = delay_s
        self.calls: list[list[Term] | None] = []
        self.response_counts: dict[int, int] = {}

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """workerが読み込んだ区間の文と受け取った用語ヒントを記録する。"""
        self.calls.append(glossary)
        if self.print_log:
            print("fake model log")
        if len(audio) != 16000:
            if self.started_event is not None and self.release_event is not None:
                self.started_event.set()
                self.release_event.wait(timeout=2)
            if self.delay_s:
                time.sleep(self.delay_s)
            audio_id = int(audio[0])
            responses = self.texts[audio_id]
            if isinstance(responses, list):
                response_index = self.response_counts.get(audio_id, 0)
                text = responses[min(response_index, len(responses) - 1)]
                self.response_counts[audio_id] = response_index + 1
            else:
                text = responses
            return Transcription(text)
        return Transcription("warm-up")


class FakeFormatter:
    """固定出力を返し、raw modeで呼ばれないことを検査できる。"""

    def __init__(self, text: str):
        self.text = text
        self.calls = 0
        self.text_calls: list[str | FormatterInput] = []
        self.glossary_calls: list[list[GlossaryEntry]] = []

    def format(self, raw_text: str | FormatterInput, glossary: list[GlossaryEntry]):
        """設定した文を返す。"""
        self.calls += 1
        self.text_calls.append(raw_text)
        self.glossary_calls.append(glossary)
        return self.text


def make_engine(
    tmp_path: Path,
    transcriber: FakeTranscriber | None = None,
    formatter_kind: str = "none",
    formatter: object | None = None,
    glossary: list[GlossaryEntry] | None = None,
    asr_accepts_glossary: bool = False,
    asr_hint_mode: str = "two-pass",
    asr_hint_format: str = "surface",
    two_pass_policy: str = "always",
    aux_transcriber: object | None = None,
    formatter_input: str = "text",
    formatter_max_glossary: int = DEFAULT_MAX_ENTRIES,
) -> RecognitionEngine:
    """テスト用の音声loader、偽ASR、履歴先を組み合わせる。"""
    return RecognitionEngine(
        transcriber=transcriber or FakeTranscriber({0: "zero", 1: "one"}),
        glossary=glossary or [],
        formatter_kind=formatter_kind,
        formatter=formatter,
        history_path=tmp_path / "history.jsonl",
        asr_name="fake-asr",
        formatter_name=formatter_kind,
        asr_accepts_glossary=asr_accepts_glossary,
        asr_hint_mode=asr_hint_mode,
        asr_hint_format=asr_hint_format,
        audio_loader=lambda path: np.array([int(path.stem)], dtype=np.float32),
        two_pass_policy=two_pass_policy,
        aux_transcriber=aux_transcriber,
        formatter_input=formatter_input,
        formatter_max_glossary=formatter_max_glossary,
    )


def run_messages(engine: RecognitionEngine, messages: list[dict]) -> tuple[list[dict], str]:
    """JSON要求列を一括で渡し、出力イベントと生の標準出力文字列を返す。"""
    source = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    output = io.StringIO()
    engine.serve(source, output)
    return [json.loads(line) for line in output.getvalue().splitlines()], output.getvalue()


def test_ready_precedes_buffered_requests_and_segments_join_by_seq(tmp_path):
    """入力が先に届いていてもreadyを先に返し、区間はseq順で結合する。"""
    transcriber = FakeTranscriber({0: "zero", 1: "one"})
    engine = make_engine(tmp_path, transcriber)
    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1", "app": {"name": "Editor"}},
            {"type": "segment", "session_id": "s1", "seq": 1, "wav_path": "1.wav"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "raw"},
            {"type": "shutdown"},
        ],
    )

    assert events[0] == {"type": "ready", "asr": "fake-asr", "formatter": "none"}
    result = next(event for event in events if event["type"] == "result")
    assert result["raw_text"] == "zeroone"
    assert result["text"] == "zeroone"
    assert result["format_ok"] is True
    assert transcriber.calls[0] is None


def test_cancelled_session_does_not_leak_into_new_session(tmp_path):
    """cancel後に遅れて返った区間を捨て、次のsession_idへ混ぜない。"""
    started = threading.Event()
    release = threading.Event()
    engine = make_engine(
        tmp_path,
        FakeTranscriber({0: "old", 1: "new"}, started_event=started, release_event=release),
    )

    def requests():
        """cancelを処理するまでASRの返却を保留し、進行中の破棄を確かめる。"""
        yield {"type": "start", "session_id": "old"}
        yield {"type": "segment", "session_id": "old", "seq": 0, "wav_path": "0.wav"}
        assert started.wait(timeout=1)
        yield {"type": "cancel", "session_id": "old"}
        release.set()
        yield from [
            {"type": "start", "session_id": "new"},
            {"type": "segment", "session_id": "new", "seq": 0, "wav_path": "1.wav"},
            {"type": "finish", "session_id": "new", "mode": "raw"},
            {"type": "shutdown"},
        ]

    output = io.StringIO()
    engine.serve((json.dumps(message) + "\n" for message in requests()), output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]

    assert not any(event.get("session_id") == "old" for event in events)
    result = next(event for event in events if event["type"] == "result")
    assert result["session_id"] == "new"
    assert result["raw_text"] == "new"


def test_raw_mode_skips_formatter_and_records_history_permissions(tmp_path):
    """raw modeで整形器を呼ばず、履歴を0600で宛先名とともに追記する。"""
    formatter = FakeFormatter("must not be used")
    engine = make_engine(tmp_path, formatter_kind="model", formatter=formatter)
    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1", "app": {"name": "Notes"}},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "raw"},
            {"type": "shutdown"},
        ],
    )

    result = next(event for event in events if event["type"] == "result")
    history_path = tmp_path / "history.jsonl"
    history = json.loads(history_path.read_text())
    assert formatter.calls == 1  # 起動時のwarm-upだけで、sessionのraw modeでは呼ばない。
    assert result["text"] == "zero"
    assert result["format_latency_s"] == 0
    assert stat.S_IMODE(history_path.stat().st_mode) == 0o600
    assert history["app_name"] == "Notes"
    assert history["raw_text"] == history["text"] == "zero"


def test_start_stores_at_most_4000_screen_characters(tmp_path):
    """startのscreen_textを4,000字まで保持し、省略時は空文字列にする。"""
    engine = make_engine(tmp_path)
    engine._output = io.StringIO()
    engine._start_session({"session_id": "long", "screen_text": "画" * 4001})
    engine._start_session({"session_id": "empty"})

    assert engine._sessions["long"].screen_text == "画" * 4000
    assert engine._sessions["empty"].screen_text == ""
    engine.close()


def test_output_check_uses_nfkc_lengths_and_rejects_preambles_and_code_blocks():
    """NFKC後の長さ比を通し、短文・前置き・コードフェンスを拒否する。

    20文字の等長文は通る。
    40文字から2文字への縮小と10文字から51文字への増加は落とす。
    """
    assert is_valid_output(
        "あいうえおかきくけこさしすせそたちつてと",
        "まみむめもやゆよらりるれろわをんがぎぐげ",
    )
    assert not is_valid_output("あいうえお" * 8, "了解")
    assert not is_valid_output("あ" * 10, "い" * 51)
    assert not is_valid_output("あ" * 10, " 整形結果: い")
    assert not is_valid_output("あ" * 10, "```text\nい\n```")
    assert is_valid_output("Ａ" * 10, "い" * 2)


def test_output_check_rejects_new_repetition_but_allows_repetition_in_asr():
    """5文字と4回の語句反復は落とし、ASRにもある反復はそのまま通す。"""
    raw_commas = "HellaSwagのクエリを照合します。"
    assert not is_valid_output(raw_commas, raw_commas + "、、、、、")

    raw_phrase = "Core i7のフラッシュです。"
    assert not is_valid_output(raw_phrase, "Core i7のフラッシュ、その、その、その、その、")

    repeated_asr = "会議はその、その、その、その、からです"
    assert is_valid_output(repeated_asr, repeated_asr + "。")

    assert is_valid_output("動画を再生します。", "動画を再生しますーーーーー。")


def test_output_check_counts_punctuation_in_length_ratio():
    """同じ箇所に句読点だけを足した場合も、非空白文字数の上限で拒否する。"""
    punctuation = "!\"#$%&'()*+,-."
    raw = "あいうえおかきくけこ"
    formatted = "いろはにほへとちりぬ" + punctuation * 3

    assert len(punctuation) == 14
    assert not is_valid_output(raw, formatted)


def test_confirmed_replacement_is_exact_longest_and_skips_ambiguous_aliases():
    """確定置換は最長の明示別名だけに適用し、対象が競合する別名は残す。"""
    glossary = [
        GlossaryEntry("DataLoader", (), ("PT", "PTK")),
        GlossaryEntry("ParallelTransport", (), ("PT",)),
    ]
    assert apply_confirmed_replacements("PTK PT pt", glossary) == "DataLoader PT pt"


def test_glossary_loader_preserves_confirmed_replacements(tmp_path):
    """JSONLのreplace_fromを読み取り、同じsurfaceの重複行も統合する。"""
    glossary_path = tmp_path / "glossary.jsonl"
    glossary_path.write_text(
        '{"surface":"PyTorch","readings":["パイトーチ"],"replace_from":["pytorch"]}\n'
        '{"surface":"PyTorch","readings":["パイ・トーチ"],"replace_from":["PT"]}\n',
        encoding="utf-8",
    )

    assert load_glossary(glossary_path) == [
        GlossaryEntry("PyTorch", ("パイトーチ", "パイ・トーチ"), ("pytorch", "PT"))
    ]


class _ScriptedTranscriber:
    """呼ばれた順に決まった文を返し、渡された用語のヒントを記録する偽のASR。"""

    def __init__(self, texts: list[str]):
        self.texts = list(texts)
        self.hints: list[list[Term] | None] = []

    def transcribe(self, audio, glossary=None):
        self.hints.append(glossary)
        return Transcription(self.texts.pop(0))


def test_transcribe_two_pass_returns_first_pass_and_final():
    """two-passは1回目（ヒント無し）と最終結果を両方返し、近い語が無ければ認識し直さない。"""
    glossary = [GlossaryEntry("PyTorch", ("パイトーチ",)), GlossaryEntry("Slack", ("スラック",))]
    asr = _ScriptedTranscriber(["パイトーチで学習", "PyTorchで学習"])
    first, final = transcribe_two_pass(asr, np.zeros(16000, dtype=np.float32), glossary, "surface-reading")
    assert (first.text, final.text) == ("パイトーチで学習", "PyTorchで学習")
    assert asr.hints == [None, [Term("PyTorch", "パイトーチ")]]

    asr = _ScriptedTranscriber(["今日は晴れ"])
    first, final = transcribe_two_pass(asr, np.zeros(16000, dtype=np.float32), glossary, "surface-reading")
    assert first is final and asr.hints == [None]

    asr = _ScriptedTranscriber(["今日は晴れ"])
    first, final = transcribe_two_pass(
        asr,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        screen_glossary=glossary[:1],
    )
    assert first is final and asr.hints == [None]


def test_segment_merge_keeps_safe_hint_replacements_and_rejects_other_spans():
    """同じ発話の正しいPlayStation置換は採り、無関係なCloud名への変更は戻す。"""
    glossary = [
        GlossaryEntry("QuickSight", ("クイックサイト",)),
        GlossaryEntry("PlayStation", ("プレイステーション",)),
        GlossaryEntry(
            "Cloud Natural Language API", ("クラウドナチュラルランゲージエーピーアイ",)
        ),
    ]
    result = merge_two_pass_text(
        "クイックサイト、プレイステーション",
        "QuickSight、Cloud Natural Language API",
        glossary,
    )

    assert result.text == "QuickSight、プレイステーション"
    assert [edit.accepted for edit in result.edits] == [True, False]
    assert result.edits[0].candidate_surface == "QuickSight"
    assert result.edits[0].reading_similarity == 1.0


@pytest.mark.parametrize(
    ("first", "second", "entry", "expected", "accepted"),
    [
        (
            "グラフを描く",
            "グRuffを描く",
            GlossaryEntry("Ruff", ("ラフ",)),
            "グラフを描く",
            False,
        ),
        (
            "なんだけど",
            "Noneだけど",
            GlossaryEntry("None", ("ナン",)),
            "なんだけど",
            False,
        ),
        (
            "ラフです",
            "Ruffです",
            GlossaryEntry("Ruff", ("ラフ",)),
            "Ruffです",
            True,
        ),
        (
            "ラグを使う",
            "RAGを使う",
            GlossaryEntry("RAG", ("ラグ",)),
            "RAGを使う",
            True,
        ),
    ],
)
def test_segment_merge_requires_short_reading_boundaries(
    first, second, entry, expected, accepted
):
    """短い読みの境界条件を選択と区間結合で共通にする。"""
    result = merge_two_pass_text(first, second, [entry])

    assert result.text == expected
    assert any(edit.accepted for edit in result.edits) is accepted


def test_transcribe_two_pass_can_apply_segment_merge_policy():
    """engineの切替引数で、1回目と2回目の安全な区間を結合する。"""
    glossary = [
        GlossaryEntry("QuickSight", ("クイックサイト",)),
        GlossaryEntry("PlayStation", ("プレイステーション",)),
        GlossaryEntry(
            "Cloud Natural Language API", ("クラウドナチュラルランゲージエーピーアイ",)
        ),
    ]
    asr = _ScriptedTranscriber(
        ["クイックサイト、プレイステーション", "QuickSight、Cloud Natural Language API"]
    )

    first, final = transcribe_two_pass(
        asr,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="segment-merge",
    )

    assert first.text == "クイックサイト、プレイステーション"
    assert final.text == "QuickSight、プレイステーション"
    assert asr.hints == [
        None,
        [Term("QuickSight", "クイックサイト"), Term("PlayStation", "プレイステーション")],
    ]


def test_no_farther_policy_falls_back_to_first_pass():
    """2回目で候補との類似度が下がった場合、発話全体で1回目を選ぶ。"""
    glossary = [GlossaryEntry("PyTorch", ("パイトーチ",))]
    asr = _ScriptedTranscriber(["パイトーチで学習", "他の話に変わりました"])

    first, final = transcribe_two_pass(
        asr,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="no-farther",
    )

    assert first.text == final.text == "パイトーチで学習"
    assert len(asr.hints) == 2


def test_reading_near_policy_skips_second_pass_for_surface_only_match():
    """読みでなく英字surfaceだけが一致する場合、reading-nearは2回目を省く。"""
    glossary = [GlossaryEntry("PyTorch", ("パイトーチ",))]
    asr = _ScriptedTranscriber(["PyTorchで学習"])

    first, final = transcribe_two_pass(
        asr,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="reading-near",
    )

    assert first is final
    assert asr.hints == [None]


def test_segment_merge_keeps_each_playstation_occurrence_and_between_word():
    """一つのdiffに二語がまとまっても、読みの一致を各出現へ割り当てる。"""
    result = merge_two_pass_text(
        "プレイステーションのプレイステーション",
        "PlayStationPlayStation",
        [GlossaryEntry("PlayStation", ("プレイステーション",))],
    )

    assert result.text == "PlayStationのPlayStation"
    assert sum(edit.accepted for edit in result.edits) == 2


def test_segment_merge_accepts_case_only_change_for_a_hinted_surface():
    """英字の大小文字だけが変わったヒント語は、周囲の文を保ったまま表記する。"""
    result = merge_two_pass_text(
        "fcmのコンテナイメージ",
        "FCMのcontainerdジ",
        [
            GlossaryEntry("FCM", ("エフシーエム",)),
            GlossaryEntry("containerd", ("コンテナディー",)),
        ],
    )

    assert result.text == "FCMのコンテナイメージ"
    assert result.edits[0].match_basis == "surface"


@pytest.mark.parametrize(
    ("first", "second", "surface", "reading"),
    [
        (
            "ページアテンションページアテンションの数値",
            "ページAttention U-Netの数値",
            "Attention U-Net",
            "アテンションユーネット",
        ),
        (
            "もっとクイックイーンな方法はないですか?",
            "もっとQuickSightはないですか?",
            "QuickSight",
            "クイックサイト",
        ),
        (
            "オブジェクト思考がしっかりしていて",
            "Objective-Cン結構",
            "Objective-C",
            "オブジェクティブシー",
        ),
        (
            "オープンaiの2強だったところ",
            "OpenCVロに最近",
            "OpenCV",
            "オープンシーブイ",
        ),
        (
            "クエリを選択できている",
            "QueryDetはできている",
            "QueryDet",
            "クエリーデット",
        ),
    ],
)
def test_segment_merge_rejects_known_unrelated_term_rewrites(
    first, second, surface, reading
):
    """読みの類似度が閾値未満のヒント語置換を、区間単位で1回目へ戻す。"""
    result = merge_two_pass_text(
        first, second, [GlossaryEntry(surface, (reading,))]
    )

    assert result.text == first


def test_formatted_output_rejection_falls_back_to_raw_text(tmp_path):
    """前置き付きの整形文を捨て、認識結果とformat_ok=falseを返す。"""
    engine = make_engine(
        tmp_path,
        formatter_kind="model",
        formatter=FakeFormatter("整形結果: zero"),
    )
    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "formatted"},
            {"type": "shutdown"},
        ],
    )

    result = next(event for event in events if event["type"] == "result")
    assert result["raw_text"] == "zero"
    assert result["text"] == "zero"
    assert result["format_ok"] is False


def test_screen_words_are_prioritized_for_asr_and_formatter_without_history_leak(tmp_path):
    """画面用語をASRと整形へ優先して渡し、screen_textは履歴へ書かない。"""
    glossary = [
        GlossaryEntry("PyTorch", ("パイトーチ",)),
        GlossaryEntry("GitHub", ("ギットハブ",)),
        GlossaryEntry("Docker", ("ドッカー",)),
    ]
    raw_text = "ギットハブとパイトーチを使います。"
    screen_text = "GitHub Docker UnlistedScreenTerm"
    transcriber = FakeTranscriber({0: raw_text, 1: raw_text})
    formatter = FakeFormatter(raw_text)
    engine = make_engine(
        tmp_path,
        transcriber=transcriber,
        formatter_kind="model",
        formatter=formatter,
        glossary=glossary,
        asr_accepts_glossary=True,
    )
    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "with-screen", "screen_text": screen_text},
            {"type": "segment", "session_id": "with-screen", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "with-screen", "mode": "formatted"},
            {"type": "start", "session_id": "without-screen"},
            {"type": "segment", "session_id": "without-screen", "seq": 0, "wav_path": "1.wav"},
            {"type": "finish", "session_id": "without-screen", "mode": "formatted"},
            {"type": "shutdown"},
        ],
    )

    assert transcriber.calls == [
        None,
        None,
        [Term("GitHub", "ギットハブ"), Term("Docker", "ドッカー"), Term("PyTorch", "パイトーチ")],
        None,
        [Term("PyTorch", "パイトーチ"), Term("GitHub", "ギットハブ")],
    ]
    assert formatter.glossary_calls == [[], [glossary[1], glossary[0]], [glossary[0], glossary[1]]]
    history_text = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert screen_text not in history_text
    assert "screen_text" not in history_text
    assert not any("screen_text" in event for event in events)


def test_repetition_stopped_formatter_falls_back_to_raw_text(tmp_path):
    """繰り返しで生成を打ち切った整形結果を貼らず、ASRの文を返す。"""
    formatter = FakeFormatter(SimpleNamespace(text="partial", finish_reason="repetition"))
    engine = make_engine(tmp_path, formatter_kind="model", formatter=formatter)
    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "formatted"},
            {"type": "shutdown"},
        ],
    )

    result = next(event for event in events if event["type"] == "result")
    assert result["raw_text"] == "zero"
    assert result["text"] == "zero"
    assert result["format_ok"] is False


def test_asr_hints_obey_term_and_character_limits(tmp_path):
    """ASR用語ヒントを既定の16語・240文字以内に制限する。"""
    entries = [GlossaryEntry(f"語{i:02d}", ()) for i in range(20)]
    engine = make_engine(tmp_path, glossary=entries, asr_accepts_glossary=True)

    hints = engine._asr_hints(entries)
    assert hints == [Term(f"語{i:02d}", "") for i in range(16)]
    assert len("、".join(term.surface for term in hints)) <= 240

    long_entries = [GlossaryEntry(f"語{i}" + "あ" * 100, ()) for i in range(4)]
    long_hints = engine._asr_hints(long_entries)
    assert len(long_hints) == 2
    assert len("、".join(term.surface for term in long_hints)) <= 240


def test_keyword_backend_hints_include_the_first_reading(tmp_path):
    """表記=読み形式のASRへ、surfaceと用語集の先頭readingを渡す。"""
    entry = GlossaryEntry(
        "GitHub", ("ギットハブ", "ギット・ハブ"), alt_readings=("ギトハブ",)
    )
    engine = make_engine(
        tmp_path,
        glossary=[entry],
        asr_accepts_glossary=True,
        asr_hint_format="surface-reading",
    )

    selected = engine.glossary_index.select("ギトハブを使う", min_score=99)
    assert selected == [entry]
    hints = engine._asr_hints(selected + [GlossaryEntry("Q", (), alt_readings=("キュー",))])

    assert hints == [Term("GitHub", "ギットハブ")]
    assert len("\n".join(f"{term.surface}={term.reading}" for term in hints)) <= 240


def test_two_pass_selects_hints_from_each_segments_first_transcript_and_counts_both(tmp_path):
    """初回文から該当語だけを選び、二回分のASR時間をfinish後遅延へ含める。"""
    glossary = [
        GlossaryEntry("GitHub", ("ギットハブ",)),
        GlossaryEntry("Docker", ("ドッカー",)),
        GlossaryEntry("MATH", ("マス",)),
    ]
    first_text = "ギットハブにプッシュしました。ロッカーを再起動します。"
    second_text = "GitHubにプッシュしました。Dockerを再起動します。"
    started = threading.Event()
    release = threading.Event()
    transcriber = FakeTranscriber(
        {0: [first_text, second_text]},
        started_event=started,
        release_event=release,
        delay_s=0.01,
    )
    engine = make_engine(
        tmp_path,
        transcriber=transcriber,
        glossary=glossary,
        asr_accepts_glossary=True,
    )

    def requests():
        """finishを1回目の認識中に送り、二段分の時間が測られるようにする。"""
        yield {"type": "start", "session_id": "two-pass"}
        yield {"type": "segment", "session_id": "two-pass", "seq": 0, "wav_path": "0.wav"}
        assert started.wait(timeout=1)
        yield {"type": "finish", "session_id": "two-pass", "mode": "raw"}
        release.set()
        yield {"type": "shutdown"}

    output = io.StringIO()
    engine.serve((json.dumps(message) + "\n" for message in requests()), output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    result = next(event for event in events if event["type"] == "result")

    assert result["raw_text"] == second_text
    assert transcriber.calls == [
        None,
        None,
        [Term("GitHub", "ギットハブ"), Term("Docker", "ドッカー")],
    ]
    assert result["asr_latency_s"] >= 0.015


def test_static_and_none_hint_modes_control_asr_calls(tmp_path):
    """staticは用語集の先頭語を一度渡し、noneは常にヒントなしで一度だけ認識する。"""
    glossary = [GlossaryEntry("GitHub", ("ギットハブ",))]
    static_asr = FakeTranscriber({0: "raw"})
    static_engine = make_engine(
        tmp_path / "static",
        transcriber=static_asr,
        glossary=glossary,
        asr_accepts_glossary=True,
        asr_hint_mode="static",
    )
    run_messages(
        static_engine,
        [
            {"type": "start", "session_id": "static"},
            {"type": "segment", "session_id": "static", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "static", "mode": "raw"},
            {"type": "shutdown"},
        ],
    )

    none_asr = FakeTranscriber({0: "raw"})
    none_engine = make_engine(
        tmp_path / "none",
        transcriber=none_asr,
        glossary=glossary,
        asr_accepts_glossary=True,
        asr_hint_mode="none",
    )
    run_messages(
        none_engine,
        [
            {"type": "start", "session_id": "none"},
            {"type": "segment", "session_id": "none", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "none", "mode": "raw"},
            {"type": "shutdown"},
        ],
    )

    assert static_asr.calls == [None, [Term("GitHub", "ギットハブ")]]
    assert none_asr.calls == [None, None]


def test_cli_defaults_asr_hint_mode_to_two_pass(monkeypatch):
    """CLIは指定がなければtwo-passを選び、既存のHaas名も受け付ける。"""
    from voiceime.engine.__main__ import _arguments

    monkeypatch.setattr(
        "sys.argv",
        [
            "voiceime.engine",
            "--asr",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--formatter",
            "rules",
            "--glossary",
            "glossary.jsonl",
            "--history",
            "history.jsonl",
        ],
    )

    args = _arguments()
    assert args.asr_hint_mode == "two-pass"
    assert args.exclude_terms is None


def test_engine_cli_exclude_terms_hides_terms_from_asr_screen_and_formatter(tmp_path, monkeypatch):
    """エンジンの--exclude-termsで除外した語は、ASRヒント・画面優先語・整形参考・確定置換に出ない。"""
    import sys
    from types import ModuleType
    from voiceime.engine import __main__ as engine_main

    glossary_path = tmp_path / "glossary.jsonl"
    glossary_path.write_text(
        json.dumps(
            {"surface": "PyTorch", "readings": ["パイトーチ"], "replace_from": ["pt"]},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {"surface": "Dataset", "readings": ["データセット"], "replace_from": ["ds"]},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    exclude_path = tmp_path / "exclude.txt"
    exclude_path.write_text("Dataset\n", encoding="utf-8")
    history_path = tmp_path / "history.jsonl"

    wav_path = tmp_path / "0.wav"
    import wave

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(bytes(3200))

    raw_text = "パイトーチとデータセットとptとds"
    transcriber = FakeTranscriber({0: [raw_text, raw_text]})
    formatter = FakeFormatter(raw_text)

    class _FakeMlxFormatter:
        def __init__(self, _path: str, use_prefix_cache: bool = True):
            self.use_prefix_cache = use_prefix_cache

        def format(self, text: str, glossary: list[GlossaryEntry]):
            return formatter.format(text, glossary)

    fake_engine_module = ModuleType("voiceime.formatter.engine")
    fake_engine_module.MlxFormatter = _FakeMlxFormatter
    monkeypatch.setitem(sys.modules, "voiceime.formatter.engine", fake_engine_module)
    monkeypatch.setattr(engine_main, "build_transcriber", lambda _spec, _decode: transcriber)
    # 音声読込の代わりにID=0を返し、FakeTranscriberで固定文を返す。
    monkeypatch.setattr("voiceime.engine.load_audio", lambda _path: np.array([0], dtype=np.float32))
    monkeypatch.setattr(
        "sys.argv",
        [
            "voiceime.engine",
            "--asr",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--aux-asr",
            "none",
            "--formatter",
            "fake-formatter-model",
            "--glossary",
            str(glossary_path),
            "--exclude-terms",
            str(exclude_path),
            "--history",
            str(history_path),
        ],
    )
    assert engine_main._arguments().exclude_terms == exclude_path

    requests = [
        {"type": "start", "session_id": "s1", "screen_text": "Dataset PyTorch"},
        {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": str(wav_path)},
        {"type": "finish", "session_id": "s1", "mode": "formatted"},
        {"type": "shutdown"},
    ]
    stdout_buffer = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO("".join(json.dumps(m) + "\n" for m in requests)))
    monkeypatch.setattr("sys.stdout", stdout_buffer)

    engine_main.main()

    events = [json.loads(line) for line in stdout_buffer.getvalue().splitlines()]
    result = next(event for event in events if event["type"] == "result")
    # warm-up(None) -> 1回目(None) -> 2回目(PyTorchのみ。Datasetは画面にあっても出ない)
    assert transcriber.calls == [None, None, [Term("PyTorch", "パイトーチ")]]
    # warm-up([]) -> 本番(PyTorchのみ。Datasetは出ない)
    assert [[entry.surface for entry in call] for call in formatter.glossary_calls] == [
        [],
        ["PyTorch"],
    ]
    # 確定置換もPyTorch(pt)だけ効き、Dataset(ds)は効かない。
    assert result["text"] == "パイトーチとデータセットとPyTorchとds"


def test_stdout_contains_only_protocol_json_when_models_print(tmp_path, capsys):
    """モデルが標準出力へログを書いても、プロトコル出力以外は混ざらない。"""
    engine = make_engine(tmp_path, FakeTranscriber({0: "zero"}, print_log=True))
    _, output = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "raw"},
            {"type": "shutdown"},
        ],
    )

    assert all(isinstance(json.loads(line), dict) for line in output.splitlines())
    assert capsys.readouterr().out == ""


def test_transcribe_two_pass_merges_aux_text_and_preserves_default(monkeypatch):
    """補助仮説を与えると選択入力を改行連結し、与えない場合は従来どおりの動作を保つ。"""
    import voiceime.engine as engine_module

    glossary = [
        GlossaryEntry("Horovod", ("ホロヴォド",)),
        GlossaryEntry("PyTorch", ("パイトーチ",)),
    ]
    recorded_inputs: list[str] = []
    original_select = engine_module.select_glossary

    def spy_select(text, entries, *args, **kwargs):
        recorded_inputs.append(text)
        return original_select(text, entries, *args, **kwargs)

    monkeypatch.setattr(engine_module, "select_glossary", spy_select)

    # (a) 補助仮説を与えると「1回目＋改行＋補助仮説」で用語を選び、結果に補助仮説と選択文字列を添える。
    asr_with_aux = _ScriptedTranscriber(["分散学習にこれを使います", "分散学習にHorovodを使います"])
    result_with_aux = transcribe_two_pass(
        asr_with_aux,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="segment-merge",
        aux_text="分散学習にHorovodを使います",
    )
    first_aux, final_aux = result_with_aux
    assert recorded_inputs[-1] == "分散学習にこれを使います\n分散学習にHorovodを使います"
    assert asr_with_aux.hints == [None, [Term("Horovod", "ホロヴォド")]]
    assert result_with_aux.aux_text == "分散学習にHorovodを使います"
    assert result_with_aux.selection_text == "分散学習にこれを使います\n分散学習にHorovodを使います"
    assert first_aux is result_with_aux[0] and final_aux is result_with_aux[1]
    # segment-mergeの採否基準は変わらず、元区間と読みが対応しない「これ」は1回目を保つ。
    assert first_aux.text == "分散学習にこれを使います"
    assert final_aux.text == "分散学習にこれを使います"

    # (b) 補助仮説を与えない場合は1回目だけで用語を選び、従来と全く同じ結果を返す。
    asr_without_aux = _ScriptedTranscriber(["分散学習にこれを使います"])
    result_without_aux = transcribe_two_pass(
        asr_without_aux,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="segment-merge",
    )
    first_base, final_base = result_without_aux
    assert recorded_inputs[-1] == "分散学習にこれを使います"
    assert asr_without_aux.hints == [None]
    assert first_base is final_base
    assert result_without_aux.aux_text is None
    assert result_without_aux.selection_text == "分散学習にこれを使います"

    # 空文字の補助仮説は連結せず、与えない場合と同じ選択文字列になる。
    asr_empty_aux = _ScriptedTranscriber(["分散学習にこれを使います"])
    result_empty_aux = transcribe_two_pass(
        asr_empty_aux,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="segment-merge",
        aux_text="",
    )
    assert recorded_inputs[-1] == "分散学習にこれを使います"
    assert result_empty_aux.selection_text == "分散学習にこれを使います"
    assert result_empty_aux[0] is result_empty_aux[1]

    # 1回目だけで一致する語がある場合も、補助なしなら従来どおり再認識する。
    asr_plain = _ScriptedTranscriber(["パイトーチで学習", "PyTorchで学習"])
    first_plain, final_plain = transcribe_two_pass(
        asr_plain,
        np.zeros(16000, dtype=np.float32),
        glossary,
        "surface-reading",
        two_pass_policy="segment-merge",
    )
    assert recorded_inputs[-1] == "パイトーチで学習"
    assert (first_plain.text, final_plain.text) == ("パイトーチで学習", "PyTorchで学習")
    assert asr_plain.hints == [None, [Term("PyTorch", "パイトーチ")]]


def test_engine_aux_asr_runs_in_parallel_and_shares_merged_selection_with_formatter(tmp_path):
    """補助ASRをwarm-up後に主ASRの1回目と並列実行し、合併文字列を整形の用語選択にも使う。"""
    glossary = [
        GlossaryEntry("Horovod", ("ホロヴォド",)),
        GlossaryEntry("PyTorch", ("パイトーチ",)),
    ]
    barrier = threading.Barrier(2, timeout=2.0)

    class _ParallelPrimaryTranscriber:
        """1回目だけbarrierで待ち、補助ASRと同時に動いていることを確かめる偽ASR。"""

        def __init__(self) -> None:
            self.calls: list[list[Term] | None] = []

        def transcribe(self, audio: np.ndarray, glossary_terms: list[Term] | None = None) -> Transcription:
            self.calls.append(glossary_terms)
            if len(audio) == 16000:
                return Transcription("warm-up")
            if glossary_terms is None:
                barrier.wait()
                return Transcription("パイトーチでこれを使う")
            return Transcription("PyTorchでHorovodを使う")

    class _ParallelAuxTranscriber:
        """主ASRの1回目と同時にbarrierへ到達し、英字表記を含む仮説を返す偽補助ASR。"""

        def __init__(self) -> None:
            self.calls: list[tuple[int, list[Term] | None]] = []

        def transcribe(self, audio: np.ndarray, glossary_terms: list[Term] | None = None) -> Transcription:
            self.calls.append((len(audio), glossary_terms))
            if len(audio) == 16000:
                return Transcription("aux-warm-up")
            barrier.wait()
            return Transcription("PyTorchでHorovodを使う")

    primary = _ParallelPrimaryTranscriber()
    aux = _ParallelAuxTranscriber()
    formatter = FakeFormatter("PyTorchでHorovodを使う。")
    engine = make_engine(
        tmp_path,
        transcriber=primary,
        formatter_kind="model",
        formatter=formatter,
        glossary=glossary,
        asr_accepts_glossary=True,
        asr_hint_format="surface-reading",
        two_pass_policy="segment-merge",
        aux_transcriber=aux,
    )

    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "formatted"},
            {"type": "shutdown"},
        ],
    )

    result = next(event for event in events if event["type"] == "result")
    # 補助ASRもwarm-up（16000サンプル）と本番区間（ヒント無し）の両方で呼ばれる。
    assert aux.calls == [(16000, None), (1, None)]
    # 2回目のヒントに、補助仮説由来のHorovodと主ASR由来のPyTorchが入る。
    assert primary.calls[0] is None
    assert primary.calls[1] is None
    assert {term.surface for term in primary.calls[2] or []} == {"PyTorch", "Horovod"}
    # segment-merge後（「これ」は読みが合わず維持）が整形の入力文になる。
    assert result["raw_text"] == "PyTorchでこれを使う"
    assert formatter.text_calls == ["音声入力", "PyTorchでこれを使う"]
    # 整形へ渡す用語一覧は合併文字列から選ぶため、segment-merge後の文に無いHorovodも含まれる。
    assert formatter.glossary_calls[0] == []
    assert {entry.surface for entry in formatter.glossary_calls[1]} == {"PyTorch", "Horovod"}
    assert result["text"] == "PyTorchでHorovodを使う。"
    assert result["format_ok"] is True


@pytest.mark.parametrize("use_aliases", [True, False])
def test_engine_applies_aliases_to_all_formatter_inputs_and_prioritizes_matches(tmp_path, use_aliases):
    """3つの整形入力を直し、別名が一致した語を画面の語よりも先に上限まで渡す。"""
    pytorch = GlossaryEntry("PyTorch", ("パイトーチ",))
    ijcai = GlossaryEntry("IJCAI", ("イジカイ",), aliases=("維持会", "いじかい") if use_aliases else ())
    iclr = GlossaryEntry("ICLR", ("アイシーエルアール",), aliases=("アイクリア",) if use_aliases else ())
    neurips = GlossaryEntry("NeurIPS", ("ニューリップス",), aliases=("ニューリプス",) if use_aliases else ())
    first = "パイトーチで維持会に向けた"
    second = "PyTorchでニューリプスに出す"
    aux = "いじかいに出す。アイクリアを使う"
    primary = FakeTranscriber({0: [first, second]})
    formatter = FakeFormatter("PyTorchで研究を発表する。")
    engine = make_engine(
        tmp_path,
        transcriber=primary,
        formatter_kind="model",
        formatter=formatter,
        glossary=[pytorch, ijcai, iclr, neurips],
        asr_accepts_glossary=True,
        aux_transcriber=FakeTranscriber({0: aux}),
        formatter_input="d",
        formatter_max_glossary=3,
    )

    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1", "screen_text": "PyTorch"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "formatted"},
            {"type": "shutdown"},
        ],
    )

    result = next(event for event in events if event["type"] == "result")
    assert result["raw_text"] == second
    assert result["format_ok"] is True
    if use_aliases:
        assert formatter.text_calls[-1] == FormatterInput(
            first_pass="パイトーチでIJCAIに向けた",
            combined_text="PyTorchでNeurIPSに出す",
            qwen_hypothesis="IJCAIに出す。ICLRを使う",
        )
        assert formatter.glossary_calls[-1] == [neurips, ijcai, iclr]
        assert primary.calls[-1] == [Term("IJCAI", "イジカイ"), Term("ICLR", "アイシーエルアール"), Term("PyTorch", "パイトーチ")]
    else:
        assert formatter.text_calls[-1] == FormatterInput(
            first_pass=first, combined_text=second, qwen_hypothesis=aux,
        )
        assert formatter.glossary_calls[-1] == [pytorch]
        assert primary.calls[-1] == [Term("PyTorch", "パイトーチ")]


def test_engine_prioritizes_alias_from_first_pass_without_auxiliary_asr(tmp_path):
    """1回目にだけ現れた別名でも、補助ASRなしで再認識と整形の用語一覧に残す。"""
    entry = GlossaryEntry("画像処理", (), aliases=("画像書類",))
    primary = FakeTranscriber({0: ["画像書類に向けた", "これに向けた"]})
    formatter = FakeFormatter("画像処理に向けた。")
    engine = make_engine(
        tmp_path,
        transcriber=primary,
        formatter_kind="model",
        formatter=formatter,
        glossary=[entry],
        asr_accepts_glossary=True,
        formatter_max_glossary=1,
    )
    events, _ = run_messages(
        engine,
        [
            {"type": "start", "session_id": "s1"},
            {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
            {"type": "finish", "session_id": "s1", "mode": "formatted"},
            {"type": "shutdown"},
        ],
    )

    assert primary.calls[-1] == [Term("画像処理", "")]
    assert formatter.text_calls[-1] == "これに向けた"
    assert formatter.glossary_calls[-1] == [entry]
    assert next(event for event in events if event["type"] == "result")["format_ok"] is True


def test_engine_aux_asr_exception_logs_warning_and_falls_back(tmp_path, caplog):
    """補助ASRが例外を出しても警告をログに出し、補助なしと同じ結果で続ける。"""
    glossary = [
        GlossaryEntry("PyTorch", ("パイトーチ",)),
        GlossaryEntry("Horovod", ("ホロヴォド",)),
    ]

    class _FailingAuxTranscriber:
        """warm-upと本番のどちらでも例外を出す偽補助ASR。"""

        def transcribe(self, audio: np.ndarray, glossary_terms: list[Term] | None = None) -> Transcription:
            raise RuntimeError("aux crashed")

    primary_fallback = FakeTranscriber({0: ["パイトーチで学習", "PyTorchで学習"]})
    formatter_fallback = FakeFormatter("PyTorchで学習。")
    engine_fallback = make_engine(
        tmp_path / "fallback",
        transcriber=primary_fallback,
        formatter_kind="model",
        formatter=formatter_fallback,
        glossary=glossary,
        asr_accepts_glossary=True,
        asr_hint_format="surface-reading",
        two_pass_policy="segment-merge",
        aux_transcriber=_FailingAuxTranscriber(),
    )

    primary_base = FakeTranscriber({0: ["パイトーチで学習", "PyTorchで学習"]})
    formatter_base = FakeFormatter("PyTorchで学習。")
    engine_base = make_engine(
        tmp_path / "base",
        transcriber=primary_base,
        formatter_kind="model",
        formatter=formatter_base,
        glossary=glossary,
        asr_accepts_glossary=True,
        asr_hint_format="surface-reading",
        two_pass_policy="segment-merge",
    )

    messages = [
        {"type": "start", "session_id": "s1"},
        {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": "0.wav"},
        {"type": "finish", "session_id": "s1", "mode": "formatted"},
        {"type": "shutdown"},
    ]
    with caplog.at_level(logging.WARNING, logger="voiceime.engine"):
        events_fallback, _ = run_messages(engine_fallback, messages)
    events_base, _ = run_messages(engine_base, messages)

    result_fallback = next(event for event in events_fallback if event["type"] == "result")
    result_base = next(event for event in events_base if event["type"] == "result")
    assert not any(event["type"] == "error" for event in events_fallback)
    assert any(record.levelno == logging.WARNING and "補助ASR" in record.message for record in caplog.records)
    assert result_fallback["raw_text"] == result_base["raw_text"] == "PyTorchで学習"
    assert result_fallback["text"] == result_base["text"] == "PyTorchで学習。"
    assert primary_fallback.calls == primary_base.calls == [None, None, [Term("PyTorch", "パイトーチ")]]
    assert formatter_fallback.glossary_calls == formatter_base.glossary_calls


def test_engine_cli_aux_asr_option_can_be_disabled_and_wires_transcriber(tmp_path, monkeypatch):
    """CLIの--aux-asrは既定で無効、指定時は補助ASRを読み込んで並列認識と整形選択へ接続する。"""
    import sys
    import wave
    from types import ModuleType
    from voiceime.engine import __main__ as engine_main

    glossary_path = tmp_path / "glossary.jsonl"
    glossary_path.write_text(
        json.dumps({"surface": "Horovod", "readings": ["ホロヴォド"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.jsonl"
    wav_path = tmp_path / "0.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(bytes(3200))

    # --aux-asr none で補助ASRを無効にでき、整形への入力は1文の形式へ戻る。
    monkeypatch.setattr(
        "sys.argv",
        [
            "voiceime.engine",
            "--asr",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--aux-asr",
            "none",
            "--formatter",
            "rules",
            "--glossary",
            str(glossary_path),
            "--history",
            str(history_path),
        ],
    )
    disabled = engine_main._arguments()
    assert disabled.aux_asr is None
    assert disabled.formatter_input == "text"

    primary = FakeTranscriber({0: ["分散学習にこれを使う", "分散学習にHorovodを使う"]})
    aux = FakeTranscriber({0: "分散学習にHorovodを使う"})
    formatter = FakeFormatter("分散学習にHorovodを使う。")
    built_sources: list[tuple[str, str]] = []

    def fake_build_transcriber(spec, decode_mode):
        built_sources.append((spec.source, decode_mode))
        if spec.option == "qwen3-asr":
            return aux
        return primary

    class _FakeMlxFormatter:
        def __init__(self, _path: str, use_prefix_cache: bool = True):
            self.use_prefix_cache = use_prefix_cache

        def format(self, text: str, glossary: list[GlossaryEntry]):
            return formatter.format(text, glossary)

    fake_engine_module = ModuleType("voiceime.formatter.engine")
    fake_engine_module.MlxFormatter = _FakeMlxFormatter
    monkeypatch.setitem(sys.modules, "voiceime.formatter.engine", fake_engine_module)
    monkeypatch.setattr(engine_main, "build_transcriber", fake_build_transcriber)
    monkeypatch.setattr("voiceime.engine.load_audio", lambda _path: np.array([0], dtype=np.float32))
    monkeypatch.setattr(
        "sys.argv",
        [
            "voiceime.engine",
            "--asr",
            "haas-ja-v1.0-speechcpp-q8_0",
            "--aux-asr",
            "qwen3-asr-0.6b-8bit",
            "--formatter-input",
            "text",
            "--formatter",
            "fake-formatter-model",
            "--glossary",
            str(glossary_path),
            "--history",
            str(history_path),
        ],
    )
    assert engine_main._arguments().aux_asr == "qwen3-asr-0.6b-8bit"

    requests = [
        {"type": "start", "session_id": "s1"},
        {"type": "segment", "session_id": "s1", "seq": 0, "wav_path": str(wav_path)},
        {"type": "finish", "session_id": "s1", "mode": "formatted"},
        {"type": "shutdown"},
    ]
    stdout_buffer = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO("".join(json.dumps(m) + "\n" for m in requests)))
    monkeypatch.setattr("sys.stdout", stdout_buffer)

    engine_main.main()

    events = [json.loads(line) for line in stdout_buffer.getvalue().splitlines()]
    result = next(event for event in events if event["type"] == "result")
    assert len(built_sources) == 2
    assert built_sources[1] == ("mlx-community/Qwen3-ASR-0.6B-8bit", "greedy")
    assert aux.calls == [None, None]  # warm-up + 本番
    assert primary.calls == [None, None, [Term("Horovod", "ホロヴォド")]]
    assert formatter.text_calls == ["音声入力", "分散学習にこれを使う"]
    assert [[e.surface for e in call] for call in formatter.glossary_calls] == [[], ["Horovod"]]
    assert result["raw_text"] == "分散学習にこれを使う"
    assert result["text"] == "分散学習にHorovodを使う。"


def test_formatter_input_d_requires_aux_transcriber(tmp_path) -> None:
    """3つのASR結果を渡す形式は、補助ASRが無いと作れないので起動時に断る。"""
    import pytest

    from voiceime.engine import RecognitionEngine

    with pytest.raises(ValueError):
        RecognitionEngine(
            transcriber=object(),
            glossary=[],
            formatter_kind="none",
            formatter=None,
            history_path=tmp_path / "history.jsonl",
            asr_name="asr",
            formatter_name="none",
            asr_accepts_glossary=True,
            formatter_input="d",
        )
