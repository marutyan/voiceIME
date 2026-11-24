"""合成音声を既存の2 ASRで認識し、条件Dの一覧と区間採否まで保存する。"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import train_pipeline as prior_asr
from teacher import read, write
from voiceime.asr.base import load_audio
from voiceime.engine import asr_hints, merge_two_pass_text
from voiceime.formatter.glossary import GlossaryIndex, load_glossary, load_term_list

# 容量評価と同じ用語集・除外リストを使う。trainだけ全held-outを除く。
HOME = Path.home()
WORK = HOME / "voiceime-work-custom"
FR = HOME / "voiceime-work-fr3/inputs"
NOVEL = FR / "test-novel-20261122"
DICT = (NOVEL / "glossary-v1.jsonl", NOVEL / "glossary-v2.jsonl")
HELDOUT = HOME / "voiceime-work-asr/r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
CUSTOM = WORK / "glossary-custom-readings.jsonl"
MODE = {"base": None, "custom": CUSTOM}


def selection(name: str, mode: str) -> GlossaryIndex:
    """上限48の容量評価にそろえ、追加読みを照合専用の索引に載せる。"""
    excluded = set()
    if name in {"novel-custom", "test-novel"}:
        excluded = load_term_list(NOVEL / "exclude-v2-83.txt")
    if name == "train-custom":
        excluded = load_term_list(HELDOUT)
        # held-outの表記の大小文字差も除く。
        from prepare import key
        protected = {key(value) for value in excluded}
        entries = load_glossary(*DICT, alt_readings_path=MODE[mode])
        return GlossaryIndex([entry for entry in entries if key(entry.surface) not in protected])
    return GlossaryIndex(load_glossary(*DICT, exclude_terms=excluded, alt_readings_path=MODE[mode]))


def records(entries: list, mode: str) -> list[dict]:
    """整形器には選択した語の基本読みと、custom条件の慣習読みを提示する。"""
    return [{ "surface": e.surface, "readings": list(e.readings + (e.alt_readings if mode == "custom" else ())) }
            for e in entries]


def run_hypotheses(row: dict, qwen: str, indexes: dict, worker: prior_asr.SpeechWorker) -> dict:
    """同じHaas初回とQwenを使って候補を選び、必要な候補の再認識をまとめる。"""
    audio = load_audio(Path(row["audio_abs"]))
    started = time.perf_counter()
    first = worker.transcribe(audio, None).text
    result = {"id": row["id"], "first_pass": first, "qwen_hypothesis": qwen,
              "haas_first_latency_s": time.perf_counter() - started}
    text = first + "\n" + qwen
    second_by_hints = {}
    for mode, (index, by_surface) in indexes.items():
        candidates = index.select(text, max_entries=20 if row["split"] == "train" else 48)
        hints = asr_hints(candidates[:16], "surface-reading") or []
        hints_key = tuple((term.surface, term.reading) for term in hints)
        if not hints_key:
            second_by_hints[hints_key] = first
        if hints_key not in second_by_hints:
            second_by_hints[hints_key] = worker.transcribe(audio, hints).text
        second = second_by_hints[hints_key]
        merged = merge_two_pass_text(first, second, [by_surface[t.surface] for t in hints])
        result[mode] = {"second_pass": second, "combined_text": merged.text,
                        "hints": [asdict(term) for term in hints],
                        "glossary": records(candidates, mode)}
    return result


def recognize(name: str) -> None:
    """Qwenの後に、既存のCUDA encoder・CPU decodeでHaasを実行する。"""
    tts = WORK / "tts" / name
    output = WORK / "asr" / name
    output.mkdir(parents=True, exist_ok=True)
    manifest = read(tts / "manifest.jsonl")
    for row in manifest:
        row["audio_abs"] = str(tts / row["audio_path"])
    prior_asr.OUTPUTS = output
    variants = ("custom",) if name == "train-custom" else tuple(MODE)
    indexes = {mode: selection(name, mode) for mode in variants}
    indexes = {mode: (index, {e.surface: e for e in index.entries}) for mode, index in indexes.items()}
    completed = []
    for shard, start in enumerate(range(0, len(manifest), 1024)):
        rows = manifest[start:start+1024]
        final = output / f"haas-{shard:03d}.jsonl"
        if final.exists():
            results = read(final)
        else:
            qwen_path, _ = prior_asr.qwen_firstpass(shard, rows)
            qwen = {row["id"]: row["hyp"] for row in read(qwen_path)}
            workers = min(18, len(rows))

            def batch(part: list[dict]) -> list[dict]:
                """1つのHaas workerで割り当てられた発話を処理し、確実に停止する。"""
                worker = prior_asr.SpeechWorker(2)
                try:
                    return [run_hypotheses(row, qwen[row["id"]], indexes, worker) for row in part]
                finally:
                    worker.close()

            with ThreadPoolExecutor(max_workers=workers) as executor:
                grouped = executor.map(batch, (rows[i::workers] for i in range(workers)))
                by_id = {result["id"]: result for group in grouped for result in group}
            results = [by_id[row["id"]] for row in rows]
            write(final, results)
        if [r["id"] for r in rows] != [r["id"] for r in results]:
            raise ValueError("ASRの完了IDがmanifestと異なります")
        completed.extend(results)
        print(f"{name} ASR {len(completed)}/{len(manifest)}", flush=True)
    write(output / "combined.jsonl", completed)


def train_material() -> None:
    """既存の条件D loaderが参照する形式で、元の正解文と3入力を保存する。"""
    output = WORK / "train-material"
    output.mkdir(exist_ok=True)
    name = "train-custom"
    manifest_path = WORK / "tts" / name / "manifest.jsonl"
    manifests = {r["id"]: r for r in read(manifest_path)} if manifest_path.exists() else {}
    rows = read(WORK / "asr" / name / "combined.jsonl") if manifests else []
    if [r["id"] for r in rows] != list(manifests):
        raise ValueError("trainのTTSとASRのIDが一致しません")
    from prepare import heldout_pattern, key
    protected = {key(term) for term in load_term_list(HELDOUT)}
    novel = {key(term) for r in read(
        HOME / "voiceime-work-tts/outputs/r3-test-novel-20261122/manifest.jsonl") for term in r["terms"]}
    protected.update(novel)
    pattern = heldout_pattern(novel)
    eval_pairs = {(r["target_text"], key(r["custom"]["surface"]))
                  for name2 in ("val-custom", "novel-custom")
                  for r in read(WORK / f"{name2}-input.jsonl")}
    if any((r["target_text"], key(r["custom"]["surface"])) in eval_pairs
           or any(key(t) in protected for t in r["terms"]) for r in manifests.values()):
        raise ValueError("trainに評価の文・用語の組かheld-outの語が混ざっています")
    examples = []
    excluded = []
    for row in rows:
        manifest = manifests[row["id"]]
        text_fields = {
            "target_text": manifest["target_text"], "spoken_text_mixed": manifest["spoken_text_mixed"],
            "first_pass": row["first_pass"], "combined_text": row["custom"]["combined_text"],
            "qwen_hypothesis": row["qwen_hypothesis"],
        }
        matches = {field: [m[0] for m in pattern.finditer(key(text))] for field, text in text_fields.items()}
        matches = {field: found for field, found in matches.items() if found}
        if matches:
            excluded.append({"id": row["id"], "matches": matches})
            continue
        if any(key(entry["surface"]) in protected for entry in row["custom"]["glossary"]):
            raise ValueError("trainの用語一覧にheld-out語があります")
        examples.append({"id": row["id"], "target_text": manifest["target_text"],
                         "split": "train", "source_id": manifest["custom"]["source_id"],
                         "spoken_marked": manifest["spoken_marked"],
                         "spoken_text": manifest["spoken_text"],
                         "terms": manifest["terms"], "glossary_fixed": True,
                         "gold_glossary": manifest["glossary"],
                         "glossary": row["custom"]["glossary"], "custom": manifest["custom"],
                         "first_pass": row["first_pass"],
                         "combined_text": row["custom"]["combined_text"],
                         "qwen_hypothesis": row["qwen_hypothesis"]})
    write(output / "train.jsonl", examples)
    for path, field in (("first-pass", "first_pass"), ("segment-merge", "combined_text"),
                        ("qwen06-hypothesis", "qwen_hypothesis")):
        write(output / f"{path}.jsonl", [{"id": row["id"], "hyp": row[field]} for row in examples])
    write(output / "formatter-glossary.jsonl", [{"id": r["id"], "glossary": r["glossary"]} for r in examples])
    write(output / "excluded-novel-surface.jsonl", excluded)
    count = len(examples)
    summary = {"rows": count, "term_types": len({r["custom"]["surface"] for r in examples}),
               "tts_asr_rows": len(rows), "excluded_novel_surface_rows": len(excluded),
               "tts": str(WORK / "tts" / name), "asr": str(WORK / "asr" / name),
               "train": str(output / "train.jsonl"), "planned": len(read(WORK / f"{name}-input.jsonl"))}
    (WORK / "train-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (WORK / "PROGRESS.md").open("a") as progress:
        progress.write(f"- 段階3完了 条件Dの学習材料 {count}/{summary['planned']}行、{summary['term_types']}語。{output}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("val-custom", "novel-custom", "train-custom", "material"))
    arg = parser.parse_args().split
    if arg == "material":
        train_material()
    else:
        recognize(arg)
