"""FULLと基準の評価をFIX2と同じ定義で採点し、言い直し行の削除数を加える。"""

import argparse
import fcntl
import json
import re
from datetime import datetime

from score_fix import CAPACITY_LISTS, CAPACITY_VARIANTS, MANIFESTS, WORK, read_rows, score
from score_fix2 import TERM_TOTALS, common_seen_terms, extra_counts
from voiceime.eval.metrics import calculate_tag_metrics

BASELINES = ("RSI-0.8B", "FIX-0.8B-cont", "fixsoup-a050")
FULL = ("FULL-cont", "FULL-scratch", "FULL-cont-drop")
OUT = WORK / "runs/full1"


def self_correction_metrics(path, report, variant, manifest):
    """タグ別削除数を再計算し、容量評価のreportに出た件数と照合する。"""
    hypotheses = {row["id"]: row["hyp"] for row in read_rows(path)}
    samples = [
        {"target_text": row["target_text"], "hyp": hypotheses[row["id"]], "tags": row["tags"]}
        for row in manifest if "self_correction" in row.get("tags", [])
    ]
    tagged = calculate_tag_metrics(samples)["self_correction"]
    prefix = f"| val-{variant} | e2e | self_correction | "
    line, = (line for line in report.splitlines() if line.startswith(prefix))
    count, expected, deletions = map(int, re.search(r"(\d+)/(\d+) \| .*削除 (\d+)\)", line).groups())
    if (count, expected, deletions) != (len(samples), len(samples), tagged["cer"]["deletions"]):
        raise ValueError(f"{path}: 言い直しの削除数がreportと一致しません")
    return tagged


def score_model(model, seen, val):
    """公開済みの一覧と同じ3上限で、各splitの出力を採点する。"""
    model_dir = WORK / "runs/capacity" / model
    val_report = (model_dir / "reports/val.report.txt").read_text()
    result = {}
    for split, expected_total in TERM_TOTALS.items():
        result[split] = {}
        for variant in CAPACITY_VARIANTS:
            path = model_dir / "inference" / f"{split}-{variant}.jsonl"
            glossary = CAPACITY_LISTS / split / f"{variant}.jsonl"
            metrics = score(path, split, glossary)
            extra = extra_counts(path, split, glossary, seen)
            for mode, values in metrics.items():
                if values["terms"] != expected_total:
                    raise ValueError(f"{path}: 用語数が想定と違います")
                values.update(extra[mode])
            if split == "val":
                metrics["self_correction"] = self_correction_metrics(path, val_report, variant, val)
            result[split][variant] = metrics
    return result


def append_progress(model, result):
    """学習と評価が終わった条件の結果を、1条件1行で追記する。"""
    OUT.mkdir(exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    model_path = OUT / f"{model}.json"
    if model_path.exists():
        if model_path.read_text() != payload:
            raise ValueError(f"{model_path}: 前に収集した結果と不一致")
    else:
        with model_path.open("x") as output:
            output.write(payload)
    pieces = []
    for cap, variant in zip((20, 32, 48), CAPACITY_VARIANTS, strict=True):
        val = result["val"][variant]["raw"]
        novel = result["test-novel"][variant]["raw"]
        deletions = result["val"][variant]["self_correction"]["cer"]["deletions"]
        pieces.append(
            f"上限{cap} val {val['correct']}/{val['terms']}・CER {val['cer']['rate']:.2%}"
            f"・一覧外 {val['seen_unlisted_correct']}/{val['seen_unlisted_total']}・言い直し削除 {deletions}"
            f"、test-novel {novel['correct']}/{novel['terms']}"
            f"・一覧内取りこぼし {novel['missed_listed']}・未発話語挿入 {novel['unspoken_insertions']}"
        )
    prefix = f"- {model} "
    with (OUT / "PROGRESS.md").open("a+", encoding="utf-8") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.seek(0)
        previous = output.read()
        if not previous:
            output.write("# FULLの評価進捗\n\n")
        if not any(line.startswith(prefix) for line in previous.splitlines()):
            output.write(f"{prefix}（{datetime.now().astimezone():%m-%d %H:%M %Z}） " + " ｜ ".join(pieces) + "\n")


def main():
    """指定条件の比較用JSONを返し、ジョブ単位では進捗も更新する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", choices=FULL)
    parser.add_argument("models", nargs="*", metavar="CONDITION")
    args = parser.parse_args()
    if args.progress and args.models:
        parser.error("--progressと条件名は同時に指定できません")
    models = (args.progress,) if args.progress else (args.models or (*BASELINES, *FULL))
    if set(models) - set((*BASELINES, *FULL)):
        parser.error("不明な条件が指定されました")
    seen = common_seen_terms()
    val = read_rows(MANIFESTS["val"])
    results = {model: score_model(model, seen, val) for model in models}
    if args.progress:
        append_progress(args.progress, results[args.progress])
    print(json.dumps({"common_seen_term_types": len(seen), "capacity": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
