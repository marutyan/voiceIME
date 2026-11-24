#!/usr/bin/env python3
"""保存済みの合成音声評価を再採点し、用語の失敗箇所と候補追加の影響を数える。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from rapidfuzz.distance import Levenshtein

# 評価一覧を再現する上限と、valで比較する照合下限。
CAPS = (20, 32, 48, 64)
SCORE_SWEEP = (75, 70, 65, 60)
# 読み照合は短い語の偶然一致を抑えるため、完全一致か5文字以上で1編集までを比較する。
READING_SWEEP = (0, 1)
KANA = re.compile(r"[ァ-ヺー]+")
KANJI = re.compile(r"[㐀-鿿々]")
LATIN = re.compile(r"[a-zA-Z0-9]")
MARK = re.compile(r"\[\[([^|\]]+)\|([^\]]+)\]\]")
JOIN_KANA = re.compile(r"[ァ-ヺー]+(?:[ \t・]+[ァ-ヺー]+)*")


def digest(path):
    """入力ファイルの内容を監査用のハッシュにする。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_selector(path, expected_digest):
    """一覧作成時と同じ選択器をハッシュで確認して読み込む。"""
    if digest(path) != expected_digest:
        raise ValueError(f"選択器のハッシュが一致しません: {path}")
    spec = importlib.util.spec_from_file_location("capacity_selector", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def indexed_rows(path):
    """JSONLをIDで引けるようにし、重複を検出する。"""
    rows = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["id"] in rows:
                raise ValueError(f"重複ID: {path} {row['id']}")
            rows[row["id"]] = row
    return rows


def nfkc(text):
    """全角と半角を揃える。"""
    return unicodedata.normalize("NFKC", text)


def kana_width(text):
    """文字数を保って仮名をカタカナに揃える。"""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in nfkc(text))


def kana_key(text):
    """カナ表記を揃え、長音符と語内の区切りを無視する。"""
    return re.sub(r"[ー・\s-]", "", kana_width(text))


def reading_keys(readings):
    """カナだけで比較できる用語集の読みを返す。"""
    return tuple(
        sorted({key for text in readings if KANA.fullmatch(key := kana_key(text))})
    )


@lru_cache(maxsize=None)
def surface_pattern(surface):
    """幅・大小文字・英語の語内空白を許し、短い英字の他語内一致を防ぐ。"""
    key = nfkc(surface).casefold()
    if not LATIN.search(key):
        return re.compile(re.escape(key))
    # 英字略語の1字ごとの空白を許しても、両端は英数字・記号で区切る。
    elements = [re.escape(char) for char in key if not char.isspace()]
    # 空白が語境界の場合もあるため、英数字の両端にだけ境界を要求する。
    before = r"(?<![a-z0-9_+#])" if re.match(r"[a-z0-9]", key) else ""
    after = r"(?![a-z0-9_+#])" if re.search(r"[a-z0-9_+#]$", key) else ""
    return re.compile(before + r"[ \t]*".join(elements) + after)


def surface_count(text, surface):
    """軽微な表記の揺れを許した表記の回数を数える。"""
    return sum(1 for _ in surface_pattern(surface).finditer(nfkc(text).casefold()))


def mark_ref(marked, tokens_by_text):
    """読み上げ台本の用語位置を、文字比較用に正規化した文へ写す。"""
    parts = []
    spans = defaultdict(list)
    offset = 0
    end = 0
    for match in MARK.finditer(marked):
        before = aligned_tokens(tokens_by_text[marked[end : match.start()]])
        surface, spoken = match.groups()
        reading = align_key(spoken)
        offset += len(before)
        spans[surface].append((offset, offset + len(reading), reading))
        parts.extend((before, reading))
        offset += len(reading)
        end = match.end()
    parts.append(aligned_tokens(tokens_by_text[marked[end:]]))
    return "".join(parts), spans


