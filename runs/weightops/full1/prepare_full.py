"""実ASR出力を条件Dの学習入力に結合し、元の正解文へfix1の規則を当てる。"""

import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

from fix_omitted_terms import fix_row, surface_key, write_jsonl

HOME = Path.home()
WORK = HOME / "voiceime-work-wops"
INPUTS = HOME / "voiceime-work-fr3/inputs"
ASR = HOME / "voiceime-work-asr/r3-multiasr-train-20261123/outputs"
LEGACY = INPUTS / "d-multiasr-20261123/train-runs"
TRAIN = INPUTS / "sft3-20261122/train-sft3.jsonl"
AUG = WORK / "fix1/data/augmentation-fixed.jsonl"
HELDOUT = HOME / "voiceime-work-asr/r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
POOL = INPUTS / "d-multiasr-20261123/legacy/training-glossary.jsonl"
DATA = WORK / "full1/data"
ASR_SOURCES = {"train-available-12000.jsonl": 12000, "train-topup44970.jsonl": 44970}
RUN_FIELDS = {
    "first-pass.jsonl": ("haas_first_pass_hyp", "hyp"),
    "segment-merge.jsonl": ("segment_merge_hyp", "hyp"),
    "qwen06-hypothesis.jsonl": ("qwen06_first_pass_hyp", "hyp"),
    "formatter-glossary.jsonl": ("formatter_glossary", "glossary"),
}


def records(path):
    """大きな入力を順に読み、必要な欄だけを保持できるようにする。"""
    with path.open(encoding="utf-8") as source:
        for line in source:
            yield json.loads(line)


def load_runs(train, available):
    """提供された実ASRと既存の別系列の実ASRを、条件Dで使う4欄へ揃える。"""
    runs = {}
    origins = {}
    for name, expected in ASR_SOURCES.items():
        count = 0
        for row in records(ASR / name):
            sample_id = row["id"]
            if sample_id in runs or train[sample_id]["target_text"] != row["target_text"]:
                raise ValueError(f"{name}: IDの重複または元データとの不一致 {sample_id}")
            if row["dataset"] != "train" or not row["speaker"].startswith("tts-"):
                raise ValueError(f"{name}: 学習用合成音声ではありません: {sample_id}")
            runs[sample_id] = tuple(row[field] for field, _ in RUN_FIELDS.values())
            origins[sample_id] = name
            count += 1
        if count != expected:
            raise ValueError(f"{name}: {count}行、期待値{expected}行")

    previous = {}
    for name, (_, key) in RUN_FIELDS.items():
        previous[name] = {r["id"]: r[key] for r in records(LEGACY / name)}
    reference = set(previous["first-pass.jsonl"])
    if any(set(values) != reference for values in previous.values()):
        raise ValueError("従来のASR結果で4欄のIDが一致しません")
    for sample_id in reference:
        old = tuple(previous[name][sample_id] for name in RUN_FIELDS)
        if sample_id in runs:
            if runs[sample_id] != old:
                raise ValueError(f"既存の実ASR結果と不一致: {sample_id}")
        else:
            if sample_id not in train:
                raise ValueError(f"元データに無い従来のASR結果: {sample_id}")
            runs[sample_id] = old
            origins[sample_id] = "legacy"
    for sample_id, (*hyps, glossary) in runs.items():
        if any(not isinstance(hyp, str) for hyp in hyps):
            raise ValueError(f"ASR結果の形式が違います: {sample_id}")
        if len(glossary) > 20 or any(entry["surface"] not in available for entry in glossary):
            raise ValueError(f"学習用一覧の上限か用語集に違反: {sample_id}")
    return runs, origins


def write_runs(rows, runs):
    """学習に残った行のASR結果を、条件Dの学習コードが読める形式で書く。"""
    directory = DATA / "train-runs"
    directory.mkdir()
    with ExitStack() as stack:
        files = [(stack.enter_context((directory / name).open("x")), key)
                 for name, (_, key) in RUN_FIELDS.items()]
        for row in rows:
            sample_id = row["id"]
            if sample_id in runs:
                for (sink, key), value in zip(files, runs[sample_id], strict=True):
                    sink.write(json.dumps({"id": sample_id, key: value}, ensure_ascii=False) + "\n")


def main():
    """レコードをIDで照合して、新しい学習データと集計を書き出す。"""
    protected = {surface_key(term) for term in HELDOUT.read_text().splitlines() if term.strip()}
    available = {row["surface"] for row in records(POOL)}
    if protected & {surface_key(term) for term in available}:
        raise ValueError("学習用用語集に除外語があります")
    train = {row["id"]: row for row in records(TRAIN)}
    if len(train) != 95934:
        raise ValueError("元の学習行数が想定と違います")
    runs, origins = load_runs(train, available)

    counts = Counter()
    decisions = Counter()
    kept = []
    omitted = set()
    learned = set()
    for sample_id, row in train.items():
        learned.update(term for term in row["terms"] if term in row["target_text"])
        origin = origins.get(sample_id, "without_asr")
        if row.get("omitted_terms"):
            term, = row["omitted_terms"]
            surface = surface_key(term["surface"])
            omitted.add(surface)
            first, merged, qwen, entries = runs.get(sample_id, (None, None, None, None))
            row, reason = fix_row(row, term, entries, first, merged, qwen, surface in protected, "glossary")
            decisions[(origin, reason)] += 1
            if row is None:
                continue
        counts[origin] += 1
        kept.append(row)

    augmentation_terms = set()
    augmentation_rows = 0
    with AUG.open("rb") as source:
        aug_hash = hashlib.file_digest(source, "sha256").hexdigest()
    for row in records(AUG):
        augmentation_rows += 1
        augmentation_terms.update(surface_key(term) for term in row["terms"])
    excluded = omitted | augmentation_terms
    eligible = {term for term in learned if surface_key(term) not in excluded}
    DATA.mkdir()
    (DATA / "seen-drop-terms.txt").write_text("".join(f"{term}\n" for term in sorted(eligible)))
    write_jsonl(DATA / "train-fixed.jsonl", kept)
    write_runs(kept, runs)

    decision_table = {}
    for (origin, reason), count in sorted(decisions.items()):
        decision_table.setdefault(origin, {})[reason] = count
    result = {
        "train_rows_before": len(train),
        "train_rows_after": len(kept),
        "input_asr_rows": dict(Counter(origins.values())),
        "kept_by_source": dict(counts),
        "omitted_decisions_by_source": decision_table,
        "augmentation_rows": augmentation_rows,
        "augmentation_sha256": aug_hash,
        "learned_types": len(learned),
        "excluded_omitted_types_normalized": len(omitted),
        "excluded_augmentation_types_normalized": len(augmentation_terms),
        "eligible_drop_types": len(eligible),
    }
    result["sha256"] = {}
    for file in (TRAIN, *(ASR / name for name in ASR_SOURCES), *(DATA.glob("*.jsonl")),
                 DATA / "seen-drop-terms.txt", *sorted((DATA / "train-runs").glob("*.jsonl"))):
        with file.open("rb") as source:
            result["sha256"][str(file)] = hashlib.file_digest(source, "sha256").hexdigest()
    (DATA / "data-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
