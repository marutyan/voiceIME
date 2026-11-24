"""区間認識、整形、履歴保存をJSON Linesプロトコルへ接続する。"""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import sys
import threading
import time
import unicodedata
from contextlib import redirect_stdout
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable, TextIO

import numpy as np
from rapidfuzz.distance import Levenshtein

from voiceime.asr.base import Term, Transcriber, Transcription, load_audio
from voiceime.formatter.glossary import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_MIN_SCORE,
    GlossaryIndex,
    GlossaryEntry,
    find_short_reading_matches,
    normalize_kana,
    score_entry_in_text,
    score_entry_readings,
    select_glossary,
    select_glossary_with_priority,
    select_screen_glossary,
    to_katakana,
)
from voiceime.formatter.output_check import is_valid_output
from voiceime.formatter.prompt import FormatterInput
from voiceime.formatter.rules import format_with_rules

logger = logging.getLogger(__name__)

# ASRの初期プロンプトが長くなりすぎないように、語数と合計文字数を制限する。
ASR_GLOSSARY_MAX_TERMS = 16
ASR_GLOSSARY_MAX_CHARS = 240
# startで受け取る画面文字列を、プロトコルの最大4,000字に切り詰める。
SCREEN_TEXT_MAX_CHARS = 4000
# two-passの再認識結果の選び方。既定のalwaysは従来の出力を保つ。
TWO_PASS_POLICIES = ("always", "reading-near", "no-farther", "segment-merge")
# 区間の元文字列と候補語の読みを比べる正規化Levenshtein類似度の下限。
# valで0.60〜0.80を整形まで通して比べ、CERが最も低い0.80を選んだ（docs/experiments/2026-11-22-segment-merge.md）。
SEGMENT_MERGE_MIN_READING_SIMILARITY = 0.80


@dataclass
class _Session:
    """1回の録音の区間、認識結果、終了状態を保持する。"""

    session_id: str
    app_name: str | None
    glossary: list[GlossaryEntry]
    screen_text: str = ""
    screen_glossary: list[GlossaryEntry] = field(default_factory=list)
    seen_seq: set[int] = field(default_factory=set)
    texts: dict[int, str] = field(default_factory=dict)
    selection_texts: dict[int, str] = field(default_factory=dict)
    # 整形へ複数のASR結果を渡す形式（formatter_input="d"）で使う、区間ごとの1回目と補助ASRの文。
    first_texts: dict[int, str] = field(default_factory=dict)
    aux_texts: dict[int, str] = field(default_factory=dict)
    pending: int = 0
    finish_at: float | None = None
    asr_done_at: float | None = None
    mode: str | None = None
    cancelled: bool = False
    finalizing: bool = False


@dataclass(frozen=True)
class _SegmentJob:
    """ASR workerへ渡す区間と、それを所有するセッション。"""

    session: _Session
    seq: int
    wav_path: Path


@dataclass(frozen=True)
class _FinalizeJob:
    """区間の無いセッションをworker側で整形・出力する要求。"""

    session: _Session


@dataclass(frozen=True)
class MergedEdit:
    """2回目の差分区間と、採否の根拠を記録する。"""

    first_start: int
    first_end: int
    second_start: int
    second_end: int
    old_text: str
    new_text: str
    candidate_surface: str | None
    reading_similarity: float | None
    match_basis: str | None
    accepted: bool
    rejection_reason: str | None


@dataclass(frozen=True)
class MergedTranscription:
    """採用した2回目の差分と、1回目を残した区間を含む結合結果。"""

    text: str
    edits: tuple[MergedEdit, ...]


# 整形LLMへ渡す入力の形式。"text"は採否後の1文だけ（第2弾までのモデル）、
# "d"は1回目・採否後・補助ASRの3つ（補助ASRの仮説も入力にして学習したモデル）。
FORMATTER_INPUTS = ("text", "d")


class TwoPassResult(tuple):
    """two-passの1回目と最終結果を2要素タプルとして保ち、補助仮説と選択用文字列を添える。

    既存の呼び出し側（2要素アンパックや添字参照）を壊さず、
    補助ASRの仮説と整形の用語選択に再利用する合併文字列を返すために使う。
    """

    aux_text: str | None
    selection_text: str

    def __new__(
        cls,
        first_pass: Transcription,
        final: Transcription,
        aux_text: str | None = None,
        selection_text: str | None = None,
    ) -> TwoPassResult:
        instance = super().__new__(cls, (first_pass, final))
        instance.aux_text = aux_text
        instance.selection_text = (
            first_pass.text if selection_text is None else selection_text
        )
        return instance

    @property
    def first_pass(self) -> Transcription:
        """ヒント無しの1回目の認識結果を返す。"""
        return self[0]

    @property
    def final(self) -> Transcription:
        """two-pass後の最終の認識結果を返す。"""
        return self[1]

    def __repr__(self) -> str:
        return (
            f"TwoPassResult(first_pass={self[0]!r}, final={self[1]!r}, "
            f"aux_text={self.aux_text!r}, selection_text={self.selection_text!r})"
        )


def _merge_selection_text(primary_text: str, aux_text: str | None) -> str:
    """用語選択の入力文字列を作る。補助仮説があれば改行でつなぎ、無ければ元の文を返す。"""
    if aux_text and aux_text.strip():
        return f"{primary_text}\n{aux_text}"
    return primary_text


def _normalize_merge_text_with_offsets(
    text: str,
) -> tuple[str, tuple[int, ...], tuple[int, ...]]:
    """比較用文字列と各文字の元位置を作り、分割後の置換位置を復元する。"""
    normalized_chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for index, character in enumerate(text):
        normalized = to_katakana(unicodedata.normalize("NFKC", character)).casefold()
        for normalized_char in normalized:
            if normalized_char.isspace() or unicodedata.category(normalized_char)[0] in {"P", "S"}:
                continue
            normalized_chars.append(normalized_char)
            starts.append(index)
            ends.append(index + 1)
    return "".join(normalized_chars), tuple(starts), tuple(ends)


