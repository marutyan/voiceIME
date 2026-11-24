"""慣習読みの認識形、一覧の包含、整形後の正答を合成音声だけで集計する。"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from recognize import DICT, FR, HOME, NOVEL, WORK, records, selection
from teacher import kana, read, write
from voiceime.eval.metrics import calculate_cer, calculate_term_accuracy

# 通常の容量評価と同じ既存ASR・モデルを使う。通常文ではASR文を固定して一覧の影響を測る。
ASR = HOME / "voiceime-work-asr/r3-multiasr-20261122/outputs"
VAL_RUNS = FR / "d-multiasr-20261123/val-runs"
CAPACITY = FR / "glossary-capacity-20261123-corrected/glossaries"
FULL = HOME / "voiceime-work-fr3"
MODEL = HOME / "voiceime-work-wops/full1/outputs/FULL-scratch/best"
SAVED = HOME / "voiceime-work-wops/runs/capacity/FULL-scratch/inference"
EXCLUSIONS = NOVEL / "exclude-v2-83.txt"
CUSTOM_SPLITS = ("val-custom", "novel-custom")
REGULAR_SPLITS = ("val", "test-novel")


def normalized_with_map(text: str) -> tuple[str, list[int]]:
    """仮名・英字の表記を揃えながらASRの生文字の位置を保持する。"""
    text = unicodedata.normalize("NFKC", text)
    chars, offsets = [], []
    for i, char in enumerate(text):
        folded = kana(char).casefold()
        if folded and folded.isalnum():
            chars.extend(folded)
            offsets.extend([i] * len(folded))
    return "".join(chars), offsets


def recognition_form(row: dict, hypothesis: str) -> tuple[str, str]:
    """読み上げ文の左右の文脈で対象区間を特定し、元の文字列を分類する。"""
    meta = row["custom"]
    engine = "ja" if row["source"] == "synthetic-tts-ja" else "multi"
    left, right = (normalized_with_map(s)[0] for s in meta["context"][engine])
    hyp = unicodedata.normalize("NFKC", hypothesis)
    norm, offsets = normalized_with_map(hyp)
    target = normalized_with_map(meta["surface"])[0]
    pronunciation = normalized_with_map(meta["reading"])[0]
    blocks = difflib.SequenceMatcher(None, left + "\ufff0" + right, norm, autojunk=False).get_matching_blocks()
    start, end = (0 if not left else None), (len(norm) if not right else None)
    for a, b, size in blocks:
        if left and a + size == len(left) and size >= min(2, len(left)):
            start = b + size
        if right and a == len(left) + 1 and size >= min(2, len(right)):
            end = b
    if start is None or end is None or start > end:
        return "判定不能", ""
    if start == end:
        return "脱落", ""
    raw = hyp[offsets[start]: offsets[end-1]+1]
    if norm[start:end] == target:
        # 長音や句読点を採点用に落としても、C++などの記号を含む表記はここで確認する。
        span_start = offsets[start - 1] + 1 if start else 0
        span_end = offsets[end] if end < len(offsets) else len(hyp)
        surface = unicodedata.normalize("NFKC", meta["surface"])
        found = re.search(re.escape(surface), hyp[span_start:span_end], re.IGNORECASE)
        if found:
            return "正しい表記", found[0]
    if norm[start:end] == pronunciation:
        return "慣習読みの仮名", raw
    return "漢字や別の語", raw


def prepare_custom(split: str) -> tuple[Path, dict]:
    """合成し直した発話に対するASR、一覧、設定を評価器の既存形式に置く。"""
    manifest = WORK / "tts" / split / "manifest.jsonl"
    by_id = {r["id"]: r for r in read(manifest)}
    rows = read(WORK / "asr" / split / "combined.jsonl")
    if [r["id"] for r in rows] != list(by_id):
        raise ValueError(f"{split}: ASRとTTSで行が不一致")
    path = WORK / "evaluation" / split
    path.mkdir(parents=True, exist_ok=True)
    form_counts = defaultdict(Counter)
    shapes = defaultdict(lambda: defaultdict(Counter))
    coverage = Counter()
    for row in rows:
        sample = by_id[row["id"]]
        surface = sample["custom"]["surface"]
        for source in ("first_pass", "qwen_hypothesis"):
            category, shape = recognition_form(sample, row[source])
            form_counts[source][category] += 1
            shapes[source][surface][(category, shape)] += 1
        for mode in ("base", "custom"):
            coverage[mode] += surface in {e["surface"] for e in row[mode]["glossary"]}
    for field in ("first_pass", "qwen_hypothesis"):
        write(path / f"{field}.jsonl", [{"id": r["id"], "hyp": r[field]} for r in rows])
    for mode in ("base", "custom"):
        for field, key in (("combined_text", "hyp"), ("glossary", "glossary")):
            write(path / f"{mode}-{field}.jsonl",
                  [{"id": r["id"], key: r[mode][field]} for r in rows])
    shape_rows = [
        {"asr": asr, "surface": surface,
         "forms": [{"category": k[0], "text": k[1], "count": n} for k, n in counts.most_common()]}
        for asr, words in shapes.items() for surface, counts in sorted(words.items())
    ]
    write(WORK / f"{split}-asr-forms.jsonl", shape_rows)
    return manifest, {"rows": len(rows), "categories": dict(form_counts), "selected": dict(coverage)}


def regular_files(split: str) -> tuple[Path, Path, Path, Path]:
    """容量評価のmanifestとHaas初回・結合文・Qwen初回を取得する。"""
    if split == "val":
        return (FR / "manifest-val-no-audio.jsonl", VAL_RUNS / "first-pass.jsonl",
                VAL_RUNS / "segment-merge.jsonl", VAL_RUNS / "qwen06-hypothesis.jsonl")
    return (NOVEL / "test-novel.jsonl", NOVEL / "a-plain.jsonl",
            ASR / "haas-plus-qwen06-test-novel-segment-merge.jsonl",
            ASR / "multiasr-test-novel-qwen06-firstpass.jsonl")


def prepare_regular(split: str) -> Path:
    """通常文では既存ASRを固定し、追加前一覧の再現を行ごとに確かめる。"""
    manifest, first, _, _ = regular_files(split)
    if split == "val":
        first = ASR / "haas-plus-qwen06-val-plain.jsonl"
    qwen = ASR / f"multiasr-{split}-qwen06-firstpass.jsonl"
    ids = [r["id"] for r in read(manifest)]
    texts = [{r["id"]: r["hyp"] for r in read(path)} for path in (first, qwen)]
    base = selection(split, "base")
    custom = selection(split, "custom")
    previous = {r["id"]: r["glossary"] for r in read(CAPACITY / split / "max48-haas-qwen.jsonl")}
    path = WORK / "evaluation" / split
    path.mkdir(parents=True, exist_ok=True)
    rows = []
    for sample_id in ids:
        text = "\n".join(source[sample_id] for source in texts)
        if records(base.select(text, max_entries=48), "base") != previous[sample_id]:
            raise ValueError(f"{split}: 上限48の基準一覧が一致しない: {sample_id}")
        rows.append({"id": sample_id, "glossary": records(custom.select(text, max_entries=48), "custom")})
    output = path / "custom-glossary.jsonl"
    write(output, rows)
    return output


def score(manifest: Path, output: Path, custom: bool) -> dict:
    """通常文は既報の厳密表記とCER、専用文は読みを替えた対象語も数える。"""
    reference = read(manifest)
    rows = read(output)
    hypotheses = {r["id"]: r["hyp"] for r in rows}
    if len(rows) != len(hypotheses) or set(hypotheses) != {r["id"] for r in reference}:
        raise ValueError(f"整形結果に過不足があります: {output}")
    terms = correct = changed = 0
    for row in reference:
        hyp = hypotheses[row["id"]]
        correct += calculate_term_accuracy(row["terms"], row.get("glossary", []), hyp)["correct"]
        terms += len(row["terms"])
        if custom:
            changed += calculate_term_accuracy([row["custom"]["surface"]], [], hyp)["correct"]
    out = {"terms": terms, "correct": correct, "rows": len(reference), "cer": calculate_cer(
        [r["target_text"] for r in reference], [hypotheses[r["id"]] for r in reference])}
    if custom:
        out["changed_term_correct"] = changed
    return out


def evaluate() -> None:
    """固定した条件で容量評価の推論器を呼び、要約と進捗を保存する。"""
    out = WORK / "inference"
    result = {}
    arguments = ["--model", str(MODEL), "--glossary", *map(str, DICT),
                 "--max-glossary", "48", "--batch-size", "32"]
    jobs = []
    for split in (*CUSTOM_SPLITS, *REGULAR_SPLITS):
        is_custom = split in CUSTOM_SPLITS
        exclusion = str(EXCLUSIONS) if split in {"test-novel", "novel-custom"} else "-"
        if is_custom:
            tts_manifest = WORK / "tts" / split / "manifest.jsonl"
            planned = len(read(WORK / f"{split}-input.jsonl"))
            if not tts_manifest.exists() or not tts_manifest.stat().st_size:
                result[split] = {"rows": 0, "planned": planned, "status": "評価できる音声がない"}
                continue
            manifest, stats = prepare_custom(split)
            result[split] = stats
            stats["planned"] = planned
            path = WORK / "evaluation" / split
            first, qwen = path / "first_pass.jsonl", path / "qwen_hypothesis.jsonl"
            inputs = [(mode, path / f"{mode}-combined_text.jsonl",
                       path / f"{mode}-glossary.jsonl") for mode in ("base", "custom")]
        else:
            manifest, first, combined, qwen = regular_files(split)
            baseline = SAVED / f"{split}-max48-haas-qwen.jsonl"
            result[split] = {"base": score(manifest, baseline, False)}
            inputs = [("custom", combined, prepare_regular(split))]
        for mode, combined, glossary in inputs:
            job = f"{split}-{mode}"
            jobs.append((split, mode, manifest, job, is_custom))
            if (out / f"{job}.summary.json").exists():
                continue
            arguments.extend(["--glossary-run", job, str(glossary), "--job-multiasr", job,
                              str(manifest), str(first), str(combined), str(qwen), exclusion])
    if "--job-multiasr" in arguments:
        # sys.executableをそのまま使い、既存の仮想環境を維持する。
        out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORK, prefix="formatter-batch-") as batch:
            subprocess.run([sys.executable, str(WORK / "voiceime-custom-formatter.py"),
                            "--out-dir", batch, *arguments], check=True)
            for artifact in Path(batch).iterdir():
                artifact.replace(out / artifact.name)
    for split, mode, manifest, job, custom in jobs:
        result[split][mode] = score(manifest, out / f"{job}.jsonl", custom)
    (WORK / "evaluation-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    with (WORK / "PROGRESS.md").open("a") as progress:
        progress.write("- 段階2完了 " + "、".join(
            (f"{split} {r['base']['changed_term_correct']}→{r['custom']['changed_term_correct']}/{r['rows']}"
             if r["rows"] else f"{split} 評価0件")
            for split, r in result.items() if split in CUSTOM_SPLITS) + "。\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    evaluate()