def align_key(text):
    """台本とASRを文字で対応づけるため、仮名・英字の幅と区切りを揃える。"""
    return "".join(c for c in kana_key(text).casefold() if c.isalnum())


def aligned_tokens(tokens):
    """読み付与した語を連結し、台本と仮説の文字を対応させる。"""
    return "".join(align_key(kana or raw) for raw, kana in tokens)


def tokenize(binary, texts):
    """日本語トークナイザをまとめて1回呼び、入力順に元表記と読みを受け取る。"""
    message = json.dumps(texts, ensure_ascii=False) + "\n"
    result = subprocess.run(
        [str(binary)], input=message, text=True, capture_output=True, check=True
    )
    tokens = json.loads(result.stdout)
    if ["".join(raw for raw, _ in row) for row in tokens] != texts:
        raise ValueError("トークンの元表記から入力を復元できません")
    return tokens


def projected_boundaries(reference, observed):
    """編集距離の対応列を使い、台本側の境界をASR側へ写す。"""
    starts, ends = [0] * (len(reference) + 1), [0] * (len(reference) + 1)
    for tag, a, b, c, d in Levenshtein.opcodes(reference, observed):
        if tag == "insert":
            starts[a], ends[a] = d, c
            continue
        for source in range(a, b + 1):
            mapped = c + (source - a) * (d - c) // (b - a)
            if source > a or a == 0:
                ends[source] = mapped
            if source < b or b == len(reference):
                starts[source] = mapped
    return starts, ends