def _surface_occurrences(
    text: str, hinted_entries: list[GlossaryEntry]
) -> list[tuple[int, int, int, int, GlossaryEntry]]:
    """2回目の差分内でヒント表記を探し、正規化位置と元位置を返す。"""
    normalized, starts, ends = _normalize_merge_text_with_offsets(text)
    matches: list[tuple[int, int, int, int, int, GlossaryEntry]] = []
    for order, entry in enumerate(hinted_entries):
        surface = _normalize_merge_text_with_offsets(entry.surface)[0]
        if len(surface) < 2:
            continue
        offset = 0
        while (start := normalized.find(surface, offset)) >= 0:
            end = start + len(surface)
            matches.append(
                (starts[start], ends[end - 1], start, end, order, entry)
            )
            offset = end

    selected: list[tuple[int, int, int, int, GlossaryEntry]] = []
    last_normalized_end = -1
    for raw_start, raw_end, start, end, _, entry in sorted(
        matches, key=lambda match: (match[0], -(match[3] - match[2]), match[4])
    ):
        if start < last_normalized_end:
            continue
        selected.append((raw_start, raw_end, start, end, entry))
        last_normalized_end = end
    return selected


def _merge_case_only_hint_surfaces(
    old_text: str,
    new_text: str,
    first_offset: int,
    second_offset: int,
    hinted_entries: list[GlossaryEntry],
) -> tuple[str, list[MergedEdit]]:
    """英字の大小文字だけが変わった区間は、ヒント語の表記部分だけ更新する。"""
    normalized_old, old_starts, old_ends = _normalize_merge_text_with_offsets(old_text)
    normalized_new, new_starts, new_ends = _normalize_merge_text_with_offsets(new_text)
    replacements: list[tuple[int, int, int, int, GlossaryEntry]] = []
    last_normalized_end = 0
    for _, _, normalized_start, normalized_end, entry in _surface_occurrences(
        new_text, hinted_entries
    ):
        surface = _normalize_merge_text_with_offsets(entry.surface)[0]
        if (
            normalized_start < last_normalized_end
            or normalized_old[normalized_start:normalized_end] != surface
            or normalized_new[normalized_start:normalized_end] != surface
        ):
            continue
        old_start = old_starts[normalized_start]
        old_end = old_ends[normalized_end - 1]
        new_start = new_starts[normalized_start]
        new_end = new_ends[normalized_end - 1]
        if old_text[old_start:old_end] == new_text[new_start:new_end]:
            continue
        replacements.append((old_start, old_end, new_start, new_end, entry))
        last_normalized_end = normalized_end

    if not replacements:
        return old_text, []
    parts: list[str] = []
    edits: list[MergedEdit] = []
    old_cursor = 0
    for old_start, old_end, new_start, new_end, entry in replacements:
        parts.append(old_text[old_cursor:old_start])
        parts.append(new_text[new_start:new_end])
        edits.append(
            MergedEdit(
                first_offset + old_start,
                first_offset + old_end,
                second_offset + new_start,
                second_offset + new_end,
                old_text[old_start:old_end],
                new_text[new_start:new_end],
                entry.surface,
                None,
                "surface",
                True,
                None,
            )
        )
        old_cursor = old_end
    parts.append(old_text[old_cursor:])
    return "".join(parts), edits


def _best_reading_span(
    old_normalized: str,
    starts_at: int,
    entry: GlossaryEntry,
    old_text: str,
    old_starts: tuple[int, ...],
    old_ends: tuple[int, ...],
    source_text: str,
    source_offset: int,
) -> tuple[int, int, float] | None:
    """元区間で候補語の読みと最も近い連続範囲を探す。"""
    best: tuple[int, int, float] | None = None
    for reading in entry.readings:
        normalized_reading = _normalize_merge_text_with_offsets(reading)[0]
        if not normalized_reading:
            continue
        if len(normalize_kana(reading)) <= 2:
            for match in find_short_reading_matches(
                reading, source_text, SEGMENT_MERGE_MIN_READING_SIMILARITY * 100
            ):
                local_start = match.start - source_offset
                local_end = match.end - source_offset
                if local_start < 0 or local_end > len(old_text):
                    continue
                normalized_positions = [
                    index
                    for index, (raw_start, raw_end) in enumerate(zip(old_starts, old_ends))
                    if raw_start >= local_start and raw_end <= local_end
                ]
                if not normalized_positions or normalized_positions[0] < starts_at:
                    continue
                candidate = (
                    normalized_positions[0],
                    normalized_positions[-1] + 1,
                    match.score / 100.0,
                )
                if best is None or candidate[2] > best[2]:
                    best = candidate
            continue
        minimum_length = max(
            1,
            math.ceil(len(normalized_reading) * SEGMENT_MERGE_MIN_READING_SIMILARITY),
        )
        maximum_length = math.floor(
            len(normalized_reading) / SEGMENT_MERGE_MIN_READING_SIMILARITY
        )
        for start in range(starts_at, len(old_normalized)):
            for length in range(
                minimum_length,
                min(maximum_length, len(old_normalized) - start) + 1,
            ):
                end = start + length
                similarity = Levenshtein.normalized_similarity(
                    old_normalized[start:end], normalized_reading
                )
                if best is None or similarity > best[2] or (
                    similarity == best[2] and (start, abs(length - len(normalized_reading)))
                    < (best[0], abs((best[1] - best[0]) - len(normalized_reading)))
                ):
                    best = (start, end, similarity)
    return best


