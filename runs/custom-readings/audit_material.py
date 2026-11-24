"""完成した条件Dの学習材料を元文・音声・ASR結果・除外条件と照合する。"""
from __future__ import annotations

import json
import wave
from collections import Counter

from prepare import HELDOUT, NOVEL, TRAIN, WORK, file_hash, heldout_pattern, key
from teacher import read

# 実際の学習loaderが読む3種類のASR文と用語一覧を、同じ発話IDで確かめる。
RUN_FIELDS = {
    "first-pass.jsonl": ("hyp", "first_pass"),
    "segment-merge.jsonl": ("hyp", "combined_text"),
    "qwen06-hypothesis.jsonl": ("hyp", "qwen_hypothesis"),
    "formatter-glossary.jsonl": ("glossary", "glossary"),
}


def audit() -> dict:
    """新しい学習行が元の正解文を保ち、試験データの語を含まないことを確かめる。"""
    folder = WORK / "train-material"
    tts = WORK / "tts/train-custom"
    rows = read(folder / "train.jsonl")
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)) or len(ids) > 20_000:
        raise ValueError("学習行のIDまたは合計上限が不正")
    for filename, (run_field, row_field) in RUN_FIELDS.items():
        expected = [{"id": row["id"], run_field: row[row_field]} for row in rows]
        if read(folder / filename) != expected:
            raise ValueError(f"条件DのASR結果や一覧が学習行と不一致: {filename}")

    held = {key(value.strip()) for value in HELDOUT.read_text().splitlines() if value.strip()}
    novel = {key(term) for row in read(NOVEL) for term in row["terms"]}
    overlap = heldout_pattern(novel)
    held.update(novel)
    evaluation = [row for split in ("val-custom", "novel-custom")
                  for row in read(WORK / f"{split}-input.jsonl")]
    pairs = {(row["target_text"], key(row["custom"]["surface"])) for row in evaluation}
    original_ids = {row["custom"]["source_id"] for row in evaluation}
    truth = {}
    requested_originals = {row["source_id"] for row in rows}
    for path in TRAIN:
        with path.open() as source:
            for row in map(json.loads, source):
                if row["id"] in requested_originals:
                    truth[row["id"]] = row["target_text"], row["speaker"], row["source"]

    manifest = {row["id"]: row for row in read(tts / "manifest.jsonl")}
    counts = Counter()
    for row in rows:
        tts_row = manifest[row["id"]]
        term = key(row["custom"]["surface"])
        counts[term] += 1
        if counts[term] > 8:
            raise ValueError("1語に対する8文の上限を超えています")
        if row["source_id"] in original_ids or (row["target_text"], term) in pairs:
            raise ValueError("評価文または評価の文と語の組に重複")
        if (row["target_text"], tts_row["speaker"], tts_row["source"]) != truth[row["source_id"]]:
            raise ValueError("元の正解文・話者・TTSの割当を保持していません")
        if any(key(t) in held for t in row["terms"]) or any(key(e["surface"]) in held for e in row["glossary"]):
            raise ValueError("学習用語または一覧にheld-out語が混ざっています")
        texts = [row[field] for field in ("target_text", "first_pass", "combined_text", "qwen_hypothesis")]
        if any(overlap.search(key(text)) for text in (*texts, tts_row["spoken_text_mixed"])):
            raise ValueError("学習材料の本文にtest-novel語があります")
        if len(row["glossary"]) > 20:
            raise ValueError("学習用一覧の上限を超えています")
        audio_path = tts / tts_row["audio_path"]
        with wave.open(str(audio_path)) as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ValueError(f"TTS音声のサンプル形式が不正: {audio_path}")
    return {
        "rows": len(rows), "term_types": len(counts), "max_per_term": max(counts.values(), default=0),
        "test_novel_term_types_checked": len(novel), "evaluation_pairs_checked": len(pairs),
        "source_ids_checked": len(truth), "audio_rows_checked": len(rows),
        "sha256": {name: file_hash(folder / name) for name in ("train.jsonl", *RUN_FIELDS)},
    }


if __name__ == "__main__":
    summary = json.dumps(audit(), ensure_ascii=False, indent=2) + "\n"
    (WORK / "train-audit.json").write_text(summary)
    print(summary)
