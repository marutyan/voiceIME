#!/usr/bin/env python3
"""YODAS v3.1の投稿者字幕から用語を含む技術文脈の候補を選ぶ。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


# 候補行以外の周辺字幕に現れたとき技術分野を示す強い語。
STRONG_CONTEXT_MARKERS = (
    "プログラミング",
    "ソフトウェア",
    "アルゴリズム",
    "機械学習",
    "人工知能",
    "ニューラル",
    "ソースコード",
    "デバッグ",
    "データベース",
    "ネットワーク",
    "GPU",
    "CPU",
    "ライブラリ",
    "API",
    "サーバー",
    "サーバ",
    "クラウド",
    "コマンド",
    "ターミナル",
    "インストール",
    "関数",
    "変数",
    "ポインタ",
    "メモリ",
    "データ型",
    "Git",
    "GitHub",
    "Docker",
    "Kubernetes",
    "Linux",
    "Windows",
    "Python",
    "JavaScript",
    "C++",
    "レンズ",
    "焦点距離",
    "カメラ",
    "バッテリー",
    "電池",
    "USB",
    "端子",
    "電源",
    "接続",
    "配線",
    "コネクタ",
    "アダプター",
    "LED",
    "液晶",
    "モーター",
    "半導体",
    "電子機器",
    "タンパク質",
    "タンパク",
    "遺伝子",
    "発現",
    "RNA",
    "細胞",
    "組織",
    "解析",
    "電子書籍",
    "フォーマット",
    "規格",
    "アクセシブル",
    "量子コンピュータ",
    "量子コンピューター",
    "量子",
    "宇宙船",
    "ロケット",
    "人工衛星",
    "電圧",
    "電流",
    "電気回路",
    "電子回路",
    "回路基板",
    "周波数",
    "暗号",
    "暗号化",
    "復号",
    "公開鍵",
    "秘密鍵",
    "暗号鍵",
    "インターネット",
    "ウェブ",
    "ブラウザ",
    "アクセシビリティ",
)

# 一語だけでは曖昧なので、2種類以上が周辺字幕にある場合だけ使う語。
BROAD_CONTEXT_MARKERS = (
    "開発",
    "実装",
    "計算",
    "アプリ",
    "コンピュータ",
    "計算機",
    "学習",
    "モデル",
    "設定",
    "技術",
    "通信",
)

# URLのschemeは字幕に書かれても発話された用語とは限らない。
URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)

# 別動画の再現可能な順序で候補を選び、同じ動画の寄与を制限する。
SELECTION_SEED = 0
PUB_EVAL_TERMS = 300
PUB_EVAL_MIN_SEGMENTS = 300
PUB_EVAL_MAX_SEGMENTS = 500
PUB_EVAL_MAX_SEGMENTS_PER_VIDEO = 8
PUB_POOL_MAX_SEGMENTS_PER_VIDEO = 120
PUB_POOL_MAX_TERMS_PER_VIDEO = 170
MIN_CANDIDATE_DURATION_MS = 500
TOTAL_SELECTED_TERMS = 1500


# 同じ英語表記・読みを一度の走査で探し、用語集を全字幕へ繰り返し走査しない。
class GlossaryMatcher:
    """表記と読みの文字列をまとめて照合し、重複しない用語出現を返す。"""

    def __init__(self, glossary: list[dict[str, Any]], excluded: set[str]) -> None:
        """用語表記と読みをトライへ登録し、失敗リンクを構築する。"""
        self.nodes: list[dict[str, int]] = [{}]
        self.failures: list[int] = [0]
        self.outputs: list[list[str]] = [[]]
        self.pattern_forms: dict[str, set[tuple[str, str]]] = defaultdict(set)

        for entry in glossary:
            surface = entry.get("surface")
            readings = entry.get("readings")
            if not isinstance(surface, str) or not surface or surface in excluded:
                continue
            if not isinstance(readings, list):
                continue

            normalized_surface = normalize(surface)
            self.pattern_forms[normalized_surface].add((surface, "surface"))
            for reading in readings:
                if isinstance(reading, str) and reading:
                    self.pattern_forms[normalize(reading)].add((surface, "reading"))

        for pattern in self.pattern_forms:
            state = 0
            for character in pattern:
                next_state = self.nodes[state].get(character)
                if next_state is None:
                    next_state = len(self.nodes)
                    self.nodes[state][character] = next_state
                    self.nodes.append({})
                    self.failures.append(0)
                    self.outputs.append([])
                state = next_state
            self.outputs[state].append(pattern)

        queue = deque(self.nodes[0].values())
        while queue:
            state = queue.popleft()
            for character, child in self.nodes[state].items():
                queue.append(child)
                fallback = self.failures[state]
                while fallback and character not in self.nodes[fallback]:
                    fallback = self.failures[fallback]
                self.failures[child] = self.nodes[fallback].get(character, 0)
                self.outputs[child].extend(self.outputs[self.failures[child]])

    def find(self, text: str) -> tuple[list[dict[str, Any]], int]:
        """字幕1行の表記または読みを最長優先で照合する。"""
        normalized = normalize(text)
        url_spans = [match.span() for match in URL_PATTERN.finditer(normalized)]
        matches: list[tuple[int, int, str, str]] = []
        ambiguous = 0
        state = 0
        for end, character in enumerate(normalized):
            while state and character not in self.nodes[state]:
                state = self.failures[state]
            state = self.nodes[state].get(character, 0)
            for pattern in self.outputs[state]:
                start = end - len(pattern) + 1
                if any(url_start <= start and end + 1 <= url_end for url_start, url_end in url_spans):
                    continue
                if is_ascii_word_pattern(pattern):
                    if start > 0 and is_ascii_word_character(normalized[start - 1]):
                        continue
                    if end + 1 < len(normalized) and is_ascii_word_character(normalized[end + 1]):
                        continue
                forms = self.pattern_forms[pattern]
                exact_surfaces = sorted(
                    {surface for surface, kind in forms if kind == "surface"}
                )
                if len(exact_surfaces) == 1:
                    matches.append((start, end + 1, exact_surfaces[0], "surface"))
                    continue
                if len(exact_surfaces) > 1:
                    ambiguous += 1
                    continue
                reading_surfaces = sorted({surface for surface, _ in forms})
                if len(reading_surfaces) == 1:
                    if is_japanese_reading(pattern) and not is_japanese_reading_boundary(
                        normalized, start, end + 1
                    ):
                        continue
                    matches.append((start, end + 1, reading_surfaces[0], "reading"))
                else:
                    ambiguous += 1

        selected: list[dict[str, Any]] = []
        cursor = -1
        for start, end, surface, kind in sorted(
            matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])
        ):
            if start < cursor:
                continue
            selected.append({"surface": surface, "kind": kind})
            cursor = end
        return selected, ambiguous


# 用語表記を全角英数字などから同じ比較形へそろえる。
def normalize(text: str) -> str:
    """NFKC正規化とcasefoldで表記の幅・大文字小文字をそろえる。"""
    return unicodedata.normalize("NFKC", text).casefold()


# 英語の表記が語の途中へ偶然一致する候補を除く。
def is_ascii_word_pattern(pattern: str) -> bool:
    """ASCII英数字を含む表記かを返す。"""
    return any(is_ascii_word_character(character) for character in pattern)


# ASCIIの英数字の境界だけを英語用語の照合に使う。
def is_ascii_word_character(character: str) -> bool:
    """英語表記の境界判定に使うASCII英数字かを返す。"""
    return character.isascii() and character.isalnum()


# 日本語の読みが別のカタカナ語の一部だけに当たる一致を除く。
def is_japanese_reading(pattern: str) -> bool:
    """かな文字を含む読みかを返す。"""
    return any(
        "HIRAGANA" in unicodedata.name(character, "")
        or "KATAKANA" in unicodedata.name(character, "")
        for character in pattern
    )


# 助詞は語境界として許し、かな・漢字語の途中で終わる読みを除く。
def is_japanese_reading_boundary(text: str, start: int, end: int) -> bool:
    """読みの前後が語の途中でないことを確認する。"""
    particles = set("はがをにでとへもやかの")
    if (
        start > 0
        and is_japanese_word_character(text[start - 1])
        and text[start - 1] not in particles
    ):
        return False
    if (
        end < len(text)
        and is_japanese_word_character(text[end])
        and text[end] not in particles
    ):
        return False
    return True


# 日本語の漢字・かなとASCII英数字を読みの語境界として扱う。
def is_japanese_word_character(character: str) -> bool:
    """日本語の文字またはASCII英数字かを返す。"""
    return (
        is_japanese_script_character(character)
        or is_ascii_word_character(character)
        or character == "ー"
    )


# ひらがな、カタカナ、漢字かを字幕言語の判定に使う。
def is_japanese_script_character(character: str) -> bool:
    """日本語の文字種のUnicode範囲にあるかを返す。"""
    codepoint = ord(character)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


# 用語集と除外ファイルはデータ生成時に確定した行をそのまま読む。
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを辞書の配列として読み、行番号つきで不正データを知らせる。"""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: objectが必要です")
            rows.append(value)
    return rows


