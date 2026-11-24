"""fix1のomitted行の正解文を表記にそろえ、入力と一覧を保った学習データを作る。"""

import hashlib
import json
from collections import Counter
from pathlib import Path

from fix_omitted_terms import rewrite_target, surface_key

WORK = Path.home() / "voiceime-work-wops"
DATA = WORK / "fix2/data"
HELDOUT = (Path.home() / "voiceime-work-asr/r3-twopass-20261122/terms"
           / "exclude-v2-plus-heldout.txt")


def convert(source, output, protected):
    """fix1で残った行を同じ順序で書き出し、分岐ごとの変更数とハッシュを返す。"""
    counts = Counter()
    reasons = Counter()
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    with source.open("rb") as rows, output.open("xb") as sink:
        for line in rows:
            source_hash.update(line)
            row = json.loads(line)
            counts["rows"] += 1
            if row.get("omitted_terms"):
                term, = row["omitted_terms"]
                surface = term["surface"]
                if surface_key(surface) in protected:
                    raise ValueError(f"{row['id']}: 除外語を含みます")
                reason = row["omitted_fix"]
                target = row["target_text"]
                if reason == "rule4-rewrite-if-cue":
                    rewrite = row.pop("cue_rewrite")
                    if rewrite["surface"] != surface or rewrite["target_text"] != rewrite_target(target, term):
                        raise ValueError(f"{row['id']}: fix1の書き換え先が一致しません")
                    target = rewrite["target_text"]
                elif reason == "rule3-no-cue":
                    target = rewrite_target(target, term)
                elif reason not in {"rule2-list", "rule2-list+merge", "rule2-merge"}:
                    raise ValueError(f"{row['id']}: 不明なfix1の処理 {reason}")
                if surface not in target:
                    raise ValueError(f"{row['id']}: 正解文に表記がありません")
                counts["target_changed"] += target != row["target_text"]
                counts["omitted_rows"] += 1
                reasons[reason] += 1
                row["target_text"] = target
                if surface not in row["terms"]:
                    row["terms"].append(surface)
                # 元行のglossaryはASR合成と一覧生成にも使うため、正解語を一覧側へ追加しない。
                row.pop("katakana_terms")
                line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
            sink.write(line)
            output_hash.update(line)
    return {**counts, "fix1_decisions": dict(reasons),
            "fix1_sha256": source_hash.hexdigest(), "fix2_sha256": output_hash.hexdigest()}


def main():
    """元データと拡張データを新しい出力先へ書き、両方が揃った時点で監査を保存する。"""
    protected = {surface_key(term) for term in HELDOUT.read_text().splitlines() if term.strip()}
    DATA.mkdir()
    result = {}
    for dataset in ("train", "augmentation"):
        name = f"{dataset}-fixed.jsonl"
        result[dataset] = convert(WORK / "fix1/data" / name, DATA / name, protected)
    (DATA / "fix-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
