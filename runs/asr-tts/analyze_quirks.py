"""Haasの出力の癖を数える（整形用LLMの学習データの加工の参考。commitせず、結果の横に置く）。

使い方: python analyze_quirks.py <名前> <manifest> <runのJSONL> [<名前> <manifest> <run> ...]
出力: 標準出力にMarkdownの表、同じ内容のJSONを第1引数の名前を付けて保存する。

数えるもの（正解は話した通りの`spoken_text`）：
- フィラー：評価（`voiceime.eval.report`）と同じ残存率（出力のフィラーのうち正解文に無いものの数÷話したフィラーの数）と、
  話したフィラーと出力のフィラーの語形ごとの総数。
- 句読点：文末に句点（。？！）が付く割合、句読点が1つも無い割合、読点「、」の数の正解に対する比。
- 用語：正解の`terms`の1回の出現ごとに、表記通り／大文字小文字だけ違う（主に小文字）／カタカナ読み／それ以外に分ける。
- 英字と日本語の間の半角空白：空白が入る発話の割合。
- 言い直し：`self_correction`の発話で、言い直しの言葉（いや、じゃなくて、間違えた、違う）が出力に残る割合。
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from voiceime.eval.metrics import count_fillers, count_residual_fillers, normalize_for_cer

CORRECTION_CUES = ("いや", "じゃなくて", "間違えた", "違う", "ではなく")
SPACE_PATTERN = re.compile(r"[A-Za-z0-9] [ぁ-んァ-ヶ一-龥]|[ぁ-んァ-ヶ一-龥] [A-Za-z0-9]")
KANA_IGNORED = str.maketrans("", "", "ー・ 　-")


def kana_norm(text):
    return normalize_for_cer(text).translate(KANA_IGNORED)


def analyze(manifest_path, run_path):
    man = {}
    for line in Path(manifest_path).read_text().splitlines():
        r = json.loads(line)
        man[r["id"]] = r
    rows = [json.loads(l) for l in Path(run_path).read_text().splitlines()]
    rows = [r for r in rows if r["id"] in man]
    fill_total = fill_left = 0
    form_map = defaultdict(Counter)
    end_punct = no_punct = 0
    comma_ref = comma_hyp = 0
    term_kind = Counter()
    upper_terms = Counter()
    space = 0
    sc_total = sc_kept = 0
    for row in rows:
        r, hyp = man[row["id"]], row["hyp"]
        ref = r["spoken_text"]
        fill_total += r.get("fillers") or 0
        fill_left += count_residual_fillers(r["target_text"], hyp)
        form_map["話した"].update({k: v for k, v in count_fillers(ref).items() if v})
        form_map["出力"].update({k: v for k, v in count_fillers(hyp).items() if v})
        end_punct += hyp.rstrip().endswith(("。", "？", "?", "！", "!"))
        no_punct += not re.search(r"[、。？?！!,，.]", hyp)
        comma_ref += ref.count("、")
        comma_hyp += hyp.count("、") + hyp.count(",")
        space += bool(SPACE_PATTERN.search(hyp))
        readings = {g["surface"]: (g.get("readings") or [g.get("reading")]) for g in r.get("glossary", [])}
        for term in r.get("terms", []):
            if term in hyp:
                kind = "表記通り"
            elif term.lower() in hyp.lower():
                kind = "大文字小文字だけ違う"
            elif any(rd and kana_norm(rd) in kana_norm(hyp) for rd in readings.get(term, [])):
                kind = "カタカナ読み"
            else:
                kind = "それ以外"
            term_kind[kind] += 1
            if any(c.isupper() for c in term):
                upper_terms[kind] += 1
        if "self_correction" in (r.get("tags") or []) and any(c in ref for c in CORRECTION_CUES):
            sc_total += 1
            sc_kept += any(c in hyp for c in CORRECTION_CUES)
    n = len(rows)
    nt = sum(term_kind.values())
    nu = sum(upper_terms.values())
    return {
        "n": n,
        "filler_residual": fill_left / fill_total if fill_total else None,
        "filler_total": fill_total,
        "end_punct_rate": end_punct / n,
        "no_punct_rate": no_punct / n,
        "comma_ratio": comma_hyp / comma_ref if comma_ref else None,
        "space_rate": space / n,
        "terms": {k: v / nt for k, v in term_kind.items()} if nt else {},
        "terms_n": nt,
        "upper_terms": {k: v / nu for k, v in upper_terms.items()} if nu else {},
        "upper_terms_n": nu,
        "self_correction_kept": sc_kept / sc_total if sc_total else None,
        "self_correction_n": sc_total,
        "filler_forms": {f: dict(c.most_common(8)) for f, c in form_map.items()},
    }


def main():
    args = sys.argv[1:]
    results = {}
    for i in range(0, len(args), 3):
        results[args[i]] = analyze(args[i + 1], args[i + 2])
    pct = lambda x: "-" if x is None else f"{x * 100:.0f}%"
    print("| 集合と系 | 件数 | フィラー残存 | 文末に句点 | 句読点なし | 読点の数（正解比） | 英字と日本語の間の空白 | 用語：表記通り | 大小だけ違う | カタカナ読み | それ以外 | 大文字を含む用語で大小だけ違う | 言い直しの言葉が残る |")
    print("|" + "---|" * 13)
    for name, x in results.items():
        t, u = x["terms"], x["upper_terms"]
        print(
            f"| {name} | {x['n']} | {pct(x['filler_residual'])} | {pct(x['end_punct_rate'])} | {pct(x['no_punct_rate'])} | "
            f"{pct(x['comma_ratio'])} | {pct(x['space_rate'])} | {pct(t.get('表記通り', 0))} | {pct(t.get('大文字小文字だけ違う', 0))} | "
            f"{pct(t.get('カタカナ読み', 0))} | {pct(t.get('それ以外', 0))} | {pct(u.get('大文字小文字だけ違う', 0))} | "
            f"{pct(x['self_correction_kept'])}（{x['self_correction_n']}件） |"
        )
    print()
    for name, x in results.items():
        print(name, "フィラーの語形の総数:", json.dumps(x["filler_forms"], ensure_ascii=False))
    Path(f"quirks-{'_'.join(results)}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
