"""保存済みの合成評価から、誤りの内訳とモデル間の一致を再集計する。"""

import argparse
import csv
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


# 誤り1件を、PM指定の各観点から数える。出力上の誤り分類は目視で付けたラベルを使う。
AXES = {
    "listed": ("一覧に正解語", {"yes": "あり", "no": "なし"}),
    "qwen_surface": ("Qwenに正しい表記", {"yes": "あり", "no": "なし"}),
    "haas_first_reading": ("Haas 1回目に登録読み", {"yes": "あり", "no": "なし"}),
    "haas_merged_reading": ("segment-mergeに登録読み", {"yes": "あり", "no": "なし"}),
    "error_class": ("出力の誤り方", {
        "a": "(a) 音写・崩れた表記", "b": "(b) 一覧の別語",
        "c": "(c) 大小・記号・空白のみ", "d": "(d) 脱落", "e": "(e) その他",
    }),
    "term_kind": ("正解語の種類", {
        "acronym": "英字の略語（全部大文字）", "word": "英単語1語",
        "compound": "複合語", "number_or_symbol": "数字・記号を含む語",
    }),
}


def normalized(text: str) -> str:
    """幅と大小を揃え、空白・記号を取り除く。英字、かな、漢字、数字は残す。"""
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold()
                   if char.isalnum())


def has_surface(term: str, text: str) -> bool:
    """表記の差を許し、別の英数字列の途中にある略語を除いて照合する。"""
    letters = normalized(term)
    if not letters:
        return False
    separator = r"[\W_]*"
    pattern = separator.join(map(re.escape, letters))
    if letters[0].isascii():
        pattern = r"(?<![a-z0-9])" + pattern
    if letters[-1].isascii():
        pattern += r"(?![a-z0-9])"
    return bool(re.search(pattern, unicodedata.normalize("NFKC", text).casefold()))


def kana(text: str) -> str:
    """ひらがなをカタカナへ寄せ、登録読みの文字列照合に使う。"""
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch
                   for ch in normalized(text))


def term_kind(term: str) -> str:
    """数字・記号を優先し、残りを複合語、全大文字、英単語に振り分ける。"""
    if re.search(r"[^A-Za-z\s-]", term):
        return "number_or_symbol"
    if re.search(r"[\s-]", term):
        return "compound"
    return "acronym" if term.isupper() else "word"


def classify(row: dict, term: str, label: dict) -> dict:
    """欠けた正解語について、入力と一覧から照合可能な根拠を記録する。"""
    readings = [reading for entry in row["gold_glossary"] if entry["surface"] == term
                for reading in entry["readings"] if kana(reading)]
    if not readings:
        raise ValueError(f"{row['id']}/{term}: 比較可能な登録読みがありません")
    if label["error_class"] == "b" and (
        label["listed_replacement"] not in row["glossary"] or
        label["listed_replacement"] not in label["aligned_output"]
    ):
        raise ValueError(f"{row['id']}/{term}: 分類(b)の別語が照合できません")
    if label["error_class"] == "c" and normalized(term) != normalized(label["aligned_output"]):
        raise ValueError(f"{row['id']}/{term}: 分類(c)の正規化表記が一致しません")

    def has_reading(text: str) -> bool:
        """登録された読みのいずれかが、仮説のかなを揃えた文に含まれるか判定する。"""
        converted = kana(text)
        return any(kana(reading) in converted for reading in readings)

    source = row["input"]
    return {
        **label, "row": row, "readings": readings,
        "listed": "yes" if term in row["glossary"] else "no",
        "qwen_surface": "yes" if has_surface(term, source["qwen_hypothesis"] or "") else "no",
        "haas_first_reading": "yes" if has_reading(source["first_pass"]) else "no",
        "haas_merged_reading": "yes" if has_reading(source["combined_text"]) else "no",
        "term_kind": term_kind(term),
    }


