"""学習データの`omitted_terms`のうち、入力に表記の手掛かりがあるのに正解文が読みのままの例を直す。

PMの規則（docs/experiments/2026-11-23-omitted-terms-fix.md）を、元の学習行と用語差し替えの拡張行の両方へ適用する。
読みのまま残す語は各行の`katakana_terms`へ書き、学習コードはその表記を一覧から除く（無作為に混ぜる語への対策）。
学習時に一覧を作る行は`cue_rewrite`に書き換え後の正解文を持たせ、学習コードが取り出しのたびに規則2を当てる。
"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    """JSONLを順序どおりに読む。"""
    with open(path, encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def write_jsonl(path, rows):
    """行の順序を保ってJSONLへ書く。"""
    with open(path, "w", encoding="utf-8") as sink:
        for row in rows:
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")


def by_id(path, field):
    """IDごとに1つの欄を引ける辞書を作る。"""
    return {row["id"]: row[field] for row in read_jsonl(path)}


def surface_key(text):
    """幅・大小・空白の違いを無視して表記を比べるための鍵。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


def surface_pattern(surface):
    """文中の表記を、幅・大小・空白の違いと英数字の語境界を考慮して探す正規表現。"""
    key = unicodedata.normalize("NFKC", surface).casefold()
    parts = [re.escape(char) for char in re.sub(r"\s+", "", key)]
    body = r"\s*".join(parts)
    # 英数字で始まる・終わる表記は、前後に英数字が続く場合（例：Goに対するGoogle）を一致にしない。
    head = r"(?<![a-z0-9])" if key[:1].isascii() and key[:1].isalnum() else ""
    tail = r"(?![a-z0-9])" if key[-1:].isascii() and key[-1:].isalnum() else ""
    return re.compile(head + body + tail)


def has_surface(text, surface):
    """文に表記が（幅・大小・空白の違いを除いて）現れるか。"""
    if not text:
        return False
    return surface_pattern(surface).search(unicodedata.normalize("NFKC", text).casefold()) is not None


def in_list(entries, surface):
    """用語一覧に同じ表記（幅・大小・空白の違いを除く）があるか。"""
    key = surface_key(surface)
    return any(surface_key(entry["surface"]) == key for entry in entries)


def reading_spans(text, readings):
    """正解文中の読みの出現位置を、別の読みに含まれる短い一致を除いて返す。"""
    spans = set()
    for reading in readings:
        start = text.find(reading)
        while start != -1:
            spans.add((start, start + len(reading)))
            start = text.find(reading, start + 1)
    return sorted(s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans))


def decide(term, target, entries, first, combined, qwen, protected):
    """1つのomitted語について、規則1〜3のどれに当たり、どう扱うかを返す。

    entriesがNoneの行は、学習時にselectorが一覧を作る行（規則4）。
    """
    surface = term["surface"]
    if protected:
        leaked = (entries is not None and in_list(entries, surface)) or any(
            has_surface(text, surface) for text in (first, combined, qwen))
        return ("drop", "rule1-leak") if leaked else ("katakana", "rule1-protected")
    if entries is None:
        # 一覧は学習時に決まるため、規則2の書き換え先だけを用意し、使うかどうかは取り出しのたびに決める。
        spans = reading_spans(target, term["readings"])
        if len(spans) != 1:
            return "drop", f"rule4-reading-count-{min(len(spans), 2)}"
        return "rewrite-if-cue", "rule4-rewrite-if-cue"
    listed = in_list(entries, surface)
    merged = has_surface(combined, surface)
    if not (listed or merged):
        return "katakana", "rule3-no-cue"
    cue = "list+merge" if listed and merged else "list" if listed else "merge"
    spans = reading_spans(target, term["readings"])
    if len(spans) != 1:
        return "drop", f"rule2-reading-count-{min(len(spans), 2)}"
    return "rewrite", f"rule2-{cue}"


def rewrite_target(target, term):
    """正解文にちょうど1回ある読みを表記へ置き換える。"""
    (start, end), = reading_spans(target, term["readings"])
    return target[:start] + term["surface"] + target[end:]


def fix_row(row, term, entries, first, combined, qwen, protected, gold_field):
    """1行に規則を当て、直した行（外す場合はNone）と判定を返す。"""
    action, reason = decide(term, row["target_text"], entries, first, combined, qwen, protected)
    if action == "drop":
        return None, reason
    fixed = dict(row)
    if action == "rewrite":
        fixed["target_text"] = rewrite_target(row["target_text"], term)
        fixed["terms"] = [*row["terms"], term["surface"]]
        fixed[gold_field] = [*row.get(gold_field, []), {"surface": term["surface"], "readings": term["readings"]}]
        fixed["katakana_terms"] = []
    elif action == "rewrite-if-cue":
        # 学習コード（train_support.target_for_inputs）が、一覧かsegment-merge後の文に表記があるときだけ使う。
        fixed["cue_rewrite"] = {"surface": term["surface"], "target_text": rewrite_target(row["target_text"], term)}
        fixed["katakana_terms"] = []
    else:
        fixed["katakana_terms"] = [term["surface"]]
    fixed["omitted_fix"] = reason
    return fixed, reason


