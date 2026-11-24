#!/usr/bin/env python3
"""実音声のmanifestと、字幕を保った条件Dの学習行を組み立てる。"""

import argparse
import hashlib
import json
import os
import random
import re
import time
import unicodedata
from collections import Counter
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path

from select_candidates import GlossaryMatcher, normalize
from voiceime.eval.metrics import calculate_cer, count_residual_fillers
from voiceime.formatter.glossary import load_glossary, load_term_list

ROOT = Path.home() / "voiceime-work-real"
HOME = Path.home()
PUB_EVAL = HOME / "voiceime-work-pubdata/final-manifest/pub-eval.jsonl"
ASR = HOME / "voiceime-work-asr"
FR3 = HOME / "voiceime-work-fr3"
WOPS = HOME / "voiceime-work-wops"
FIX = WOPS / "fix2"
ORIGINAL = FR3 / "inputs/sft3-20261122/train-sft3.jsonl"
ORIGINAL_SWAP = WOPS / "rsi1/data/augmentation.jsonl"
SYNTHETIC = FIX / "data/train-fixed.jsonl"
SWAP = FIX / "data/augmentation-fixed.jsonl"
NOVEL = FR3 / "inputs/test-novel-20261122/test-novel.jsonl"
D_INPUT = FR3 / "inputs/d-multiasr-20261123"
MULTIASR = ASR / "r3-multiasr-20261122/outputs"
RSI = WOPS / "outputs/RSI-0.8B/best"
HELDOUT = ASR / "r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
RUN_FIELDS = {
    "first-pass": ("haas_first_pass_hyp", "haas_first_pass_latency_s"),
    "segment-merge": ("segment_merge_hyp", "haas_second_pass_latency_s"),
    "qwen06-hypothesis": ("qwen06_first_pass_hyp", "qwen06_first_pass_latency_s"),
}


def sha256(path):
    """faculty内部で入力ファイルのハッシュを検証する。"""
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def freeze_inputs():
    """既存の入力が後続ジョブの開始時まで変わっていないか照合できるようにする。"""
    run_files = [f"{name}.jsonl" for name in RUN_FIELDS] + ["formatter-glossary.jsonl"]
    inputs = [
        ORIGINAL, ORIGINAL_SWAP, SYNTHETIC, SWAP, NOVEL, PUB_EVAL,
        FIX / "data/fix-audit.json", FIX / "data/verify-dynamic.json",
        WOPS / "rsi1/train_support.py",
        *(RSI / name for name in (
            "model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json",
            "chat_template.jinja", "generation_config.json",
        )),
        FR3 / "inputs/val-select.jsonl", FR3 / "inputs/manifest-val-no-audio.jsonl",
        D_INPUT / "legacy/training-glossary.jsonl", NOVEL.parent / "a-plain.jsonl",
        *(D_INPUT / run / filename for run in ("train-runs", "val-runs") for filename in run_files),
        *(NOVEL.parent / filename for filename in ("glossary-v1.jsonl", "glossary-v2.jsonl", "exclude-v2-83.txt")),
        *(MULTIASR / filename for filename in (
            "haas-plus-qwen06-test-novel-segment-merge.jsonl",
            "multiasr-test-novel-qwen06-firstpass.jsonl", "formatter-glossary-qwen06-test-novel.jsonl",
        )),
        ASR / "data/glossary/glossary.jsonl", ASR / "data/glossary/glossary-v2.jsonl", HELDOUT,
    ]
    info = {str(path): sha256(path) for path in inputs}
    audit = json.loads(ORIGINAL_SWAP.with_name("augmentation-audit.json").read_text())
    assert info[str(ORIGINAL_SWAP)] == audit["augmentation_sha256"]
    assert all(info[path] == value for path, value in audit["sources_sha256"].items() if path in info)
    corrected = json.loads((FIX / "data/fix-audit.json").read_text())
    assert info[str(SYNTHETIC)] == corrected["train"]["fix2_sha256"]
    assert info[str(SWAP)] == corrected["augmentation"]["fix2_sha256"]
    write_stats("frozen-inputs", info)