def analyze_split(rows: list[dict], labels: dict) -> tuple[dict, list[dict]]:
    """用語の出現単位で一致を数え、0.8Bの全誤りにラベルがあることを確認する。"""
    agreements = {
        (True, True): "both_correct", (True, False): "only_drop0",
        (False, True): "only_2b", (False, False): "both_wrong",
    }
    counts = {group: Counter(dict.fromkeys(agreements.values(), 0))
              for group in ("all", "listed", "unlisted")}
    errors = []
    for row in rows:
        for term, expected in Counter(row["terms"]).items():
            # この評価集合では1行内に同一termsの重複がないため、目視ラベルをIDと語で特定できる。
            if expected != 1:
                raise ValueError(f"{row['id']}/{term}: 同じ語の複数出現に対応するラベルが必要です")
            a, b = term in row["drop0"], term in row["2b"]
            agreement = agreements[a, b]
            counts["all"][agreement] += 1
            counts["listed" if term in row["glossary"] else "unlisted"][agreement] += 1
            if not a:
                errors.append(classify(row, term, labels.pop((row["id"], term))))
    if labels:
        raise ValueError("正解語の誤りに対応しないラベルがあります")
    by_axis = {
        axis: {key: sum(error[axis] == key for error in errors) for key in names}
        for axis, (_, names) in AXES.items()
    }
    return {
        "samples": len(rows), "term_agreement": counts, "drop0_errors": len(errors),
        "counts_by_axis": by_axis,
        "errors_by_list_and_class": {
            listed: dict(Counter(error["error_class"] for error in errors if error["listed"] == listed))
            for listed in ("yes", "no")
        },
        "errors_by_list_and_qwen_surface": {
            listed: dict(Counter(error["qwen_surface"] for error in errors if error["listed"] == listed))
            for listed in ("yes", "no")
        },
        "haas_correct_surface_without_reading": {
            key: sum(error[axis] == "no" and has_surface(error["gold_term"], error["row"]["input"][key])
                     for error in errors)
            for key, axis in (("first_pass", "haas_first_reading"), ("combined_text", "haas_merged_reading"))
        },
    }, errors


def examples(split: str, errors: list[dict]) -> str:
    """観点と分類ごとに先頭5件を参照し、同じ例の本文は一度だけ載せる。"""
    lines = [f"## {split}", "",
             "| 観点 | 分類 | 件数 | 例 |", "| --- | --- | ---: | --- |"]
    selected = set()
    for axis, (heading, names) in AXES.items():
        for key, name in names.items():
            indices = [index for index, error in enumerate(errors, 1) if error[axis] == key]
            chosen = indices[:5]
            selected.update(chosen)
            links = "、".join(f"[{index:03d}](#{split}-{index:03d})" for index in chosen)
            lines.append(f"| {heading} | {name} | {len(indices)} | {links or '—'} |")
    lines.append("")
    for index in sorted(selected):
        item = errors[index - 1]
        row = item["row"]
        source = row["input"]
        entries = row["glossary_entries"]
        relevant = [entry for entry in entries
                    if entry["surface"] in {item["gold_term"], item["listed_replacement"]}]
        shown = relevant or entries[:3]
        glossary = " ／ ".join(
            f"{'、'.join(entry['readings'])} → {entry['surface']}"
            if entry["readings"] else entry["surface"] for entry in shown
        )
        if not shown:
            glossary = "一覧は空。"
        elif not relevant:
            glossary = "該当語なし。先頭3語 " + glossary
        badges = "、".join(f"{heading} {names[item[axis]]}" for axis, (heading, names) in AXES.items())
        lines.extend([f"### {split} {index:03d}", "",
                      f"{row['id']}。正解語 `{item['gold_term']}`。{badges}。"
                      f"登録読み {'、'.join(item['readings'])}。", ""])
        for heading, value in (
            ("Haas 1回目", source["first_pass"]), ("segment-merge", source["combined_text"]),
            ("Qwen 0.6B", source["qwen_hypothesis"] or "（空）"), ("一覧の抜粋", glossary),
            ("整形出力", row["drop0"] or "（空）"), ("正解文", row["target_text"]),
        ):
            lines.append(f"- **{heading}**　{html.escape(value.replace(chr(10), ' ⏎ '), quote=False)}")
        if item["listed_replacement"]:
            lines.append(f"- **置換された一覧語**　{item['listed_replacement']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """元runから抽出したデータと目視ラベルを使い、集計と例を生成する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baselines", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    base = json.loads(args.baselines.read_text())
    with Path(__file__).with_name("error-labels.tsv").open(newline="", encoding="utf-8") as source:
        annotations = list(csv.DictReader(source, delimiter="\t"))
    result = {}
    pages = ["# D-0.8B-drop0の誤り例", "",
             "分類ごとに評価順の先頭5件を掲げる。5件に満たない分類は全件を掲げる。"
             "同じ用語例を複数の分類から参照できる。改行は ⏎ で表示する。", ""]
    for split, data in base.items():
        labels = {(label["id"], label["gold_term"]): label for label in annotations if label["split"] == split}
        stats, errors = analyze_split(data["rows"], labels)
        result[split] = {"source_counts": data["source_counts"], "sha256": data["sha256"], **stats}
        pages.append(examples(split, errors))
    if sum(data["drop0_errors"] for data in result.values()) != len(annotations):
        raise ValueError("目視ラベル数が誤りの総数と一致しません")
    (args.output_dir / "baseline-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (args.output_dir / "error-examples.md").write_text("\n".join(pages))


if __name__ == "__main__":
    main()
