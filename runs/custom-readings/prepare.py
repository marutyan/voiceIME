"""印付き合成文を使い、対象語1件の読みだけを替える。"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

from checks import TAG_RE, render_spoken
from teacher import kana, read, write

# 全入力は既存の合成音声のmanifest。元の話者とTTSを引き継ぐ。
HOME = Path.home()
WORK = HOME / "voiceime-work-custom"
TTS = HOME / "voiceime-work-tts/outputs"
ASR = HOME / "voiceime-work-asr"
VAL = HOME / "voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/data/tts/val/manifest.jsonl"
NOVEL = TTS / "r3-test-novel-20261122/manifest.jsonl"
TRAIN = (TTS / "r3-train-20261122/manifest.jsonl", TTS / "r3-audio-topup-20261123/manifest.jsonl")
FORMATTER_TRAIN = HOME / "voiceime-work-wops/full1/data/train-fixed.jsonl"
HELDOUT = ASR / "r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
ALIAS = WORK / "glossary-custom-readings.jsonl"
MARKER = "\ufff0"


def key(surface: str) -> str:
    """別splitでの大文字小文字・全半角の揺れを吸収する。"""
    return unicodedata.normalize("NFKC", surface).casefold()


def term_pattern(surface: str) -> re.Pattern:
    """他の英文トークンの一部に現れる表記は対象にしない。"""
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(surface) + r"(?![A-Za-z0-9_])")


def heldout_pattern(surfaces: set[str]) -> re.Pattern:
    """対象語注記の外に出たtest-novelの表記も、英字の語境界で検出する。"""
    alternatives = "|".join(re.escape(surface) for surface in sorted(surfaces))
    return re.compile(r"(?<![a-z0-9_])(?:" + alternatives + r")(?![a-z0-9_])")


def file_hash(path: Path) -> str:
    """固定した入力と出力をSHA-256で記録する。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def marked_options(row: dict, aliases: dict[str, list[str]], protected: set[str]) -> list[tuple]:
    """正解文に表記があり、発話内で一箇所を特定できる語だけを候補にする。"""
    marked = row.get("spoken_marked", "")
    matches = list(TAG_RE.finditer(marked))
    if not matches or any(key(m[1].strip()) in protected for m in matches):
        return []
    if render_spoken(marked) != (row["spoken_text_kana"], row["spoken_text_mixed"]):
        return []
    counts = Counter(key(match[1].strip()) for match in matches)
    options = []
    for match in matches:
        surface, pronunciation = (part.strip() for part in match.groups())
        if surface not in row["terms"] or counts[key(surface)] != 1:
            continue
        if not term_pattern(surface).search(row["target_text"]):
            continue
        for variant in aliases.get(surface, ()):
            if kana(pronunciation) != kana(variant):
                options.append((surface, variant, match.span()))
    return options


def replace_reading(row: dict, chosen: tuple, split: str) -> dict:
    """英字TTSと仮名TTSの両方で、同じ位置だけを別読みで発音させる。"""
    surface, variant, (start, end) = chosen
    marked = row["spoken_marked"]
    replaced = marked[:start] + MARKER + marked[end:]
    ja, multi = (part.split(MARKER) for part in render_spoken(replaced))
    return {
        **{k: v for k, v in row.items() if k != "audio_path"},
        "id": f"{split}-{row['id']}",
        "spoken_marked": marked[:start] + f"[[{surface}|{variant}]]" + marked[end:],
        "spoken_text_kana": variant.join(ja),
        "spoken_text_mixed": variant.join(multi),
        "custom": {"source_id": row["id"], "surface": surface, "reading": variant,
                   "context": {"ja": ja, "multi": multi}},
    }


def plan(rows: list[dict], aliases: dict, split: str, limit: int, per_term: int,
         protected: set[str], forbidden_pairs: set[tuple[str, str]]) -> tuple[list[dict], dict]:
    """種0で文と候補を並べ、回数が少ない語の候補から優先する。"""
    rng = random.Random(0)
    rng.shuffle(rows)
    counts = Counter()
    eligible = []
    for row in rows:
        if not row.get("speaker", "").startswith("tts-") or key(row.get("source", "")) not in (
            "synthetic-tts-ja", "synthetic-tts-multi",
        ):
            raise ValueError(f"既存の合成音声でない行: {row['id']}")
        if any(key(term) in protected for term in row["terms"]):
            continue
        options = [item for item in marked_options(row, aliases, protected)
                   if (row["target_text"], key(item[0])) not in forbidden_pairs]
        if options:
            rng.shuffle(options)
            eligible.append((row, options))
    chosen = []
    reading_counts = Counter()
    for row, options in eligible:
        if len(chosen) == limit:
            break
        options = [o for o in options if counts[key(o[0])] < per_term]
        if options:
            option = min(options, key=lambda o: (counts[key(o[0])], reading_counts[o[:2]]))
            counts[key(option[0])] += 1
            reading_counts[option[:2]] += 1
            chosen.append(replace_reading(row, option, split))
    return chosen, {"eligible_sentences": len(eligible), "selected": len(chosen), "term_types": len(counts),
                    "planned_limit": limit, "max_per_term": max(counts.values(), default=0),
                    "source_rows": len(rows)}


def main() -> None:
    """評価用・学習用のTTS入力と、重複除外の集計を保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=("eval", "train"))
    args = parser.parse_args()
    aliases = {row["surface"]: row["readings"] for row in read(ALIAS)}
    protected = {key(line.strip()) for line in HELDOUT.read_text().splitlines() if line.strip()}
    val, novel = read(VAL), read(NOVEL)
    novel_surfaces = {key(term) for row in novel for term in row["terms"]}
    protected.update(novel_surfaces)
    summary = {"seed": 0, "dictionary_sha256": file_hash(ALIAS), "splits": {}}
    if args.group == "eval":
        with FORMATTER_TRAIN.open() as rows:
            seen = {key(t) for row in map(json.loads, rows) for t in row["terms"]
                    if t in row["target_text"]}
        val_aliases = {surface: readings for surface, readings in aliases.items() if key(surface) in seen}
        specs = [("val-custom", val, 500, protected, val_aliases),
                 ("novel-custom", novel, 300, set(), aliases)]
        forbidden = set()
    else:
        tests = read(WORK / "val-custom-input.jsonl") + read(WORK / "novel-custom-input.jsonl")
        forbidden = {(row["target_text"], key(row["custom"]["surface"])) for row in tests}
        eval_ids = {row["id"] for row in val + novel}
        source = [row for path in TRAIN for row in read(path) if row["id"] not in eval_ids]
        if len({row["id"] for row in source}) != len(source):
            raise ValueError("trainの元IDに重複があります")
        specs = [("train-custom", source, 20_000, protected, aliases)]
    for split, rows, limit, excluded, permitted_aliases in specs:
        chosen, audit = plan(rows, permitted_aliases, split, limit, 8 if args.group == "train" else limit,
                             excluded, forbidden)
        if args.group == "train":
            pattern = heldout_pattern(novel_surfaces)
            chosen = [row for row in chosen if not any(
                pattern.search(key(row[field])) for field in ("target_text", "spoken_text_mixed")
            )]
            audit["excluded_unmarked_novel"] = audit["selected"] - len(chosen)
            audit["selected"] = len(chosen)
            counts = Counter(key(row["custom"]["surface"]) for row in chosen)
            audit.update(term_types=len(counts), max_per_term=max(counts.values(), default=0))
        output = WORK / f"{split}-input.jsonl"
        write(output, chosen)
        audit["input_sha256"] = file_hash(output)
        summary["splits"][split] = audit
    (WORK / f"{args.group}-plan.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
