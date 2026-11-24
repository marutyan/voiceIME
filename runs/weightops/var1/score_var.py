"""通常の容量評価と、固定したval-ゆれの正答・挿入を集計する。"""

import argparse
import fcntl
import json
from collections import Counter, defaultdict
from datetime import datetime

from score_fix import MANIFESTS, WORK, read_rows, score
from score_fix2 import common_seen_terms, extra_counts
from score_full import score_model

OUTPUT = WORK / "runs/var1"
INPUT = WORK / "var1/val-variants"
SPLIT = "val-variants"
MODELS = ("FULL-scratch", "VAR-cont", "VAR-scratch")


def variant_score(tag):
    """変更した語と全正解語を出現単位で数え、未発話語の挿入も従来定義で測る。"""
    manifest = INPUT / "manifest.jsonl"
    MANIFESTS[SPLIT] = manifest
    glossary = INPUT / "formatter-glossary.jsonl"
    run = OUTPUT / tag / f"{SPLIT}.jsonl"
    scores = score(run, SPLIT, glossary)
    extra = extra_counts(run, SPLIT, glossary, set())
    for mode, values in scores.items():
        values.update(extra[mode])
    changed = {row["id"]: row for row in read_rows(INPUT / "changed.jsonl")}
    clean_run = WORK / f"runs/capacity/{tag}/inference/val-max32-haas-qwen.jsonl"
    clean = {row["id"]: row for row in read_rows(clean_run) if row["id"] in changed}
    modified = {row["id"]: row for row in read_rows(run)}
    if changed.keys() != clean.keys() or changed.keys() != modified.keys():
        raise ValueError("変更対象と評価結果のIDが一致しません")
    if any(clean[sample_id]["glossary"] != row["glossary"] for sample_id, row in modified.items()):
        raise ValueError("変更前の評価と一覧が一致しません")
    totals = Counter(total=0, correct=0, clean_correct=0)
    by_passes = defaultdict(lambda: totals.copy())
    for sample_id, row in changed.items():
        term = row["term"]
        counts = by_passes[len(row["changes"])]
        counts["total"] += 1
        counts["correct"] += term in modified[sample_id]["hyp"]
        counts["clean_correct"] += term in clean[sample_id]["hyp"]
    for counts in by_passes.values():
        totals.update(counts)
    scores["changed_terms"] = {**totals, "by_changed_passes": dict(sorted(by_passes.items()))}
    return scores


def save_progress(tag, result):
    """比較用JSONを保存したあと、条件ごとの結果をロック付きで1行追記する。"""
    score_path = OUTPUT / f"{tag}.json"
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if score_path.exists():
        if score_path.read_text() != payload:
            raise ValueError(f"{tag}: 保存済み集計と一致しません")
    else:
        with score_path.open("x") as sink:
            sink.write(payload)
    cap = "max32-haas-qwen"
    val = result["capacity"]["val"][cap]
    novel = result["capacity"]["test-novel"][cap]["raw"]
    changed = result["val_variants"]["changed_terms"]
    perturbed = result["val_variants"]["raw"]
    prefix = f"- {tag} "
    line = (
        f"{prefix}（{datetime.now().astimezone():%m-%d %H:%M %Z}）"
        f"上限32 val {val['raw']['correct']}/{val['raw']['terms']}・CER {val['raw']['cer']['rate']:.2%}"
        f"・言い直し削除 {val['self_correction']['cer']['deletions']}"
        f"、test-novel {novel['correct']}/{novel['terms']}"
        f"、val-ゆれ変更語 {changed['correct']}/{changed['total']}"
        f"・全正解 {perturbed['correct']}/{perturbed['terms']}"
        f"・未発話語挿入 {perturbed['unspoken_insertions']}\n"
    )
    with (OUTPUT / "PROGRESS.md").open("a+", encoding="utf-8") as sink:
        fcntl.flock(sink, fcntl.LOCK_EX)
        sink.seek(0)
        previous = sink.read()
        if not previous:
            sink.write("# VARの評価進捗\n\n")
        if not any(existing.startswith(prefix) for existing in previous.splitlines()):
            sink.write(line)
    print(line, end="")


def main():
    """指定した1条件を採点して、通常とゆれの結果を同時に記録する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", choices=MODELS)
    tag = parser.parse_args().tag
    seen = common_seen_terms()
    result = {
        "capacity": score_model(tag, seen, read_rows(MANIFESTS["val"])),
        "val_variants": variant_score(tag),
    }
    save_progress(tag, result)


if __name__ == "__main__":
    main()