def merge_two_pass_text(
    first_text: str, second_text: str, hinted_entries: list[GlossaryEntry]
) -> MergedTranscription:
    """差分区間内で読みと対応したヒント語だけ置き換え、残りは1回目を残す。"""
    # ASCII英字の大小文字だけを等価にして、surfaceのcase修正を分割しない。
    first_key = "".join(
        chr(ord(character) + 32) if "A" <= character <= "Z" else character
        for character in first_text
    )
    second_key = "".join(
        chr(ord(character) + 32) if "A" <= character <= "Z" else character
        for character in second_text
    )
    matcher = SequenceMatcher(None, first_key, second_key, autojunk=False)
    merged_parts: list[str] = []
    edits: list[MergedEdit] = []
    for tag, first_start, first_end, second_start, second_end in matcher.get_opcodes():
        if tag == "equal":
            old_text = first_text[first_start:first_end]
            new_text = second_text[second_start:second_end]
            if old_text == new_text:
                merged_parts.append(old_text)
                continue
            case_merged, case_edits = _merge_case_only_hint_surfaces(
                old_text,
                new_text,
                first_start,
                second_start,
                hinted_entries,
            )
            merged_parts.append(case_merged)
            edits.extend(case_edits)
            continue

        old_text = first_text[first_start:first_end]
        new_text = second_text[second_start:second_end]
        normalized_old, old_starts, old_ends = _normalize_merge_text_with_offsets(old_text)
        surface_matches = _surface_occurrences(new_text, hinted_entries)
        accepted_spans: list[
            tuple[int, int, int, int, GlossaryEntry, float | None, str]
        ] = []
        old_cursor = 0
        for new_start, new_end, _, _, entry in surface_matches:
            normalized_surface = _normalize_merge_text_with_offsets(entry.surface)[0]
            surface_start = normalized_old.find(normalized_surface, old_cursor)
            if surface_start >= 0:
                surface_end = surface_start + len(normalized_surface)
                accepted_spans.append(
                    (
                        old_starts[surface_start],
                        old_ends[surface_end - 1],
                        new_start,
                        new_end,
                        entry,
                        None,
                        "surface",
                    )
                )
                old_cursor = surface_end
                continue
            match = _best_reading_span(
                normalized_old,
                old_cursor,
                entry,
                old_text,
                old_starts,
                old_ends,
                first_text,
                first_start,
            )
            if match is None or match[2] < SEGMENT_MERGE_MIN_READING_SIMILARITY:
                continue
            normalized_start_old, normalized_end_old, similarity = match
            old_raw_start = old_starts[normalized_start_old]
            old_raw_end = old_ends[normalized_end_old - 1]
            accepted_spans.append(
                (
                    old_raw_start,
                    old_raw_end,
                    new_start,
                    new_end,
                    entry,
                    similarity,
                    "reading",
                )
            )
            old_cursor = normalized_end_old

        if not accepted_spans:
            merged_parts.append(old_text)
            if _normalize_merge_text_with_offsets(old_text)[0] != _normalize_merge_text_with_offsets(new_text)[0]:
                best_surface = surface_matches[0][4].surface if surface_matches else None
                best_similarity = None
                if surface_matches and normalized_old:
                    candidate_span = _best_reading_span(
                        normalized_old,
                        0,
                        surface_matches[0][4],
                        old_text,
                        old_starts,
                        old_ends,
                        first_text,
                        first_start,
                    )
                    best_similarity = candidate_span[2] if candidate_span else None
                reason = (
                    "ヒント語に読みがない"
                    if best_surface and not surface_matches[0][4].readings
                    else "元区間が読みから遠い"
                    if best_surface and best_similarity is not None
                    else "ヒント表記と読みが対応しない"
                )
                edits.append(
                    MergedEdit(
                        first_start,
                        first_end,
                        second_start,
                        second_end,
                        old_text,
                        new_text,
                        best_surface,
                        best_similarity,
                        None,
                        False,
                        reason,
                    )
                )
            continue

        merged_text_parts: list[str] = []
        old_raw_cursor = new_raw_cursor = 0
        old_residual_parts: list[str] = []
        new_residual_parts: list[str] = []
        for old_start, old_end, new_start, new_end, entry, similarity, match_basis in accepted_spans:
            old_residual_parts.append(old_text[old_raw_cursor:old_start])
            new_residual_parts.append(new_text[new_raw_cursor:new_start])
            merged_text_parts.append(old_text[old_raw_cursor:old_start])
            merged_text_parts.append(new_text[new_start:new_end])
            edits.append(
                MergedEdit(
                    first_start + old_start,
                    first_start + old_end,
                    second_start + new_start,
                    second_start + new_end,
                    old_text[old_start:old_end],
                    new_text[new_start:new_end],
                    entry.surface,
                    similarity,
                    match_basis,
                    True,
                    None,
                )
            )
            old_raw_cursor = old_end
            new_raw_cursor = new_end
        old_residual_parts.append(old_text[old_raw_cursor:])
        new_residual_parts.append(new_text[new_raw_cursor:])
        merged_text_parts.append(old_text[old_raw_cursor:])
        merged_parts.append("".join(merged_text_parts))
        old_residual = "".join(old_residual_parts)
        new_residual = "".join(new_residual_parts)
        if _normalize_merge_text_with_offsets(old_residual)[0] != _normalize_merge_text_with_offsets(new_residual)[0]:
            edits.append(
                MergedEdit(
                    first_start,
                    first_end,
                    second_start,
                    second_end,
                    old_residual,
                    new_residual,
                    None,
                    None,
                    None,
                    False,
                    "ヒント語の読みと対応する差分以外",
                )
            )
    return MergedTranscription("".join(merged_parts), tuple(edits))


