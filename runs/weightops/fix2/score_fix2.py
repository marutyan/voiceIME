"""容量評価の既存指標に、一覧外の学習済み語の正答数と発話に無い用語の挿入数を加える。"""

import argparse
import json
import unicodedata
from collections import Counter

from fix_omitted_terms import has_surface, surface_pattern
from score_fix import CAPACITY_LISTS, CAPACITY_VARIANTS, FR3, MANIFESTS, WORK, read_rows, score
from restore_main import restore_listed_readings
from voiceime.formatter.glossary import entry_from_record

BASELINE_MODELS = ("RSI-0.8B", "FIX-0.8B-cont")
MODELS = (*BASELINE_MODELS, "FIX2-0.8B-cont", "FIX2-0.8B-contfix")
TERM_TOTALS = {"val": 1427, "test-novel": 500}


def common_seen_terms():
    """共通の初期学習（RSI）の正解文に表記がある用語を、元データと拡張から求める。"""
    seen = set()
    for path in (
        FR3 / "sft3-20261122/train-sft3.jsonl",
        WORK / "rsi1/data/augmentation.jsonl",
    ):
        with path.open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                seen.update(term for term in row["terms"] if term in row["target_text"])
    return seen


def extra_counts(run_path, split, list_path, seen):
    """一覧外の正解語と、発話に表記も読みも無い用語の出力回数を数える。"""
    samples = {row["id"]: row for row in read_rows(MANIFESTS[split])}
    lists = {row["id"]: row["glossary"] for row in read_rows(list_path)}
    counts = {"raw": Counter(), "restored": Counter()}
    for row in read_rows(run_path):
        sample = samples[row["id"]]
        prompt = lists[row["id"]]
        listed = set(row["glossary"])
        unlisted = Counter(term for term in sample["terms"] if term in seen and term not in listed)
        # 正解文から消えた言い直しも、発話に表記または読みがあれば挿入から除く。
        spoken = sample["spoken_text"]
        kana = sample["spoken_text_kana"] or spoken
        readings = {}
        for entry in (*prompt, *sample.get("glossary", [])):
            readings.setdefault(entry["surface"], set()).update(entry["readings"])
        absent = {
            term for term, forms in readings.items()
            if term not in sample["terms"]
            and not has_surface(spoken, term)
            and not any(form in kana or form in spoken for form in forms if form)
        }
        entries = [entry_from_record(entry) for entry in prompt]
        for mode, hyp in (("raw", row["hyp"]), ("restored", restore_listed_readings(row["hyp"], entries))):
            c = counts[mode]
            if split == "val":
                c["seen_unlisted_total"] += unlisted.total()
                c["seen_unlisted_correct"] += sum(min(n, hyp.count(term)) for term, n in unlisted.items())
            normalized_hyp = unicodedata.normalize('NFKC', hyp).casefold()
            inserted = {term: len(surface_pattern(term).findall(normalized_hyp)) for term in absent}
            c["unspoken_insertions"] += sum(inserted.values())
            c["unspoken_listed_insertions"] += sum(n for term, n in inserted.items() if term in listed)
    return counts


def main():
    """指定条件を採点し、既存の基準値を再現できたことを確認してから集計を出す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    seen = common_seen_terms()
    prior = json.loads((WORK / "fix1/score.json").read_text())["capacity"]
    models = BASELINE_MODELS if args.baseline_only else MODELS
    result = {}
    for model in models:
        result[model] = {}
        for split, expected_total in TERM_TOTALS.items():
            result[model][split] = {}
            for variant in CAPACITY_VARIANTS:
                path = WORK / f"runs/capacity/{model}/inference/{split}-{variant}.jsonl"
                glossary = CAPACITY_LISTS / split / f"{variant}.jsonl"
                metrics = score(path, split, glossary)
                if model in BASELINE_MODELS and metrics != prior[model][split][variant]:
                    raise ValueError(f"{model} {split} {variant}: fix1の採点を再現できません")
                extra = extra_counts(path, split, glossary, seen)
                for mode in metrics:
                    if metrics[mode]["terms"] != expected_total:
                        raise ValueError(f"{model} {split} {variant}: 用語数が一致しません")
                    metrics[mode].update(extra[mode])
                result[model][split][variant] = metrics
    print(json.dumps({"common_seen_term_types": len(seen), "capacity": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