# 周辺の投稿者字幕に技術語がある場合だけ、候補として残す。
def context_markers(segments: list[dict[str, Any]], starts: list[int], index: int) -> list[str]:
    """候補行を除く前後20秒の強い技術語か複数の広い語を返す。"""
    segment = segments[index]
    start = int(segment.get("start", 0))
    left = bisect_left(starts, start - 20_000)
    right = bisect_right(starts, start + 20_000)
    context = "\n".join(
        str(item.get("text", ""))
        for context_index, item in enumerate(segments[left:right], start=left)
        if context_index != index
    )
    folded = normalize(context)
    strong = [marker for marker in STRONG_CONTEXT_MARKERS if contains_context_marker(folded, marker)]
    broad = [marker for marker in BROAD_CONTEXT_MARKERS if contains_context_marker(folded, marker)]
    return strong + (broad if strong or len(broad) >= 2 else [])


# ASCIIの文脈語は英数字の途中に現れた一致を数えない。
def contains_context_marker(text: str, marker: str) -> bool:
    """正規化済みの文脈に、単語境界を守ってmarkerがあるか返す。"""
    normalized_marker = normalize(marker)
    for match in re.finditer(re.escape(normalized_marker), text):
        if is_ascii_word_pattern(normalized_marker):
            if match.start() and is_ascii_word_character(text[match.start() - 1]):
                continue
            if match.end() < len(text) and is_ascii_word_character(text[match.end()]):
                continue
        return True
    return False