def verify_inputs():
    """元データ、差し替え、評価入力、初期重みが同じであることを確認する。"""
    ledger = json.loads((ROOT / "stats/frozen-inputs.json").read_text())
    for path, expected in ledger.items():
        if sha256(Path(path)) != expected:
            raise ValueError(f"実験開始時と入力ファイルのSHA-256が異なります: {path}")


def read_rows(path):
    """JSONLを改行ごとに読み込む。"""
    with path.open() as file:
        return [json.loads(line) for line in file if line.strip()]


def write_rows(path, rows):
    """書き終えたJSONLだけを後続処理へ渡す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def write_stats(name, value):
    """手元で使う集計JSONを保存する。"""
    path = ROOT / "stats" / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def key_char(char):
    """句読点・記号・空白以外を大文字小文字を区別せずに比較する。"""
    return "" if char.isspace() or unicodedata.category(char)[0] in "PS" else char.casefold()


def text_key(text):
    """CERの表記置換とは別に、教師文が字幕の文字を保つか確認する。"""
    return "".join(map(key_char, text))


def indexed_key(text):
    """比較用の文字ごとに、原文での位置を返す。"""
    chars = []
    positions = []
    for pos, char in enumerate(text):
        for lowered in key_char(char):
            chars.append(lowered)
            positions.append(pos)
    return "".join(chars), positions


def copy_punctuation(caption, hypothesis):
    """ASRと字幕で前後の文字が一致する箇所に、日本語の句読点を写す。"""
    source, source_pos = indexed_key(hypothesis)
    target, target_pos = indexed_key(caption)
    insertions = {}
    for block in SequenceMatcher(None, source, target, autojunk=False).get_matching_blocks():
        for j in range(block.size):
            src = block.a + j
            dst = block.b + j
            pair_inside = j + 1 < block.size
            both_end = src + 1 == len(source) and dst + 1 == len(target)
            if pair_inside:
                source_gap = hypothesis[source_pos[src] + 1 : source_pos[src + 1]]
                target_gap = caption[target_pos[dst] + 1 : target_pos[dst + 1]]
            elif both_end:
                source_gap = hypothesis[source_pos[src] + 1 :]
                target_gap = caption[target_pos[dst] + 1 :]
            else:
                continue
            punctuation = "".join(char for char in source_gap if char in "、。！？")
            if punctuation and (not target_gap or target_gap.isspace()):
                insertions[target_pos[dst]] = punctuation
    return "".join(char + insertions.get(pos, "") for pos, char in enumerate(caption))


def extraction_manifests(shard=None):
    """対象のtarシャードが揃うまで待ち、検証済みWAVだけを返す。"""
    selected = read_rows(ROOT / "selection-v3/candidates.jsonl")
    if shard is not None:
        # 音声区間の多い2シャードは、残りの取得を待たずにASRへ渡せる。
        large = {"0105": 0, "0106": 1}
        selected = [row for row in selected if large.get(row["shard"], 2) == shard]
    expected = {row["shard"] for row in selected}
    status_dir = ROOT / "extract-status"
    status_paths = [status_dir / f"{name}.json" for name in sorted(expected)]
    while not all(path.is_file() for path in status_paths):
        extraction_pid = int((ROOT / "logs/extraction.pid").read_text())
        try:
            os.kill(extraction_pid, 0)
        except ProcessLookupError:
            raise RuntimeError("必要なシャードが揃う前に音声取得が終了した") from None
        time.sleep(60)
    valid = [
        row for path in status_paths for row in read_rows(path.with_suffix(".jsonl"))
    ]
    ids = {row["id"] for row in valid}
    assert len(ids) == len(valid) and ids <= {row["id"] for row in selected}
    assert not {row["video_id"] for row in valid} & {row["video_id"] for row in read_rows(PUB_EVAL)}
    return selected, valid, status_paths


def manifest_for_asr(shard):
    """指定グループのASR入力を音声長の降順で保存する。"""
    _, valid, _ = extraction_manifests(shard)
    valid.sort(key=lambda row: (row["start_ms"] - row["end_ms"], row["id"]))
    assert valid
    write_rows(ROOT / "asr-inputs" / f"shard-{shard:02d}.jsonl", valid)


def summarize_extraction():
    """全選定区間と再取得できたWAVを、重複を除いた件数と容量で集計する。"""
    selected, valid, status_paths = extraction_manifests()
    recovery = sorted((ROOT / "recovery-status").glob("*.json"))
    stats = [json.loads(path.read_text()) for path in [*status_paths, *recovery]]
    valid_by_id = {row["id"]: row for row in valid}
    for path in recovery:
        for row in read_rows(path.with_suffix(".jsonl")):
            valid_by_id[row["id"]] = row
    assert valid_by_id.keys() <= {row["id"] for row in selected}
    latest = {row["shard"]: row for row in stats}
    write_stats("extraction", {
        "selected": len(selected), "valid": len(valid_by_id), "failed": len(selected) - len(valid_by_id),
        "valid_videos": len({row["video_id"] for row in valid_by_id.values()}),
        "header_requests": sum(row["headers"] for row in stats),
        "webm_bytes": sum(row["webm_bytes"] for row in stats),
        "wav_bytes": sum(Path(row["audio_path"]).stat().st_size for row in valid_by_id.values()),
        "retried_shards": len(recovery),
        "recovered_wavs": len(valid_by_id) - len(valid),
        "shards_with_archive_error": sum("archive" in row["errors"] for row in latest.values()),
        "shards_with_errors": sum(bool(row["errors"]) for row in latest.values()),
    })


def manifest_for_recovery_asr():
    """再取得で増えた区間だけのASR入力を作り、済んだ区間の重複を防ぐ。"""
    selected, valid, _ = extraction_manifests()
    known = {row["id"] for row in valid}
    selected_ids = {row["id"] for row in selected}
    recovered = {}
    for path in (ROOT / "recovery-status").glob("*.jsonl"):
        for row in read_rows(path):
            if row["id"] not in known:
                recovered[row["id"]] = row
    assert recovered.keys() <= selected_ids
    rows = sorted(recovered.values(), key=lambda row: (row["start_ms"] - row["end_ms"], row["id"]))
    write_rows(ROOT / "asr-inputs/shard-03.jsonl", rows)


def wait_for_recovery():
    """補充ASRが終わるまで待ち、途中終了を成功と扱わない。"""
    process_file = ROOT / "logs/recovery.pid"
    marker = ROOT / "logs/recovery-complete"
    if not process_file.exists():
        return
    while not marker.exists():
        try:
            os.kill(int(process_file.read_text()), 0)
        except ProcessLookupError:
            if not marker.exists():
                raise RuntimeError("補充ASRの完了前に再取得処理が終了した") from None
        time.sleep(60)


def runs_to_files(directory, rows):
    """既存評価器が読む条件DのASR runと固定用語一覧を保存する。"""
    for name, (hypothesis, latency) in RUN_FIELDS.items():
        write_rows(directory / f"{name}.jsonl", (
            {"id": row["id"], "hyp": row[hypothesis], "latency_s": row[latency]} for row in rows
        ))
    write_rows(directory / "formatter-glossary.jsonl", (
        {"id": row["id"], "glossary": row["formatter_glossary"]} for row in rows
    ))


def prepare_teacher():
    """CERで実音声学習候補を絞り、教師モデル用に保存する。"""
    wait_for_recovery()
    summarize_extraction()
    kept = []
    stats = Counter(dict.fromkeys((
        "recognized", "kept", "both_asr_empty", "caption_empty_after_normalization",
        "both_cer_above_15_percent", "both_pass", "haas_only", "qwen_only",
    ), 0))
    for shard in range(4):
        subset = f"{shard:02d}"
        path = ROOT / "asr-inputs" / f"shard-{subset}.jsonl"
        if shard == 3 and (not path.exists() or not path.stat().st_size):
            continue
        inputs = read_rows(path)
        results = read_rows(ROOT / "asr" / f"train-{subset}" / f"combined-shard-{subset}.jsonl")
        assert {row["id"] for row in inputs} == {row["id"] for row in results}
        assert len(inputs) == len(results)
        for row in results:
            stats["recognized"] += 1
            caption = row["spoken_text"]
            hyps = [row["haas_first_pass_hyp"], row["qwen06_first_pass_hyp"]]
            if not any(hyp.strip() for hyp in hyps):
                stats["both_asr_empty"] += 1
                continue
            rates = [calculate_cer([caption], [hyp])["rate"] for hyp in hyps]
            if rates[0] is None:
                stats["caption_empty_after_normalization"] += 1
                continue
            passes = tuple(rate <= 0.15 for rate in rates)
            if not any(passes):
                stats["both_cer_above_15_percent"] += 1
                continue
            stats["kept"] += 1
            stats["both_pass" if all(passes) else "haas_only" if passes[0] else "qwen_only"] += 1
            row["haas_cer"], row["qwen_cer"] = rates
            kept.append(row)
    assert stats["recognized"] == stats["kept"] + sum(
        stats[name] for name in ("both_asr_empty", "caption_empty_after_normalization", "both_cer_above_15_percent")
    )
    extraction = json.loads((ROOT / "stats/extraction.json").read_text())
    assert stats["recognized"] == extraction["valid"]
    teacher = ROOT / "teacher-inputs"
    write_rows(teacher / "manifest.jsonl", kept)
    runs_to_files(teacher, kept)
    write_stats("cer-filter", dict(stats))


def prepare_pub_eval():
    """評価300件には学習候補のCERによる除外を適用しない。"""
    pub_dir = ROOT / "pub-eval-inputs"
    combined = read_rows(ROOT / "asr/pub-eval/combined-shard-00.jsonl")
    manifest = read_rows(PUB_EVAL)
    assert len(combined) == len(manifest) == 300
    assert {row["id"] for row in manifest} == {row["id"] for row in combined}
    runs_to_files(pub_dir, combined)


def contains_english(surface):
    """英字を含む用語を日本語字幕での表記照合対象にする。"""
    return re.search(r"[a-z]", normalize(surface)) is not None


def matches(matcher, text):
    """字幕やASRに現れた表記を、出現回数を保って返す。"""
    return [row["surface"] for row in matcher.find(text)[0]]


def prepare_training():
    """正解文候補を検証し、比較2条件の混合比と監査を保存する。"""
    verify_inputs()
    sources = read_rows(ROOT / "teacher-inputs/manifest.jsonl")
    predictions = read_rows(ROOT / "teacher-output/real-teacher.jsonl")
    assert [row["id"] for row in sources] == [row["id"] for row in predictions]
    entries = load_glossary(ASR / "data/glossary/glossary.jsonl", ASR / "data/glossary/glossary-v2.jsonl")
    glossary = {entry.surface: asdict(entry) for entry in entries if contains_english(entry.surface)}
    matcher = GlossaryMatcher([{"surface": term, "readings": []} for term in glossary], set())
    novel = {term for row in read_rows(NOVEL) for term in row["novel_terms"]}
    heldout = load_term_list(HELDOUT)
    novel_matcher = GlossaryMatcher([{"surface": term, "readings": []} for term in novel], set())
    mask = {normalize(term) for term in novel | heldout}
    assert len(novel) == 500
    counts = Counter()
    examples = []
    rows = []
    novel_references = set()
    novel_inputs = set()
    novel_reference_by_id = {}
    novel_input_by_id = {}
    for source, prediction in zip(sources, predictions, strict=True):
        caption = source["spoken_text"]
        hypothesis = prediction["hyp"]
        haas = source["haas_first_pass_hyp"]
        qwen = source["qwen06_first_pass_hyp"]
        if prediction["finish_reason"] == "eos" and text_key(hypothesis) == text_key(caption):
            method = "rsi"
            target = hypothesis
        else:
            best_asr = haas if source["haas_cer"] <= source["qwen_cer"] else qwen
            target = copy_punctuation(caption, best_asr)
            method = "punctuation_copied" if target != caption else "caption_unchanged"
            counts["rsi_length_limited" if prediction["finish_reason"] == "length" else "rsi_text_changed"] += 1
        assert text_key(target) == text_key(caption)
        terms = matches(matcher, caption)
        counts[method] += 1
        counts["with_english_terms"] += bool(terms)
        counts["english_term_occurrences"] += len(terms)
        fillers = max(count_residual_fillers(caption, hyp) for hyp in (haas, qwen))
        counts["asr_extra_filler_form_rows"] += bool(fillers)
        listed = source["formatter_glossary"]
        assert len(listed) <= 20 and all(normalize(entry["surface"]) not in mask for entry in listed)
        exposed_references = matches(novel_matcher, target)
        exposed_inputs = matches(novel_matcher, "\n".join([haas, qwen, source["segment_merge_hyp"]]))
        novel_references.update(exposed_references)
        novel_inputs.update(exposed_inputs)
        counts["target_rows_with_test_novel_surface"] += bool(exposed_references)
        counts["asr_rows_with_test_novel_surface"] += bool(exposed_inputs)
        clip_id = source["id"]
        novel_reference_by_id[clip_id] = exposed_references
        novel_input_by_id[clip_id] = exposed_inputs
        row = {
            "id": clip_id, "target_text": target, "terms": terms,
            "gold_glossary": [glossary[term] for term in dict.fromkeys(terms)],
            "first_pass": haas, "combined_text": source["segment_merge_hyp"],
            "qwen_hypothesis": qwen, "glossary": listed,
        }
        rows.append(row)
        examples.append({
            "id": clip_id, "caption": caption, "target": target, "method": method,
            "haas": haas, "haas_second": source["haas_second_pass_plain_hyp"],
            "segment_merge": source["segment_merge_hyp"], "qwen": qwen,
            "haas_cer": source["haas_cer"], "qwen_cer": source["qwen_cer"],
            "terms": terms, "glossary": [entry["surface"] for entry in listed],
            "asr_extra_filler_forms": fillers,
        })
    assert rows
    counts.update({
        "available_rows": len(rows),
        "test_novel_surfaces_in_targets": len(novel_references),
        "test_novel_surfaces_in_asr": len(novel_inputs),
    })
    write_stats("targets", counts)
    rng = random.Random(0)
    # 教師文の決め方を目視できるよう各方法を最大10件確保する。
    examples.sort(key=lambda row: row["id"])
    rng.shuffle(examples)
    chosen = []
    for method in ("rsi", "punctuation_copied", "caption_unchanged"):
        chosen.extend([row for row in examples if row["method"] == method][:10])
    was_chosen = {row["id"] for row in chosen}
    chosen.extend([row for row in examples if row["id"] not in was_chosen][:30 - len(chosen)])
    write_rows(ROOT / "stats/examples.jsonl", chosen)

    audit = json.loads((FIX / "data/fix-audit.json").read_text())
    dynamic = json.loads((FIX / "data/verify-dynamic.json").read_text())
    assert all(dynamic[name]["target_without_surface"] == 0 for name in ("train", "augmentation"))
    original = read_rows(SYNTHETIC)
    swap = read_rows(SWAP)
    assert len(original) == audit["train"]["rows"] and len(swap) == audit["augmentation"]["rows"]
    all_ids = {row["id"] for group in (original, swap, rows) for row in group}
    assert len(all_ids) == len(original) + len(swap) + len(rows)
    base = len(original) + len(swap)
    # 全体の20%は実音声数 <= 元データ数 / 4 と等価。
    cap = base // 4
    population = sorted(rows, key=lambda row: row["id"])
    selected = random.Random(0).sample(population, cap) if len(population) > cap else population
    output = ROOT / "training-inputs/REAL-0.8B.jsonl"
    write_rows(output, selected)
    write_stats("REAL-0.8B", {
        "original_rows": len(original), "swap_rows": len(swap),
        "real_rows": len(selected), "real_fraction": len(selected) / (base + len(selected)),
        "real_sha256": sha256(output),
        "synthetic_sha256": sha256(SYNTHETIC), "swap_sha256": sha256(SWAP),
        "test_novel_surfaces_in_real_targets": sorted({
            term for row in selected for term in novel_reference_by_id[row["id"]]
        }),
        "test_novel_surfaces_in_real_asr": sorted({
            term for row in selected for term in novel_input_by_id[row["id"]]
        }),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["asr", "asr-recovery", "extraction", "pub-eval", "teacher", "training", "freeze", "verify"])
    parser.add_argument("--shard", type=int, choices=range(3))
    args = parser.parse_args()
    if args.stage == "asr":
        if args.shard is None:
            parser.error("asrには--shardが必要です")
        manifest_for_asr(args.shard)
    else:
        {
            "extraction": summarize_extraction,
            "asr-recovery": manifest_for_recovery_asr,
            "pub-eval": prepare_pub_eval,
            "teacher": prepare_teacher,
            "training": prepare_training,
            "freeze": freeze_inputs,
            "verify": verify_inputs,
        }[args.stage]()