class RecognitionEngine:
    """ASRと整形器を直列workerで動かし、セッションごとの結果をJSON Linesで返す。"""

    def __init__(
        self,
        transcriber: Transcriber,
        glossary: list[GlossaryEntry],
        formatter_kind: str,
        formatter: object | None,
        history_path: str | Path,
        asr_name: str,
        formatter_name: str,
        asr_accepts_glossary: bool,
        asr_hint_mode: str = "two-pass",
        asr_hint_format: str = "surface",
        audio_loader: Callable[[Path], np.ndarray] = load_audio,
        two_pass_policy: str = "always",
        aux_transcriber: Transcriber | None = None,
        formatter_input: str = "text",
        formatter_max_glossary: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        """既存のASR・formatterと入出力先を受け取る。

        履歴はセッション処理の前に本人だけが読める権限で準備する。
        """
        if formatter_kind not in {"rules", "none", "model"}:
            raise ValueError(f"formatter_kindが不正: {formatter_kind}")
        if formatter_kind == "model" and formatter is None:
            raise ValueError("formatter_kind=modelにはformatterが必要")
        if asr_hint_mode not in {"none", "static", "two-pass"}:
            raise ValueError(f"asr_hint_modeが不正: {asr_hint_mode}")
        if asr_hint_format not in {"surface", "surface-reading"}:
            raise ValueError(f"asr_hint_formatが不正: {asr_hint_format}")
        if two_pass_policy not in TWO_PASS_POLICIES:
            raise ValueError(f"two_pass_policyが不正: {two_pass_policy}")
        self.transcriber = transcriber
        self.glossary = glossary
        self.glossary_index = GlossaryIndex(glossary)
        self.formatter_kind = formatter_kind
        self.formatter = formatter
        self.history_path = Path(history_path)
        self.asr_name = asr_name
        self.formatter_name = formatter_name
        self.asr_accepts_glossary = asr_accepts_glossary
        self.asr_hint_mode = asr_hint_mode
        self.asr_hint_format = asr_hint_format
        self.two_pass_policy = two_pass_policy
        self.audio_loader = audio_loader
        self.aux_transcriber = aux_transcriber
        if formatter_input not in FORMATTER_INPUTS:
            raise ValueError(f"formatter_inputは{FORMATTER_INPUTS}のいずれか: {formatter_input}")
        if formatter_input == "d" and aux_transcriber is None:
            raise ValueError("formatter_input='d'には補助ASR（aux_transcriber）が必要です")
        self.formatter_input = formatter_input
        if formatter_max_glossary < 1:
            raise ValueError(f"formatter_max_glossaryは1以上: {formatter_max_glossary}")
        # 整形LLMへ渡す用語一覧の上限件数。
        self.formatter_max_glossary = formatter_max_glossary
        self._sessions: dict[str, _Session] = {}
        self._state_lock = threading.RLock()
        self._output_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._jobs: queue.Queue[_SegmentJob | _FinalizeJob | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._transcriber_closed = False
        self._output: TextIO | None = None
        self._prepare_history()

    def _prepare_history(self) -> None:
        """履歴ファイルを作成し、既存ファイルも本人だけが読める0600へ揃える。"""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.history_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

    def warm_up(self) -> None:
        """readyを出す前にASRと、選択された整形器の初回推論を実行する。"""
        audio = np.zeros(16000, dtype=np.float32)
        with redirect_stdout(sys.stderr):
            self.transcriber.transcribe(audio, None)
            if self.aux_transcriber is not None:
                try:
                    self.aux_transcriber.transcribe(audio, None)
                except Exception:
                    logger.warning(
                        "補助ASRのwarm-upに失敗したため補助なしで続けます",
                        exc_info=True,
                    )
            if self.formatter_kind == "rules":
                format_with_rules("音声入力", self.glossary)
            elif self.formatter_kind == "model":
                self.formatter.format("音声入力", [])

    def serve(self, source: Iterable[str], output: TextIO) -> None:
        """warm-up後にreadyを返し、入力を処理してworkerの結果をすべて出力する。"""
        self._output = output
        try:
            self.warm_up()
            self._write_event({"type": "ready", "asr": self.asr_name, "formatter": self.formatter_name})
            self._worker = threading.Thread(target=self._work, name="voiceime-asr", daemon=True)
            self._worker.start()
            for line in source:
                if self.handle_line(line):
                    break
        finally:
            self.close()

    def handle_line(self, line: str) -> bool:
        """JSON Linesの1件を検証して処理し、shutdownならTrueを返す。"""
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            self._write_event({"type": "error", "message": f"JSONを読めない: {error.msg}"})
            return False
        if not isinstance(message, dict):
            self._write_event({"type": "error", "message": "要求はJSON objectで指定する"})
            return False

        message_type = message.get("type")
        if message_type == "start":
            self._start_session(message)
        elif message_type == "segment":
            self._enqueue_segment(message)
        elif message_type == "finish":
            self._finish_session(message)
        elif message_type == "cancel":
            self._cancel_session(message)
        elif message_type == "shutdown":
            return True
        else:
            self._write_event({"type": "error", "message": f"未知の要求type: {message_type!r}"})
        return False

    def close(self) -> None:
        """未完了セッションを破棄し、finish済みの要求を完了してworkerを閉じる。"""
        with self._state_lock:
            for session_id, session in list(self._sessions.items()):
                if session.finish_at is None:
                    session.cancelled = True
                    del self._sessions[session_id]
        if self._worker is not None:
            self._jobs.join()
            self._jobs.put(None)
            self._worker.join()
            self._worker = None
        if not self._transcriber_closed:
            self._transcriber_closed = True
            for label, target in (("ASR", self.transcriber), ("補助ASR", self.aux_transcriber)):
                close_transcriber = getattr(target, "close", None)
                if callable(close_transcriber):
                    try:
                        with redirect_stdout(sys.stderr):
                            close_transcriber()
                    except Exception:
                        logger.exception("%s workerを終了できませんでした", label)

    def _start_session(self, message: dict) -> None:
        """新しい録音セッションを登録し、同じIDの古い処理があれば無効化する。"""
        session_id = message.get("session_id")
        app = message.get("app")
        if not isinstance(session_id, str) or not session_id:
            self._write_event({"type": "error", "message": "startにはsession_idが必要"})
            return
        app_name = app.get("name") if isinstance(app, dict) and isinstance(app.get("name"), str) else None
        screen_text = message.get("screen_text")
        if not isinstance(screen_text, str):
            screen_text = ""
        screen_text = screen_text[:SCREEN_TEXT_MAX_CHARS]
        screen_glossary = select_screen_glossary(screen_text, self.glossary)
        with self._state_lock:
            previous = self._sessions.get(session_id)
            if previous is not None:
                previous.cancelled = True
            self._sessions[session_id] = _Session(
                session_id,
                app_name,
                self.glossary,
                screen_text=screen_text,
                screen_glossary=screen_glossary,
            )

    def _enqueue_segment(self, message: dict) -> None:
        """区間をセッションへ登録し、ASR workerへ順次送る。"""
        session_id = message.get("session_id")
        session = self._session_for_message(session_id)
        if session is None:
            return
        seq = message.get("seq")
        wav_path = message.get("wav_path")
        if (
            isinstance(seq, bool)
            or not isinstance(seq, int)
            or seq < 0
            or not isinstance(wav_path, str)
            or not wav_path.strip()
        ):
            self._write_session_error(session, "segmentには0以上のseqとwav_pathが必要")
            return
        with self._state_lock:
            if session.cancelled or self._sessions.get(session_id) is not session:
                return
            if session.finish_at is not None:
                self._write_session_error(session, "finish後にsegmentを受け取った")
                return
            if seq in session.seen_seq:
                self._write_session_error(session, f"seqが重複している: {seq}")
                return
            session.seen_seq.add(seq)
            session.pending += 1
            session.asr_done_at = None
            self._jobs.put(_SegmentJob(session, seq, Path(wav_path)))

    def _finish_session(self, message: dict) -> None:
        """終了時刻とmodeを保存し、全区間が終わった時点で結果作成を予約する。"""
        session_id = message.get("session_id")
        session = self._session_for_message(session_id)
        if session is None:
            return
        mode = message.get("mode")
        if not isinstance(mode, str) or mode not in {"formatted", "raw"}:
            self._write_session_error(session, "finishのmodeはformattedまたはraw")
            return
        should_finalize = False
        with self._state_lock:
            if session.cancelled or self._sessions.get(session_id) is not session:
                return
            if session.finish_at is not None:
                self._write_session_error(session, "finishを複数回受け取った")
                return
            if session.seen_seq != set(range(len(session.seen_seq))):
                self._write_session_error(session, "seqは0から始まる連番で指定する")
                return
            session.finish_at = time.perf_counter()
            session.mode = mode
            if session.pending == 0:
                session.finalizing = True
                should_finalize = True
        if should_finalize:
            self._jobs.put(_FinalizeJob(session))

    def _cancel_session(self, message: dict) -> None:
        """指定セッションを無効化し、進行中のASR結果や整形結果を破棄する。"""
        session_id = message.get("session_id")
        session = self._session_for_message(session_id)
        if session is None:
            return
        with self._state_lock:
            session.cancelled = True
            if self._sessions.get(session_id) is session:
                del self._sessions[session_id]

    def _session_for_message(self, session_id: object) -> _Session | None:
        """session_idを確認し、現在処理中のセッションを返す。"""
        if not isinstance(session_id, str) or not session_id:
            self._write_event({"type": "error", "message": "要求にsession_idが必要"})
            return None
        with self._state_lock:
            session = self._sessions.get(session_id)
        if session is None:
            self._write_event(
                {"type": "error", "session_id": session_id, "message": "startされていないsession_id"}
            )
        return session

    def _work(self) -> None:
        """区間を到着順に認識し、完了区間とセッション結果を排他して出力する。"""
        while True:
            job = self._jobs.get()
            try:
                if job is None:
                    return
                if isinstance(job, _FinalizeJob):
                    self._finalize_session(job.session)
                    continue
                self._transcribe_segment(job)
            finally:
                self._jobs.task_done()

    def _transcribe_segment(self, job: _SegmentJob) -> None:
        """WAV区間を読み取って認識し、seqに対応するpartialと結果を記録する。"""
        session = job.session
        with self._state_lock:
            if session.cancelled or self._sessions.get(session.session_id) is not session:
                session.pending -= 1
                return
        try:
            audio = self.audio_loader(job.wav_path)
            with redirect_stdout(sys.stderr):
                transcription, selection_text, first_text, aux_text = self._transcribe_with_hints(
                    audio, session.glossary, session.screen_glossary
                )
            if not isinstance(transcription.text, str):
                raise TypeError("ASRの結果textは文字列ではない")
        except Exception as error:
            logger.exception("区間認識に失敗しました: session=%s seq=%d", session.session_id, job.seq)
            with self._state_lock:
                session.pending -= 1
                if not session.cancelled and self._sessions.get(session.session_id) is session:
                    session.cancelled = True
                    del self._sessions[session.session_id]
                    self._write_event(
                        {"type": "error", "session_id": session.session_id, "message": str(error)}
                    )
            return

        should_finalize = False
        with self._state_lock:
            session.pending -= 1
            if session.cancelled or self._sessions.get(session.session_id) is not session:
                return
            session.texts[job.seq] = transcription.text
            if selection_text is not None:
                session.selection_texts[job.seq] = selection_text
            if first_text is not None:
                session.first_texts[job.seq] = first_text
            if aux_text is not None:
                session.aux_texts[job.seq] = aux_text
            if session.pending == 0:
                session.asr_done_at = time.perf_counter()
            self._write_event(
                {"type": "partial", "session_id": session.session_id, "seq": job.seq, "text": transcription.text}
            )
            if session.finish_at is not None and session.pending == 0 and not session.finalizing:
                session.finalizing = True
                should_finalize = True
        if should_finalize:
            self._finalize_session(session)

    def _finalize_session(self, session: _Session) -> None:
        """seq順に結合し、必要なら整形・検査して履歴とresultを出力する。"""
        with self._state_lock:
            if session.cancelled or self._sessions.get(session.session_id) is not session:
                return
            if session.finish_at is None or session.pending:
                return
            finish_at = session.finish_at
            ordered_seqs = sorted(session.texts)
            raw_text = "".join(session.texts[seq] for seq in ordered_seqs)
            glossary_selection_text = (
                "\n".join(
                    session.selection_texts.get(seq, session.texts[seq])
                    for seq in ordered_seqs
                )
                if session.selection_texts
                else raw_text
            )
            formatter_input = self._formatter_input(session, ordered_seqs, raw_text)
            asr_done_at = session.asr_done_at or time.perf_counter()

        if session.mode == "raw" or self.formatter_kind == "none":
            formatted_text, format_ok = raw_text, True
            format_latency = 0.0
        else:
            format_started = time.perf_counter()
            formatted_text, format_ok = self._format_text(
                raw_text,
                session.glossary,
                session.mode or "formatted",
                session.screen_glossary,
                selection_text=glossary_selection_text,
                formatter_input=formatter_input,
            )
            format_latency = time.perf_counter() - format_started
        asr_latency = max(0.0, asr_done_at - finish_at)

        with self._state_lock:
            if session.cancelled or self._sessions.get(session.session_id) is not session:
                return
            event = {
                "type": "result",
                "session_id": session.session_id,
                "raw_text": raw_text,
                "text": formatted_text,
                "format_ok": format_ok,
                "asr_latency_s": asr_latency,
                "format_latency_s": format_latency,
                "total_latency_s": max(0.0, time.perf_counter() - finish_at),
            }
            try:
                self._append_history(
                    {
                        "raw_text": raw_text,
                        "text": formatted_text,
                        "format_ok": format_ok,
                        "asr_latency_s": event["asr_latency_s"],
                        "format_latency_s": event["format_latency_s"],
                        "total_latency_s": event["total_latency_s"],
                        "app_name": session.app_name,
                    }
                )
            except OSError as error:
                logger.exception("履歴を書けません: %s", self.history_path)
                session.cancelled = True
                del self._sessions[session.session_id]
                self._write_event(
                    {"type": "error", "session_id": session.session_id, "message": f"履歴を書けない: {error}"}
                )
                return
            self._write_event(event)
            del self._sessions[session.session_id]

    def _formatter_input(
        self, session: _Session, ordered_seqs: list[int], raw_text: str
    ) -> FormatterInput | None:
        """整形へ複数のASR結果を渡す形式のときだけ、1回目・採否後・補助ASRの文をまとめて返す。

        学習時と同じ3つの欄（1回目、区間ごとの採否後、補助ASR）を作る。補助ASRが失敗した区間は空として扱う。
        """
        if self.formatter_input != "d" or not session.first_texts:
            return None
        aux_text = "".join(session.aux_texts.get(seq, "") for seq in ordered_seqs)
        return FormatterInput(
            first_pass="".join(session.first_texts.get(seq, session.texts[seq]) for seq in ordered_seqs),
            combined_text=raw_text,
            qwen_hypothesis=aux_text or None,
        )

    def _format_text(
        self,
        raw_text: str,
        glossary: list[GlossaryEntry],
        mode: str,
        screen_glossary: list[GlossaryEntry] | None = None,
        selection_text: str | None = None,
        formatter_input: FormatterInput | None = None,
    ) -> tuple[str, bool]:
        """raw modeまたは無効な整形結果を原文へ戻し、有効な文にだけ確定置換を行う。"""
        if mode == "raw" or self.formatter_kind == "none":
            return raw_text, True
        try:
            alias_entries: dict[str, GlossaryEntry] = {}

            def replace_aliases(text: str) -> str:
                """整形に渡す文を置換し、一致した用語を一覧の先頭に置けるよう集める。"""
                replaced, matches = self.glossary_index.replace_aliases(text)
                for entry in matches:
                    alias_entries.setdefault(entry.surface, entry)
                return replaced

            format_text = replace_aliases(raw_text)
            with redirect_stdout(sys.stderr):
                if self.formatter_kind == "rules":
                    candidate = format_with_rules(format_text, glossary)
                else:
                    if formatter_input is not None:
                        fields = {}
                        for name in ("first_pass", "combined_text", "qwen_hypothesis", "second_pass"):
                            text = getattr(formatter_input, name)
                            if text is not None:
                                fields[name] = format_text if text == raw_text else replace_aliases(text)
                        formatter_input = replace(formatter_input, **fields)
                    selection_text = (
                        format_text if selection_text is None or selection_text == raw_text
                        else replace_aliases(selection_text)
                    )
                    selected = select_glossary_with_priority(
                        selection_text,
                        glossary,
                        screen_glossary or [],
                        self.formatter_max_glossary,
                        selection_index=self.glossary_index,
                        alias_entries=list(alias_entries.values()),
                    )
                    result = self.formatter.format(
                        format_text if formatter_input is None else formatter_input, selected
                    )
                    if getattr(result, "finish_reason", None) == "repetition":
                        logger.warning(
                            "整形出力の生成を繰り返しで打ち切り、認識結果を使います"
                        )
                        return raw_text, False
                    candidate = result.text if hasattr(result, "text") else result
            candidate = apply_confirmed_replacements(candidate, glossary)
            if not isinstance(candidate, str) or not is_valid_output(format_text, candidate):
                logger.warning("整形出力を検査で拒否し、認識結果を使います")
                return raw_text, False
            return candidate, True
        except Exception:
            logger.exception("整形に失敗し、認識結果を使います")
            return raw_text, False

    def _run_with_aux(
        self,
        primary_fn: Callable[[], Transcription],
        audio: np.ndarray,
    ) -> tuple[Transcription, str | None]:
        """主ASRと補助ASRをスレッドで同時実行し、補助ASRの失敗時は警告のみ出して続行する。"""
        assert self.aux_transcriber is not None
        primary_box: dict[str, object] = {}

        def run_primary() -> None:
            try:
                primary_box["result"] = primary_fn()
            except BaseException as error:
                primary_box["error"] = error

        thread = threading.Thread(target=run_primary, name="voiceime-primary-asr")
        thread.start()
        aux_text: str | None = None
        try:
            # speech.cppの主ASRは別プロセスI/O待ちのため子スレッドで動かし、
            # MLXの補助ASRは整形器と同じworkerスレッド上で実行する。
            aux_result = self.aux_transcriber.transcribe(audio, None)
            if not isinstance(aux_result.text, str):
                raise TypeError("補助ASRの結果textは文字列ではない")
            aux_text = aux_result.text
        except Exception:
            logger.warning(
                "補助ASRの認識に失敗したため補助なしで続けます",
                exc_info=True,
            )
        finally:
            thread.join()

        if "error" in primary_box:
            raise primary_box["error"]  # type: ignore[misc]
        return primary_box["result"], aux_text  # type: ignore[return-value]

    def _transcribe_with_hints(
        self,
        audio: np.ndarray,
        glossary: list[GlossaryEntry],
        screen_glossary: list[GlossaryEntry] | None = None,
    ) -> tuple[Transcription, str | None, str | None, str | None]:
        """none、static、two-passの選択に従い、区間を0回または1回だけ追加認識する。

        返り値は、最終の認識結果、用語選択に使う合併文字列、ヒント無しの1回目の文、補助ASRの文。
        後ろの3つは、該当する処理をしなかった場合はNone。
        """
        mode = self.asr_hint_mode if self.asr_accepts_glossary else "none"
        if self.aux_transcriber is None and mode != "two-pass":
            return (
                transcribe_with_hints(
                    self.transcriber,
                    audio,
                    glossary,
                    mode,
                    self.asr_hint_format,
                    screen_glossary,
                    two_pass_policy=self.two_pass_policy,
                    selection_index=self.glossary_index,
                ),
                None,
                None,
                None,
            )
        if mode == "none":
            primary, aux_text = self._run_with_aux(
                lambda: self.transcriber.transcribe(audio, None),
                audio,
            )
            if not isinstance(primary.text, str):
                raise TypeError("ASRの結果textは文字列ではない")
            selection_text = (
                _merge_selection_text(primary.text, aux_text)
                if aux_text and aux_text.strip()
                else None
            )
            return primary, selection_text, None, aux_text
        if mode == "static":
            hints = asr_hints(glossary, self.asr_hint_format)
            primary, aux_text = self._run_with_aux(
                lambda: self.transcriber.transcribe(audio, hints),
                audio,
            )
            if not isinstance(primary.text, str):
                raise TypeError("ASRの結果textは文字列ではない")
            selection_text = (
                _merge_selection_text(primary.text, aux_text)
                if aux_text and aux_text.strip()
                else None
            )
            return primary, selection_text, None, aux_text
        first_pass, aux_text = (
            (self.transcriber.transcribe(audio, None), None)
            if self.aux_transcriber is None
            else self._run_with_aux(lambda: self.transcriber.transcribe(audio, None), audio)
        )
        result = transcribe_two_pass(
            self.transcriber,
            audio,
            glossary,
            self.asr_hint_format,
            screen_glossary,
            two_pass_policy=self.two_pass_policy,
            selection_index=self.glossary_index,
            aux_text=aux_text,
            first_pass=first_pass,
        )
        selection_text = None
        if aux_text and aux_text.strip():
            selection_text = result.selection_text
        elif self.glossary_index.replace_aliases(first_pass.text)[1]:
            # 補助仮説がなくても、1回目だけに現れた別名を整形の用語選択へ引き継ぐ。
            selection_text = _merge_selection_text(first_pass.text, result.final.text)
        return result.final, selection_text, first_pass.text if self.aux_transcriber else None, aux_text

    def _asr_hints(self, glossary: list[GlossaryEntry]) -> list[Term] | None:
        """用語のsurfaceと最初のreadingを最大16語・240文字までASRへ渡す。"""
        return asr_hints(glossary, self.asr_hint_format)

    def _append_history(self, row: dict) -> None:
        """JSONL履歴を0600のまま追記する。"""
        line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        with self._history_lock:
            descriptor = os.open(
                self.history_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                os.fchmod(descriptor, 0o600)
                remaining = memoryview(line)
                while remaining:
                    written = os.write(descriptor, remaining)
                    remaining = remaining[written:]
            finally:
                os.close(descriptor)

    def _write_session_error(self, session: _Session, message: str) -> None:
        """壊れた要求の対象セッションを破棄してerrorを返す。

        既にキューへ入った区間も、破棄済みセッションとしてworkerに無視させる。
        """
        with self._state_lock:
            session.cancelled = True
            if self._sessions.get(session.session_id) is session:
                del self._sessions[session.session_id]
            self._write_event({"type": "error", "session_id": session.session_id, "message": message})

    def _write_event(self, event: dict) -> None:
        """標準出力へ1行のJSONイベントだけを書き、複数スレッドの出力を直列化する。"""
        if self._output is None:
            raise RuntimeError("出力先が設定されていない")
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self._output_lock:
            self._output.write(encoded + "\n")
            self._output.flush()


def transcribe_with_hints(
    transcriber: Transcriber,
    audio: np.ndarray,
    glossary: list[GlossaryEntry],
    mode: str,
    hint_format: str,
    screen_glossary: list[GlossaryEntry] | None = None,
    two_pass_policy: str = "always",
    selection_index: GlossaryIndex | None = None,
):
    """用語のヒントの渡し方（none、static、two-pass）に従って1区間を認識する。

    two-passでは、ヒント無しの1回目の結果に近い語を用語集から選び、選べた場合だけヒント付きで認識し直す。
    アプリの認識と評価（`voiceime.asr.run`）で同じ選び方を使うため、ここに1つだけ置く。
    """
    if mode == "none":
        return transcriber.transcribe(audio, None)
    if mode == "static":
        return transcriber.transcribe(audio, asr_hints(glossary, hint_format))
    return transcribe_two_pass(
        transcriber,
        audio,
        glossary,
        hint_format,
        screen_glossary,
        two_pass_policy=two_pass_policy,
        selection_index=selection_index,
    )[1]


def transcribe_two_pass(
    transcriber: Transcriber,
    audio: np.ndarray,
    glossary: list[GlossaryEntry],
    hint_format: str,
    screen_glossary: list[GlossaryEntry] | None = None,
    two_pass_policy: str = "always",
    selection_index: GlossaryIndex | None = None,
    aux_text: str | None = None,
    first_pass: Transcription | None = None,
) -> TwoPassResult:
    """two-passの結果を返す。1回目で語を選べなければ、画面語だけでは再認識しない。

    画面OCRには発話と無関係な語も含まれる。
    画面語だけで全区間を再認識すると遅延が増えるため、1回目の選択語が必要。
    学習データ作りでは1回目の結果も使うため、最初の認識結果は捨てずに返す。
    `aux_text`が与えられた場合は「1回目＋改行＋補助仮説」で用語を選び、
    同じ選択用文字列と補助仮説を返り値へ添える。
    """
    if two_pass_policy not in TWO_PASS_POLICIES:
        raise ValueError(f"two_pass_policyが不正: {two_pass_policy}")
    if aux_text is not None and not isinstance(aux_text, str):
        raise TypeError("補助ASRの結果aux_textは文字列ではない")
    if first_pass is None:
        first_pass = transcriber.transcribe(audio, None)
    if not isinstance(first_pass.text, str):
        raise TypeError("ASRの結果textは文字列ではない")
    selection_text = _merge_selection_text(first_pass.text, aux_text)
    index = selection_index
    if index is None and any(entry.aliases for entry in glossary):
        index = GlossaryIndex(glossary)
    normalized_selection, alias_entries = (
        index.replace_aliases(selection_text) if index is not None else (selection_text, [])
    )
    selected_from_speech = select_glossary(
        normalized_selection,
        glossary,
        selection_index=index,
    )
    if not alias_entries and not selected_from_speech:
        return TwoPassResult(
            first_pass,
            first_pass,
            aux_text=aux_text,
            selection_text=selection_text,
        )
    all_candidates = [*alias_entries, *(screen_glossary or []), *selected_from_speech]
    hints = asr_hints(all_candidates, hint_format)
    if not hints:
        return TwoPassResult(
            first_pass,
            first_pass,
            aux_text=aux_text,
            selection_text=selection_text,
        )
    entries_by_surface: dict[str, GlossaryEntry] = {}
    for entry in all_candidates:
        entries_by_surface.setdefault(entry.surface, entry)
    hinted_entries = [
        entries_by_surface[term.surface]
        for term in hints
        if term.surface in entries_by_surface
    ]
    if two_pass_policy == "reading-near" and max(
        (score_entry_readings(entry, first_pass.text) for entry in hinted_entries),
        default=0.0,
    ) < DEFAULT_MIN_SCORE:
        return TwoPassResult(
            first_pass,
            first_pass,
            aux_text=aux_text,
            selection_text=selection_text,
        )

    second_pass = transcriber.transcribe(audio, hints)
    if two_pass_policy == "segment-merge":
        merged = merge_two_pass_text(
            first_pass.text, second_pass.text, hinted_entries
        )
        return TwoPassResult(
            first_pass,
            replace(second_pass, text=merged.text),
            aux_text=aux_text,
            selection_text=selection_text,
        )
    if two_pass_policy == "no-farther":
        first_score = max(
            (score_entry_in_text(entry, first_pass.text) for entry in hinted_entries),
            default=0.0,
        )
        second_score = max(
            (score_entry_in_text(entry, second_pass.text) for entry in hinted_entries),
            default=0.0,
        )
        if second_score < first_score:
            return TwoPassResult(
                first_pass,
                first_pass,
                aux_text=aux_text,
                selection_text=selection_text,
            )
    return TwoPassResult(
        first_pass,
        second_pass,
        aux_text=aux_text,
        selection_text=selection_text,
    )


def asr_hints(glossary: list[GlossaryEntry], hint_format: str) -> list[Term] | None:
    """用語のsurfaceと最初のreadingを最大16語・240文字までASRへ渡す。"""
    hints: list[Term] = []
    for entry in glossary:
        if any(term.surface == entry.surface for term in hints) or len(hints) >= ASR_GLOSSARY_MAX_TERMS:
            continue
        reading = entry.readings[0] if entry.readings else ""
        if hint_format == "surface-reading" and not reading:
            continue
        candidate = [*hints, Term(entry.surface, reading)]
        if hint_format == "surface-reading":
            joined_length = len("\n".join(f"{term.surface}={term.reading}" for term in candidate))
        else:
            joined_length = len("、".join(term.surface for term in candidate))
        if joined_length <= ASR_GLOSSARY_MAX_CHARS:
            hints.append(candidate[-1])
    return hints or None


def apply_confirmed_replacements(text: str, glossary: list[GlossaryEntry]) -> str:
    """replace_fromに明示された表記だけを、最長一致かつ曖昧な別名を除いて置換する。"""
    targets: dict[str, set[str]] = {}
    for entry in glossary:
        for alias in entry.replace_from:
            if alias:
                targets.setdefault(alias, set()).add(entry.surface)
    replacements = {alias: next(iter(surfaces)) for alias, surfaces in targets.items() if len(surfaces) == 1}
    if not replacements:
        return text
    pattern = re.compile("|".join(re.escape(alias) for alias in sorted(replacements, key=len, reverse=True)))
    return pattern.sub(lambda match: replacements[match.group(0)], text)