# 発話候補の字幕が日本語を含むことを確認する。
def contains_japanese_text(text: str) -> bool:
    """ひらがな、カタカナ、漢字のいずれかを含む場合にTrueを返す。"""
    return any(is_japanese_script_character(character) for character in normalize(text))


# コンテキストを持つ投稿者字幕だけを候補にし、動画ごとの上限を守って選ぶ。
def select_from_videos(
    candidates_by_video: dict[str, list[dict[str, Any]]],
    target_terms: int,
    *,
    excluded_videos: set[str] | None = None,
    minimum_segments: int = 0,
    maximum_segments: int | None = None,
    max_segments_per_video: int,
    max_terms_per_video: int | None = None,
    prioritize_low_loss_videos: bool = False,
) -> tuple[list[dict[str, Any]], set[str]]:
    """動画単位の上限と安定した順序で、指定数の候補を選ぶ。"""
    excluded_videos = excluded_videos or set()
    video_ids = [
        video_id for video_id in candidates_by_video if video_id not in excluded_videos
    ]
    if prioritize_low_loss_videos:
        video_ids.sort(
            key=lambda video_id: (
                sum(
                    len(row["terms"]) + len(row["terms_katakana_in_caption"])
                    for row in candidates_by_video[video_id]
                ),
                len(candidates_by_video[video_id]),
                stable_key(f"video:{video_id}"),
            )
        )
    else:
        video_ids.sort(key=lambda video_id: stable_key(f"video:{video_id}"))
    selected: list[dict[str, Any]] = []
    used_videos: set[str] = set()
    selected_terms = 0

    for video_id in video_ids:
        video_terms = 0
        video_segments = 0
        video_rows = sorted(
            candidates_by_video[video_id],
            key=lambda row: stable_key(row["candidate_key"]),
        )
        for row in video_rows:
            if video_segments >= max_segments_per_video:
                break
            occurrence_count = len(row["terms"]) + len(row["terms_katakana_in_caption"])
            if (
                max_terms_per_video is not None
                and video_terms + occurrence_count > max_terms_per_video
            ):
                continue
            if maximum_segments is not None and len(selected) >= maximum_segments:
                return selected, used_videos
            selected.append(row)
            used_videos.add(video_id)
            selected_terms += occurrence_count
            video_terms += occurrence_count
            video_segments += 1
            if selected_terms >= target_terms and len(selected) >= minimum_segments:
                return selected, used_videos

    return selected, used_videos