class Hypothesis:
    """ASR仮説を、元文・カナ照合・台本に対する位置対応へ変換する。"""

    def __init__(self, text, tokens, reference):
        self.text = text
        self.tokens = []
        pieces = []
        offset = 0
        for raw, kana in tokens:
            key = align_key(kana or raw)
            self.tokens.append((raw, kana, offset, offset + len(key)))
            pieces.append(key)
            offset += len(key)
        self.aligned_text = "".join(pieces)
        self.starts, self.ends = projected_boundaries(reference, self.aligned_text)

    def region(self, span):
        """台本上の用語の両端をASR仮説の比較用文字位置へ写す。"""
        start, end, _ = span
        return self.starts[start], self.ends[end]

    def original_region(self, start, end):
        """対応した文字範囲の元表記を返し、漢字と仮名の区別を保つ。"""
        pieces = []
        for raw, kana, left, right in self.tokens:
            if left >= end or right <= start or left == right:
                continue
            if kana:
                pieces.append(raw)
            else:
                # 区切りは位置合わせから外している。元表記と比較用の長さが同じときのみ切る。
                pieces.append(
                    raw[max(start - left, 0) : end - left]
                    if len(raw) == right - left
                    else raw
                )
        return "".join(pieces)

    def raw_near(self, keys):
        """文中に元から書かれた仮名だけで用語集の読みを照合する。"""
        runs = [
            kana_key(match.group())
            for match in JOIN_KANA.finditer(kana_width(self.text))
        ]
        # 3文字以下は短い仮名の単語・文字種区間の完全一致に限定する。
        short_keys = {
            kana_key(raw)
            for raw, _, _, _ in self.tokens
            if KANA.fullmatch(kana_width(raw))
        }
        for key in keys:
            if len(key) <= 3:
                if key in short_keys or key in runs:
                    return True
                continue
            limit = min(2, len(key) // 4)
            for run in runs:
                if key in run:
                    return True
                for width in range(
                    len(key) - limit, min(len(run), len(key) + limit) + 1
                ):
                    if any(
                        Levenshtein.distance(
                            key, run[i : i + width], score_cutoff=limit
                        )
                        <= limit
                        for i in range(len(run) - width + 1)
                    ):
                        return True
        return False

    def converted_windows(self, max_width):
        """漢字を読み直した箇所を含む、トークン境界間のカナ列を列挙する。"""
        for i, (raw, kana, left, _) in enumerate(self.tokens):
            if not KANA.fullmatch(kana_key(kana or raw)):
                continue
            key = ""
            converted = False
            for raw, kana, _, right in self.tokens[i:]:
                if not kana and not raw.strip(" \t・"):
                    continue
                part = kana_key(kana or raw)
                if not KANA.fullmatch(part) or len(key) + len(part) > max_width:
                    break
                key += part
                converted |= bool(kana)
                if converted and len(key) >= 2:
                    yield key, left, right


def remove_one(key):
    """1文字削除した読みの集合を作る。位置違いの重複は1回だけ扱う。"""
    return {key[:i] + key[i + 1 :] for i in range(len(key))}


class ReadingIndex:
    """用語集の読みを引き、完全一致と1編集までの候補を返す。"""

    def __init__(self, keys_by_surface, max_edits):
        self.exact = defaultdict(set)
        self.one_deleted = defaultdict(set)
        self.max_width = max(
            (len(key) for keys in keys_by_surface.values() for key in keys), default=0
        )
        for term, keys in keys_by_surface.items():
            for key in keys:
                if len(key) < 2:
                    continue
                self.exact[key].add(term)
        if max_edits:
            for key in self.exact:
                if len(key) >= 5:
                    for shorter in remove_one(key):
                        self.one_deleted[shorter].add(key)

    @lru_cache(maxsize=65536)
    def find(self, key):
        """照合に通った用語ごとに最小の編集距離を返す。"""
        hits = dict.fromkeys(self.exact.get(key, ()), 0)
        near = set(self.one_deleted.get(key, ()))
        if self.one_deleted and len(key) >= 5:
            for shorter in remove_one(key):
                near.update(self.one_deleted.get(shorter, ()))
                if len(shorter) >= 5 and shorter in self.exact:
                    near.add(shorter)
        for candidate in near:
            if Levenshtein.distance(candidate, key, score_cutoff=1) == 1:
                for term in self.exact[candidate]:
                    hits.setdefault(term, 1)
        return hits

    def matches(self, hypothesis):
        """文中のどの範囲に候補が出たかを保持し、用語の位置確認にも使う。"""
        matches = defaultdict(list)
        for key, left, right in hypothesis.converted_windows(self.max_width + 1):
            for term, distance in self.find(key).items():
                matches[term].append((distance, left, right))
        return matches


def c_details(hypotheses, span):
    """台本の位置を使い、読みが最も残った側のASRで崩れ方を分類する。"""
    if span is None:
        return "unclear", "", ""
    _, _, expected = span
    options = []
    for label, hypothesis in hypotheses.items():
        start, end = hypothesis.region(span)
        observed = hypothesis.aligned_text[start:end]
        raw = hypothesis.original_region(start, end)
        similarity = Levenshtein.normalized_similarity(expected, observed)
        # 同点なら音が残る方、それも同じならHaasを採る。
        options.append(
            (similarity, bool(observed), label == "haas", label, observed, raw)
        )
    _, _, _, label, observed, raw = max(options)
    if not observed:
        return "deletion", label, ""
    operations = Levenshtein.opcodes(expected, observed)
    if any(
        op.tag == "delete" and op.src_start > 0 and op.src_end < len(expected)
        for op in operations
    ):
        if all(op.tag in ("delete", "equal") for op in operations):
            return "sound_drop", label, raw[:30]
    common = (
        SequenceMatcher(None, expected, observed, autojunk=False)
        .find_longest_match()
        .size
    )
    if len(observed) < len(expected) and common >= max(2, (len(expected) + 1) // 2):
        return "partial", label, raw[:30]
    if KANJI.search(raw) and LATIN.search(nfkc(raw)):
        return "mixed", label, raw[:30]
    if KANJI.search(raw):
        return "kanji", label, raw[:30]
    if LATIN.search(nfkc(raw)):
        return "latin", label, raw[:30]
    if KANA.search(kana_width(raw)):
        return "kana", label, raw[:30]
    return "unclear", label, raw[:30]


def rank_reason(selector, index, text, term, rank):
    """上限で落ちた語と、採点や候補索引で落ちた語を区別する。"""
    if rank is not None:
        return "rank", None
    kana = selector._text_runs(text, "kana", ignore_long_vowel=True)
    latin = selector._text_runs(text, "latin")
    roman = selector._romanized_runs(text)
    found = [
        index.keys[k]
        for k in index._candidate_key_indexes(kana, latin, roman)
        if index.entries[index.keys[k].entry_index].surface == term
    ]
    if not found:
        return "not_indexed", None
    return "below_score", max(
        index._score_key(key, kana, latin, roman, 0.0) for key in found
    )


def unspoken(entries, manifest, spans):
    """正解語・読み上げの用語マーク・台本の表記に根拠がない候補を数える。"""
    spoken = set(manifest["terms"]) | spans.keys()
    mixed = manifest.get("spoken_text_mixed") or manifest["spoken_text"]
    return sum(
        term not in spoken and not surface_count(mixed, term) for term in entries
    )


def reading_hit(matches, max_edit, hypothesis, span):
    """読みで拾った候補が、台本から写した発話位置にも重なるかを確かめる。"""
    if span is None:
        return False
    start, end = hypothesis.region(span)
    return any(
        distance <= max_edit
        and max(0, min(end, right) - max(start, left)) * 2 >= right - left
        for distance, left, right in matches
    )


def classify(term, occurrence, manifest, result, hypotheses, span, readings):
    """公式採点で落ちた各出現を、Dの判定を先にしてA/B/Cへ振り分ける。"""
    if manifest["target_text"].count(term) <= occurrence:
        return "D", "reference_target"
    if surface_count(result["hyp"], term) > occurrence:
        return "D", "surface_variant"
    if term in result["glossary"]:
        combined = result["input_text"]["combined_text"]
        return "A", "merged_present" if combined.count(
            term
        ) > occurrence else "merged_absent"
    if term not in readings:
        return "D", "outside_pool"
    # 正表記は読み未登録でも検出できる。読みがなければCとは判定しない。
    if any(surface_count(h.text, term) > occurrence for h in hypotheses.values()):
        return "B", "surface"
    if not readings[term]:
        return "D", "missing_reading"
    if span is None:
        return "D", "missing_spoken_mark"
    if any(h.raw_near(readings[term]) for h in hypotheses.values()):
        return "B", "raw_kana"
    return "C", ""


def analyze_split(
    root, split, caps, selector, token_binary, settings, selection_audit, result_audit
):
    """一つのsplitで保存結果を照合し、一覧の感度分析と誤りの分類を行う。"""
    fr3 = root / "voiceime-work-fr3"
    base = root / "voiceime-work-wops/runs/capacity/FULL-scratch"
    list_base = fr3 / "inputs/glossary-capacity-20261123-corrected/glossaries" / split
    inputs = selection_audit["inputs"]
    verified = {}
    for label in (
        "manifest",
        "first_pass",
        "qwen",
        "glossary_1",
        "glossary_2",
        "exclusions",
    ):
        if label not in inputs:
            continue
        path = root / Path(inputs[label]["path"]).relative_to("/home/maru")
        sha = digest(path)
        if sha != inputs[label]["sha256"]:
            raise ValueError(f"保存時と入力が異なります: {path}")
        verified[label] = path
    manifest = indexed_rows(verified["manifest"])
    first_pass = indexed_rows(verified["first_pass"])
    qwen_pass = indexed_rows(verified["qwen"])
    if tuple(first_pass) != tuple(manifest) or tuple(qwen_pass) != tuple(manifest):
        raise ValueError(f"{split}: ASRとmanifestのIDまたは順序が異なります")
    excluded = (
        selector.load_term_list(verified["exclusions"])
        if "exclusions" in verified
        else set()
    )
    pool = selector.load_glossary(
        verified["glossary_1"], verified["glossary_2"], exclude_terms=excluded
    )
    if len(pool) != selection_audit["glossary_pool_entries"]:
        raise ValueError("用語集の語数が事前監査と一致しません")
    readings = {entry.surface: reading_keys(entry.readings) for entry in pool}
    index = selector.GlossaryIndex(pool)
    reading_index = ReadingIndex(readings, max(settings["reading"]))
    source_hashes = {label: digest(path) for label, path in verified.items()}

    results = {}
    saved = {}
    for cap in (20, 32, 48):
        variant = f"max{cap}-haas-qwen"
        inf_path = base / "inference" / f"{split}-{variant}.jsonl"
        list_path = list_base / f"{variant}.jsonl"
        results[cap] = indexed_rows(inf_path)
        saved[cap] = indexed_rows(list_path)
        source_hashes[f"inference_{cap}"] = digest(inf_path)
        source_hashes[f"list_{cap}"] = digest(list_path)
        if tuple(results[cap]) != tuple(manifest) or tuple(saved[cap]) != tuple(
            manifest
        ):
            raise ValueError(
                f"{split}/{cap}: 保存結果とmanifestのIDまたは順序が異なります"
            )

    # 一覧の監査が指すASR原本を使う。整形入力を使った場合の分類差も集計する。
    texts = {rid: (first_pass[rid]["hyp"], qwen_pass[rid]["hyp"]) for rid in manifest}
    formatter_texts = {
        rid: (
            row["input_text"]["first_pass"],
            row["input_text"]["qwen_hypothesis"] or "",
        )
        for rid, row in results[20].items()
    }
    reference_parts = []
    for row in manifest.values():
        # マーク内の読みは合成時に指定された値を使い、前後の文脈だけ読み付与する。
        reference_parts.extend(MARK.split(row["spoken_marked"])[::3])
    token_texts = list(
        dict.fromkeys(
            [
                text
                for pair in (*texts.values(), *formatter_texts.values())
                for text in pair
            ]
            + reference_parts
        )
    )
    tokens_by_text = dict(
        zip(token_texts, tokenize(token_binary, token_texts), strict=True)
    )
    summaries = {cap: defaultdict(Counter) for cap in caps}
    audit = {cap: Counter() for cap in results}
    input_differences = Counter()
    ledger = []
    primary_changes = {
        "cap48",
        "cap64",
        f"score{settings['primary_score']}",
        f"reading{settings['primary_reading']}",
    }

    for rid, row in manifest.items():
        first, qwen = texts[rid]
        formatter_first, formatter_qwen = formatter_texts[rid]
        input_differences["haas"] += first != formatter_first
        input_differences["qwen"] += qwen != formatter_qwen
        reference, spans = mark_ref(row["spoken_marked"], tokens_by_text)
        hypotheses = {
            "haas": Hypothesis(first, tokens_by_text[first], reference),
            "qwen": Hypothesis(qwen, tokens_by_text[qwen], reference),
        }
        formatter_hypotheses = {
            name: hypotheses[name]
            if hypotheses[name].text == hyp
            else Hypothesis(hyp, tokens_by_text[hyp], reference)
            for name, hyp in zip(
                hypotheses, (formatter_first, formatter_qwen), strict=True
            )
        }
        text = "\n".join((first, qwen))
        order = [entry.surface for entry in index.select(text, len(pool), 75)]
        ranks = {term: rank for rank, term in enumerate(order, 1)}
        for cap, result in results.items():
            stored = result[rid]
            list_rows = [entry["surface"] for entry in saved[cap][rid]["glossary"]]
            if (
                stored["input_text"] != results[20][rid]["input_text"]
                or list_rows != stored["glossary"]
            ):
                raise ValueError(f"{split}/{rid}/{cap}: 保存済み一覧または入力に不一致")
            if order[:cap] != list_rows:
                raise ValueError(
                    f"{split}/{rid}/{cap}: 選択器の再実行で一覧を再現できません"
                )
            audit[cap]["rows"] += 1
            audit[cap]["glossary_match"] += 1
            audit[cap]["model_input_match"] += 1

        reading_matches = {
            label: reading_index.matches(h) for label, h in hypotheses.items()
        }
        reading_candidates = {edit: set() for edit in settings["reading"]}
        for hits in reading_matches.values():
            for term, locations in hits.items():
                best = min(distance for distance, _, _ in locations)
                for edit in settings["reading"]:
                    if best <= edit:
                        reading_candidates[edit].add(term)

        selections = {f"cap{cap}": set(order[:cap]) for cap in (48, 64)}
        low_orders = {
            score: [entry.surface for entry in index.select(text, max(caps), score)]
            for score in settings["score"]
            if score != 75
        }
        terms = Counter(row["terms"])
        for cap, result in results.items():
            current = set(result[rid]["glossary"])
            for term, count in terms.items():
                correct = min(count, result[rid]["hyp"].count(term))
                bucket = "included" if term in current else "excluded"
                audit[cap]["terms"] += count
                audit[cap]["correct"] += correct
                audit[cap][bucket] += count
                audit[cap][bucket + "_correct"] += correct

        for cap, summary in summaries.items():
            result = results[cap][rid]
            current = set(result["glossary"])
            alternatives = {
                **selections,
                **{
                    f"score{score}": set(positions[:cap])
                    for score, positions in low_orders.items()
                },
                **{
                    f"reading{edit}": current | candidates
                    for edit, candidates in reading_candidates.items()
                },
            }
            additions = {
                label: candidates - current
                for label, candidates in alternatives.items()
            }
            for label, added in additions.items():
                removed = current - alternatives[label]
                summary[label]["added_candidates"] += len(added)
                summary[label]["added_unspoken"] += unspoken(added, row, spans)
                summary[label]["removed_unspoken"] += unspoken(removed, row, spans)
                summary[label]["added_gold"] += sum(terms[term] for term in added)
                summary[label]["displaced_gold"] += sum(terms[term] for term in removed)

            for term, count in terms.items():
                correct = min(count, result["hyp"].count(term))
                # 公式指標は出現位置を持たないため、同じ用語の正答は先頭の出現に割り当てる。
                for occurrence in range(correct, count):
                    occurrences = spans.get(term, [])
                    # 同じ語を発話中に繰り返す場合、原文の最後から必要な数だけを使う。
                    span = (
                        occurrences[len(occurrences) - count + occurrence]
                        if len(occurrences) >= count
                        else None
                    )
                    category, reason = classify(
                        term, occurrence, row, result, hypotheses, span, readings
                    )
                    if category in ("B", "C") and texts[rid] != formatter_texts[rid]:
                        alt, _ = classify(
                            term,
                            occurrence,
                            row,
                            result,
                            formatter_hypotheses,
                            span,
                            readings,
                        )
                        if alt != category:
                            summary["formatter_asr_changes"][
                                f"{category}_to_{alt}"
                            ] += 1
                    rank = ranks.get(term)
                    score = None
                    evidence = reason
                    c_source, c_raw = "", ""
                    if category == "B":
                        reason, score = rank_reason(selector, index, text, term, rank)
                    if category == "C":
                        reason, c_source, c_raw = c_details(hypotheses, span)
                    summary["classes"][category] += 1
                    summary[f"{category}_types"][reason] += 1
                    merged_exact = (
                        result["input_text"]["combined_text"].count(term) > occurrence
                    )
                    if merged_exact:
                        summary["merged_exact"][category] += 1
                    flag = {}
                    for label, added in additions.items():
                        if term not in added:
                            continue
                        summary[label][f"{category}_added"] += 1
                        flag[label] = 1
                        if label.startswith("reading") and category == "C":
                            edit = int(label.removeprefix("reading"))
                            if any(
                                reading_hit(
                                    reading_matches[name].get(term, ()), edit, h, span
                                )
                                for name, h in hypotheses.items()
                            ):
                                summary[label]["C_position_confirmed"] += 1
                                flag[label] = 2
                    # Cの読み復帰は発話位置も確認する。ほかの変更で一覧へ追加された語と和集合を取る。
                    eligible = {
                        label
                        for label, value in flag.items()
                        if category != "C"
                        or not label.startswith("reading")
                        or value == 2
                    }
                    summary["candidate_union"][f"{category}_any_tested"] += bool(
                        eligible
                    )
                    summary["candidate_union"][f"{category}_primary"] += bool(
                        eligible & primary_changes
                    )
                    ledger.append(
                        {
                            "split": split,
                            "cap": cap,
                            "id": rid,
                            "term": term,
                            "occurrence": occurrence + 1,
                            "class": category,
                            "reason": reason,
                            "evidence": evidence,
                            "rank_at_75": rank,
                            "indexed_score_at_0": score,
                            "merged_exact": int(merged_exact),
                            "c_asr": c_source,
                            "c_fragment": c_raw,
                            "added_by": json.dumps(
                                flag, sort_keys=True, separators=(",", ":")
                            ),
                        }
                    )

    for cap, counts in audit.items():
        compare = result_audit[f"max{cap}-haas-qwen"]
        if dict(counts) != compare:
            raise ValueError(
                f"{split}/{cap}: 公式監査と再集計に不一致: {dict(counts)} {compare}"
            )
    report = {
        "source_sha256": source_hashes,
        "settings": settings,
        "audit": audit,
        "selector_vs_formatter_input_differences": input_differences,
        "conditions": {},
    }
    for cap, summary in summaries.items():
        missed = audit[cap]["terms"] - audit[cap]["correct"]
        if sum(summary["classes"].values()) != missed:
            raise ValueError(f"{split}/{cap}: 分類と全誤り数が一致しません")
        report["conditions"][cap] = dict(summary)
    return report, ledger


def main():
    """valで比較条件を出力し、固定設定を読み取ってnovelを一度集計する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--tokenizer", required=True, type=Path)
    parser.add_argument("--split", required=True, choices=("val", "test-novel"))
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.inputs
    fr3 = root / "voiceime-work-fr3"
    base = root / "voiceime-work-wops/runs/capacity/FULL-scratch"
    list_audit = json.loads(
        (
            fr3 / "inputs/glossary-capacity-20261123-corrected/selection-audit.json"
        ).read_text()
    )
    audit = json.loads((base / "audit.json").read_text())
    selector = load_selector(
        fr3 / "overlays/glossary-main-c2ad276.py", list_audit["selector_sha256"]
    )
    if args.split == "test-novel" and args.settings is None:
        parser.error("test-novelの前にvalで照合条件を固定してください")
    settings = (
        json.loads(args.settings.read_text())
        if args.settings
        else {
            "score": SCORE_SWEEP,
            "reading": READING_SWEEP,
            "primary_score": 70,
            "primary_reading": 0,
        }
    )
    split_key = args.split.replace("-", "_")
    result, ledger = analyze_split(
        root,
        args.split,
        (20,) if args.split == "val" else (20, 32),
        selector,
        args.tokenizer,
        settings,
        list_audit[split_key],
        audit[split_key],
    )
    result["selector_commit"] = list_audit["selector_commit"]
    result["selector_sha256"] = list_audit["selector_sha256"]
    result["rapidfuzz_version"] = __import__("rapidfuzz").__version__
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.split}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (args.out / f"{args.split}-misses.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ledger[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(ledger)
    print(json.dumps(result["conditions"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