def leftover_rows(rows, lists):
    """一覧に表記があるのに、正解文に表記が無く、その語の読みがある行を数える。

    lists[i]は行iの事前の一覧（無い行はNone）。学習時に作る一覧は別の確認（verify_dynamic.py）で調べる。
    """
    counts = Counter()
    examples = []
    for row, entries in zip(rows, lists, strict=True):
        if entries is None:
            continue
        omitted = {t["surface"] for t in row.get("omitted_terms", [])}
        hits = [e for e in entries
                if not has_surface(row["target_text"], e["surface"])
                and reading_spans(row["target_text"], e["readings"])]
        if not hits:
            continue
        counts["rows"] += 1
        if any(e["surface"] in omitted for e in hits):
            counts["rows_omitted_term"] += 1
            if len(examples) < 5:
                examples.append({"id": row["id"], "target_text": row["target_text"],
                                 "hits": [e["surface"] for e in hits]})
        if any(e["surface"] not in omitted and max(map(len, e["readings"])) >= 6 for e in hits):
            counts["rows_other_term_reading6"] += 1
        if any(e["surface"] in row.get("katakana_terms", []) for e in hits):
            counts["rows_katakana_term"] += 1
    return dict(counts), examples


def main():
    """元の学習行と拡張行を直し、件数と0件確認を記録する。"""
    p = argparse.ArgumentParser()
    p.add_argument("--train", required=True)
    p.add_argument("--augmentation", required=True)
    p.add_argument("--train-runs", required=True, help="条件Dの学習用runの置き場所")
    p.add_argument("--heldout", required=True)
    p.add_argument("--novel", required=True)
    p.add_argument("--val", nargs=2, action="append", default=[], metavar=("MANIFEST", "RUNS"),
                   help="件数だけを数えるvalのmanifestとrunの置き場所")
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()

    runs = Path(args.train_runs)
    lists = by_id(runs / "formatter-glossary.jsonl", "glossary")
    firsts = by_id(runs / "first-pass.jsonl", "hyp")
    merges = by_id(runs / "segment-merge.jsonl", "hyp")
    qwens = by_id(runs / "qwen06-hypothesis.jsonl", "hyp")
    protected = {line.strip() for line in open(args.heldout, encoding="utf-8") if line.strip()}
    protected |= {t for row in read_jsonl(args.novel) for t in row["terms"]}
    protected_keys = {surface_key(t) for t in protected}

    train = read_jsonl(args.train)
    source_by_id = {row["id"]: row for row in train}
    reasons = Counter()
    fixed_train, examples = [], []
    for row in train:
        if not row.get("omitted_terms"):
            fixed_train.append(row)
            continue
        term, = row["omitted_terms"]
        fixed, reason = fix_row(row, term, lists.get(row["id"]), firsts.get(row["id"]),
                                merges.get(row["id"]), qwens.get(row["id"]),
                                surface_key(term["surface"]) in protected_keys, "glossary")
        reasons[reason] += 1
        if fixed is not None:
            fixed_train.append(fixed)
            if reason.startswith("rule2-") and fixed["target_text"] != row["target_text"] and len(examples) < 20:
                examples.append({"id": row["id"], "before": row["target_text"], "after": fixed["target_text"]})

    aug_reasons = Counter()
    fixed_aug = []
    for row in read_jsonl(args.augmentation):
        source = source_by_id[row["source_id"]]
        if not source.get("omitted_terms"):
            fixed_aug.append(row)
            continue
        term, = source["omitted_terms"]
        fixed, reason = fix_row(row, term, row["glossary"], row["first_pass"], row["combined_text"],
                                row["qwen_hypothesis"], surface_key(term["surface"]) in protected_keys,
                                "gold_glossary")
        if fixed is not None:
            # 元行のomitted語を、拡張行の0件確認でも参照できるようにする。
            fixed["omitted_terms"] = source["omitted_terms"]
        aug_reasons[reason] += 1
        if fixed is not None:
            fixed_aug.append(fixed)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "train-fixed.jsonl", fixed_train)
    write_jsonl(out / "augmentation-fixed.jsonl", fixed_aug)

    train_lists = [lists.get(row["id"]) for row in fixed_train]
    before_lists = [lists.get(row["id"]) for row in train]
    original_aug = read_jsonl(args.augmentation)
    for row in original_aug:
        row["omitted_terms"] = source_by_id[row["source_id"]].get("omitted_terms", [])
    audit = {
        "train_rows_before": len(train),
        "train_rows_after": len(fixed_train),
        "train_omitted_rows": sum(reasons.values()),
        "train_omitted_rows_prebuilt_list": sum(1 for r in train if r.get("omitted_terms") and r["id"] in lists),
        "train_decisions": dict(sorted(reasons.items())),
        "augmentation_rows_before": len(original_aug),
        "augmentation_rows_after": len(fixed_aug),
        "augmentation_omitted_source_rows": sum(aug_reasons.values()),
        "augmentation_decisions": dict(sorted(aug_reasons.items())),
        "leftover_before": {
            "train_prebuilt": leftover_rows(train, before_lists)[0],
            "augmentation": leftover_rows(original_aug, [r["glossary"] for r in original_aug])[0],
        },
        "leftover_after": {
            "train_prebuilt": leftover_rows(fixed_train, train_lists),
            "augmentation": leftover_rows(fixed_aug, [r["glossary"] for r in fixed_aug]),
        },
        "val": {},
        "rewrite_examples": examples,
    }
    for manifest, val_runs in args.val:
        val_rows = read_jsonl(manifest)
        val_lists = by_id(Path(val_runs) / "formatter-glossary.jsonl", "glossary")
        audit["val"][manifest] = {
            "rows": len(val_rows),
            "rows_with_omitted_terms": sum(1 for r in val_rows if r.get("omitted_terms")),
            "leftover": leftover_rows(val_rows, [val_lists.get(r["id"]) for r in val_rows]),
        }
    (out / "fix-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in audit.items() if k != "rewrite_examples"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