# seed 0とキーから安定した選択順を作る。
def stable_key(value: str) -> bytes:
    """候補順を実行環境によらず再現するSHA-256値を返す。"""
    return hashlib.sha256(f"{SELECTION_SEED}:{value}".encode("utf-8")).digest()


# レコードをJSONLとして保存し、集計ファイルを再計算可能にする。
def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """UTF-8のJSON Linesを空白なしで書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


# 入力、出力先、選択数は作業スクリプトから固定して呼び出せる。
def parse_args() -> argparse.Namespace:
    """metadata、用語集、出力先の引数を読む。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--audio-root", default="/home/maru/voiceime-work-pubdata/audio")
    return parser.parse_args()


# 投稿者字幕の全体統計と、評価用・学習候補用の動画単位分割を作る。
def main() -> None:
    """日本語metadata全体を一度走査し、候補と統計を出力する。"""
    args = parse_args()
    glossary = read_jsonl(args.glossary)
    excluded = {
        line.strip()
        for line in args.excluded.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    matcher = GlossaryMatcher(glossary, excluded)
    readings_by_surface = {
        entry["surface"]: entry.get("readings", [])
        for entry in glossary
        if isinstance(entry.get("surface"), str)
    }
    parquet_files = sorted(args.metadata_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"parquetがありません: {args.metadata_dir}")

    totals: Counter[str] = Counter()
    all_term_counts: Counter[str] = Counter()
    technical_term_counts: Counter[str] = Counter()
    candidates_by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    manual_video_ids: set[str] = set()
    term_video_ids: set[str] = set()
    technical_video_ids: set[str] = set()
    manual_video_hours = 0.0
    term_video_hours = 0.0
    technical_video_hours = 0.0

    for parquet_path in parquet_files:
        parquet = pq.ParquetFile(parquet_path)
        for batch in parquet.iter_batches(
            columns=["id", "shard", "transcript", "length"], batch_size=256
        ):
            for video in batch.to_pylist():
                totals["videos"] += 1
                video_id = str(video["id"])
                duration_s = float(video.get("length") or 0.0)
                totals["video_seconds"] += duration_s
                transcript_raw = video.get("transcript")
                if not transcript_raw:
                    totals["videos_without_transcript"] += 1
                    continue

                segments = json.loads(transcript_raw)
                if not isinstance(segments, list) or not segments:
                    totals["videos_without_segments"] += 1
                    continue
                has_words = [isinstance(item, dict) and "words" in item for item in segments]
                if all(has_words):
                    totals["auto_caption_videos"] += 1
                    continue
                if any(has_words):
                    totals["mixed_caption_videos"] += 1
                    continue

                manual_video_ids.add(video_id)
                manual_video_hours += duration_s / 3600
                totals["manual_videos"] += 1
                totals["manual_video_seconds"] += duration_s
                usable_segments = [
                    item
                    for item in segments
                    if isinstance(item, dict)
                    and isinstance(item.get("text"), str)
                    and item["text"].strip()
                ]
                usable_segments.sort(key=lambda item: (int(item.get("start", 0)), int(item.get("duration", 0))))
                starts = [int(item.get("start", 0)) for item in usable_segments]
                segment_matches: list[list[dict[str, Any]]] = []
                video_has_terms = False
                for segment in usable_segments:
                    hits, ambiguous = matcher.find(segment["text"])
                    totals["ambiguous_reading_matches"] += ambiguous
                    segment_matches.append(hits)
                    if not hits:
                        continue
                    video_has_terms = True
                    totals["manual_term_lines"] += 1
                    totals["manual_term_occurrences"] += len(hits)
                    all_term_counts.update(hit["surface"] for hit in hits)

                if not video_has_terms:
                    continue
                term_video_ids.add(video_id)
                term_video_hours += duration_s / 3600
                totals["term_videos"] += 1
                totals["term_video_seconds"] += duration_s

                video_has_technical_context = False
                for index, (segment, hits) in enumerate(zip(usable_segments, segment_matches, strict=True)):
                    if not hits:
                        continue
                    if not contains_japanese_text(segment["text"]):
                        totals["term_lines_without_japanese_text"] += 1
                        continue
                    line_start = max(0, int(segment.get("start", 0)))
                    line_duration = max(1, int(segment.get("duration", 1)))
                    line_end = min(int(duration_s * 1000), line_start + line_duration)
                    if line_end - line_start < MIN_CANDIDATE_DURATION_MS:
                        totals["term_lines_too_short"] += 1
                        continue
                    markers = context_markers(usable_segments, starts, index)
                    if not markers:
                        totals["term_lines_without_context_markers"] += 1
                        continue
                    video_has_technical_context = True
                    totals["technical_term_lines"] += 1
                    occurrence_count = len(hits)
                    totals["technical_term_occurrences"] += occurrence_count
                    technical_term_counts.update(hit["surface"] for hit in hits)
                    context_text = "\n".join(
                        str(item.get("text", ""))
                        for item in usable_segments[
                            bisect_left(starts, line_start - 20_000) : bisect_right(
                                starts, line_start + 20_000
                            )
                        ]
                    )
                    row = {
                        "candidate_key": f"{video_id}:{line_start}:{index}",
                        "video_id": video_id,
                        "speaker": video_id,
                        "shard": str(video.get("shard", "")),
                        "start_ms": line_start,
                        "end_ms": max(line_start + 1, line_end),
                        "duration_ms": max(1, line_end - line_start),
                        "spoken_text": segment["text"],
                        "terms": [hit["surface"] for hit in hits if hit["kind"] == "surface"],
                        "terms_katakana_in_caption": [
                            hit["surface"] for hit in hits if hit["kind"] == "reading"
                        ],
                        "glossary": [],
                        "context_markers": markers,
                        "context_text": context_text,
                        "source": "yodas3.1",
                        "license": "CC-BY-3.0 (YODAS README); CC-BY-4.0 (Hugging Face metadata tag)",
                    }
                    row["glossary"] = [
                        {"surface": surface, "readings": readings_by_surface[surface]}
                        for surface in dict.fromkeys(hit["surface"] for hit in hits)
                        if surface in readings_by_surface
                    ]
                    candidates_by_video[video_id].append(row)

                if video_has_technical_context:
                    technical_video_ids.add(video_id)
                    technical_video_hours += duration_s / 3600
                    totals["technical_videos"] += 1
                    totals["technical_video_seconds"] += duration_s

    pub_eval, eval_video_ids = select_from_videos(
        candidates_by_video,
        PUB_EVAL_TERMS,
        minimum_segments=PUB_EVAL_MIN_SEGMENTS,
        maximum_segments=PUB_EVAL_MAX_SEGMENTS,
        max_segments_per_video=PUB_EVAL_MAX_SEGMENTS_PER_VIDEO,
        prioritize_low_loss_videos=True,
    )
    eval_terms = sum(len(row["terms"]) + len(row["terms_katakana_in_caption"]) for row in pub_eval)
    pub_pool, pool_video_ids = select_from_videos(
        candidates_by_video,
        max(0, TOTAL_SELECTED_TERMS - eval_terms),
        excluded_videos=eval_video_ids,
        max_segments_per_video=PUB_POOL_MAX_SEGMENTS_PER_VIDEO,
        max_terms_per_video=PUB_POOL_MAX_TERMS_PER_VIDEO,
    )
    eval_met = len(pub_eval) >= PUB_EVAL_MIN_SEGMENTS and len(pub_eval) <= PUB_EVAL_MAX_SEGMENTS and eval_terms >= PUB_EVAL_TERMS

    def finalize(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
        """選択順にmanifest IDと音声ファイルpathを付ける。"""
        finalized: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            sample_id = f"yodas-{split}-{index:06d}"
            audio_path = f"{args.audio_root}/{split}/{sample_id}.wav"
            finalized.append(
                {
                    "id": sample_id,
                    "split": split,
                    "audio_path": audio_path,
                    "spoken_text": row["spoken_text"],
                    "target_text": row["spoken_text"],
                    "terms": row["terms"],
                    "terms_katakana_in_caption": row["terms_katakana_in_caption"],
                    "glossary": row["glossary"],
                    "speaker": row["speaker"],
                    "source": row["source"],
                    "domain": "technology",
                    "fillers": 0,
                    "tags": ["technical_context"],
                    "video_id": row["video_id"],
                    "video_id_kind": "YODAS opaque media ID, not original YouTube ID",
                    "shard": row["shard"],
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                    "license": row["license"],
                    "license_attribution": "YODAS v3 dataset and paper; original uploader identity is not present in this metadata",
                    "context_markers": row["context_markers"],
                }
            )
        return finalized

    eval_manifest = finalize(pub_eval, "pub-eval")
    pool_manifest = finalize(pub_pool, "pub-pool")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "pub-eval.jsonl", eval_manifest)
    write_jsonl(args.output_dir / "pub-pool.jsonl", pool_manifest)

    review_rows: list[dict[str, Any]] = []
    all_candidates = [row for video_rows in candidates_by_video.values() for row in video_rows]
    selected_review_ids: set[str] = set()
    for row in sorted(
        pub_eval,
        key=lambda item: stable_key(f"{item['video_id']}:{item['start_ms']}"),
    ):
        if row["video_id"] in selected_review_ids:
            continue
        selected_review_ids.add(row["video_id"])
        review_rows.append(
            {
                key: row[key]
                for key in (
                    "video_id",
                    "start_ms",
                    "end_ms",
                    "spoken_text",
                    "terms",
                    "terms_katakana_in_caption",
                    "context_markers",
                    "context_text",
                )
            }
        )
        if len(review_rows) == 20:
            break
    write_jsonl(args.output_dir / "manual-review.jsonl", review_rows)
    write_jsonl(args.output_dir / "technical-candidates.jsonl", all_candidates)

    total_videos = totals["videos"]
    total_hours = totals["video_seconds"] / 3600
    term_video_count = len(term_video_ids)
    technical_video_count = len(technical_video_ids)
    stats = {
        "dataset": "espnet/yodas3.1",
        "revision": args.revision,
        "caption_policy": "Only video transcripts where every segment lacks words are treated as uploader-provided captions; auto and mixed tracks are excluded.",
        "candidate_unit": "One uploader-caption line of at least 500 ms; audio is cut to that line's start and duration.",
        "minimum_candidate_duration_ms": MIN_CANDIDATE_DURATION_MS,
        "term_match_policy": "Glossary surface/readings are matched with word boundaries; matches inside URLs are excluded.",
        "context_policy": "Keep a term line if a strong technical marker or at least two broad markers occur in other caption lines within 20 seconds.",
        "candidate_language_policy": "Technical candidates must contain at least one Japanese hiragana, katakana, or kanji character.",
        "technical_context_markers": {
            "strong": list(STRONG_CONTEXT_MARKERS),
            "broad_requires_two": list(BROAD_CONTEXT_MARKERS),
            "context_window_s": 20,
            "candidate_line_excluded": True,
        },
        "video_cap": {
            "pub-eval_max_segments": PUB_EVAL_MAX_SEGMENTS_PER_VIDEO,
            "pub-pool_max_segments": PUB_POOL_MAX_SEGMENTS_PER_VIDEO,
            "pub-pool_max_term_occurrences": PUB_POOL_MAX_TERMS_PER_VIDEO,
        },
        "split_selection_policy": "pub-eval takes low-volume videos first to minimize candidates discarded when keeping videos disjoint; pub-pool uses remaining videos in a seed-stable order.",
        "selection_seed": SELECTION_SEED,
        "counts": dict(totals),
        "summary": {
            "videos": total_videos,
            "hours": total_hours,
            "manual_caption_videos": len(manual_video_ids),
            "manual_caption_hours": manual_video_hours,
            "videos_with_glossary_terms": term_video_count,
            "hours_with_glossary_terms": term_video_hours,
            "term_video_technical_context_videos": technical_video_count,
            "technical_context_video_ratio": technical_video_count / term_video_count if term_video_count else None,
            "technical_context_video_ratio_of_manual_caption_videos": technical_video_count / len(manual_video_ids) if manual_video_ids else None,
            "technical_context_video_hours": technical_video_hours,
            "manual_caption_term_occurrences": totals["manual_term_occurrences"],
            "technical_context_term_occurrences": totals["technical_term_occurrences"],
            "top_terms_manual": all_term_counts.most_common(30),
            "top_terms_technical_context": technical_term_counts.most_common(30),
        },
        "splits": {
            "pub-eval": {
                "segments": len(eval_manifest),
                "term_occurrences": eval_terms,
                "videos": len(eval_video_ids),
                "meets_target": eval_met,
            },
            "pub-pool": {
                "segments": len(pool_manifest),
                "term_occurrences": sum(
                    len(row["terms"]) + len(row["terms_katakana_in_caption"]) for row in pub_pool
                ),
                "videos": len(pool_video_ids),
            },
        },
        "selected_term_occurrences": eval_terms + sum(
            len(row["terms"]) + len(row["terms_katakana_in_caption"])
            for row in pub_pool
        ),
        "meets_total_term_target": eval_terms + sum(
            len(row["terms"]) + len(row["terms_katakana_in_caption"])
            for row in pub_pool
        ) >= TOTAL_SELECTED_TERMS,
        "same_video_overlap": bool(eval_video_ids & pool_video_ids),
        "manual_review_sample": {
            "segments": len(review_rows),
            "source": "pub-eval",
            "distinct_videos": len(selected_review_ids),
        },
        "glossary": {
            "entries": len(glossary),
            "excluded_entries": len(excluded),
            "usable_entries": len(glossary) - len(excluded),
        },
        "caveats": [
            "YODAS id is an opaque media identifier, not the source YouTube video ID or verified speaker ID.",
            "Uploader-provided caption does not guarantee human transcription accuracy.",
            "Technical-context classification is a fixed keyword heuristic and requires manual review.",
            "Hugging Face metadata tags CC-BY-4.0 while the dataset README says source audio was CC-BY-3.0.",
        ],
    }
    (args.output_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(stats["summary"] | {"splits": stats["splits"], "manual_review": len(review_rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
