"""課題1〜3の集計：モデル別の遅延と用語の件数、並行時の時間、用語の選択で正解が候補に入る件数を表にする。

用語の正表記の件数は`voiceime.eval.metrics.calculate_term_accuracy`（評価の担当の実装）で数える。
「大文字小文字・空白・記号を無視した一致」は課題で求められた参考の値で、この集計の中だけで数える（評価の正式な指標ではない）。

実行場所：手元のMac、リポジトリの直下で
    uv run python runs/multiasr-metal/scripts/analyze.py > runs/multiasr-metal/summary.md
"""

from __future__ import annotations

import json
import statistics
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf

from voiceime.eval.metrics import calculate_term_accuracy, count_inserted_terms, summarize_latency
from voiceime.formatter.glossary import GlossaryIndex, load_glossary, select_glossary

REPO = Path("/Users/marutyan/PrivateDev/voiceIME")
RUN = REPO / "runs/multiasr-metal"
MANIFEST = REPO / "data/dev-user/manifest.jsonl"
GLOSSARY = REPO / "data/text/glossary.jsonl"
HAAS = "haas-ja-v1.0-speechcpp-q8_0"
MULTI = [
    "qwen3-asr-0.6b-bf16", "qwen3-asr-0.6b-8bit", "qwen3-asr-0.6b-4bit",
    "qwen3-asr-1.7b-bf16", "qwen3-asr-1.7b-8bit", "qwen3-asr-1.7b-4bit",
    "whisper-large-v3-turbo", "whisper-large-v3-turbo-q8", "whisper-large-v3-turbo-q4",
]
# 2つのASRの文をつなぐ区切り（`parallel_pipeline.py`と同じ）。
JOIN = "\n"


def read_jsonl(path: Path) -> list[dict]:
    """1行1件のJSONLを読む。"""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def loose_key(text: str) -> str:
    """大文字小文字を揃え、空白・記号（Unicodeの区切り、句読点、記号の分類）を除いた比較用の文字列。"""
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(c for c in text if unicodedata.category(c)[0] not in "PSZ")


def loose_term_count(terms: list[str], hyp: str) -> int:
    """正解の各用語の出現回数を上限に、比較用の文字列どうしで一致した回数を数える。"""
    key = loose_key(hyp)
    return sum(min(n, key.count(loose_key(t))) for t, n in Counter(terms).items())


def fmt(x: float | None) -> str:
    """秒を小数2桁で表す。"""
    return "-" if x is None else f"{x:.2f}"


def lat(values: list[float]) -> str:
    """中央値（p90）の表記。"""
    s = summarize_latency(values)
    return f"{fmt(s['median_s'])}（{fmt(s['p90_s'])}）"


def main() -> None:
    """表をMarkdownで標準出力へ書き、数値をsummary.jsonへ残す。"""
    manifest = {r["id"]: r for r in read_jsonl(MANIFEST)[:50]}
    duration = {i: sf.info(REPO / "data/dev-user" / r["audio_path"]).duration for i, r in manifest.items()}
    mid = {i for i, d in duration.items() if 5 < d <= 15}
    n_terms = sum(len(r["terms"]) for r in manifest.values())
    # 挿入の数え方に使う用語集第1版の行（surfaceとreadings）。
    glossary_records = read_jsonl(GLOSSARY)
    summary: dict = {"n_utterances": len(manifest), "n_5_15s": len(mid), "n_terms": n_terms}

    # 課題1：単独で動かした1回目の遅延と用語の件数
    print(f"## 課題1：ヒント無しの1回目（本人の読み上げ{len(manifest)}件、5〜15秒は{len(mid)}件、用語{n_terms}回）\n")
    print("| モデル | 遅延 5〜15秒 中央値（p90） | 遅延 全50件 中央値（p90） | 用語 正表記 | 用語 大小・空白・記号を無視 | 用語 読みも許す |")
    print("| --- | --- | --- | --- | --- | --- |")
    single: dict[str, dict[str, dict]] = {}
    for model in [HAAS, *MULTI]:
        path = RUN / "single" / f"{model}.jsonl"
        if not path.exists():
            continue
        rows = {r["id"]: r for r in read_jsonl(path)}
        assert set(rows) == set(manifest), model
        single[model] = rows
        exact = loose = reading = 0
        for i, r in manifest.items():
            acc = calculate_term_accuracy(r["terms"], r["glossary"], rows[i]["hyp"])
            exact += acc["correct"]
            reading += acc["loose_correct"]
            loose += loose_term_count(r["terms"], rows[i]["hyp"])
        mid_lat = [rows[i]["latency_s"] for i in mid]
        all_lat = [rows[i]["latency_s"] for i in manifest]
        summary.setdefault("single", {})[model] = {
            "latency_5_15": summarize_latency(mid_lat), "latency_all": summarize_latency(all_lat),
            "terms_exact": exact, "terms_loose": loose, "terms_reading": reading}
        print(f"| {model} | {lat(mid_lat)} | {lat(all_lat)} | {exact}/{n_terms} | {loose}/{n_terms} | {reading}/{n_terms} |")

    # 課題2：並行実行の時間
    par_dir = RUN / "parallel"
    par_models = [m for m in MULTI if (par_dir / f"{m}.jsonl").exists()]
    haas_final_text: dict[str, str] = {}
    if par_models:
        print("\n## 課題2：Haasのtwo-passと多言語ASRの同時実行（5〜15秒の発話、中央値（p90）、秒）\n")
        print("| 多言語ASR | Haas two-pass 単独 | 多言語 単独 | 順に（合計） | 同時A：全体 | 同時A：Haas | 同時A：多言語 | 同時B：全体 | 整形 base | 整形 union | 既定の構成（Haas two-pass＋整形） | 同時A＋整形union | 同時B＋整形union |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for model in par_models:
            rows = {r["id"]: r for r in read_jsonl(par_dir / f"{model}.jsonl")}
            ids = [i for i in manifest if i in mid]
            g = lambda f: [f(rows[i]) for i in ids]  # noqa: E731
            cols = {
                "haas_alone": g(lambda r: r["seq"]["haas_s"]),
                "multi_alone": g(lambda r: r["seq"]["multi_s"]),
                "seq_total": g(lambda r: r["seq"]["wall_s"]),
                "parA_wall": g(lambda r: r["parA"]["wall_s"]),
                "parA_haas": g(lambda r: r["parA"]["haas_s"]),
                "parA_multi": g(lambda r: r["parA"]["multi_s"]),
                "parB_wall": g(lambda r: r["parB"]["wall_s"]),
                "fmt_base": g(lambda r: r["format"]["base"]["s"]),
                "fmt_union": g(lambda r: r["format"]["union"]["s"]),
                # 既定の構成の見込み：単独のHaas two-passの時間に、baseの整形の時間を足す（同じ発話の値どうし）。
                "default_e2e": g(lambda r: r["seq"]["haas_s"] + r["format"]["base"]["s"]),
                "parA_e2e": g(lambda r: r["parA"]["wall_s"] + r["format"]["union"]["s"]),
                "parB_e2e": g(lambda r: r["parB"]["wall_s"] + r["format"]["union"]["s"]),
            }
            summary.setdefault("parallel", {})[model] = {k: summarize_latency(v) for k, v in cols.items()}
            # 同時に動かしたことによる遅れ（発話ごとの差の中央値）
            summary["parallel"][model]["slowdown_haas_median_s"] = statistics.median(
                rows[i]["parA"]["haas_s"] - rows[i]["seq"]["haas_s"] for i in ids)
            summary["parallel"][model]["slowdown_multi_median_s"] = statistics.median(
                rows[i]["parA"]["multi_s"] - rows[i]["seq"]["multi_s"] for i in ids)
            summary["parallel"][model]["gpu_util_pct_median"] = statistics.median(
                rows[i]["load"]["gpu_util_pct"] for i in manifest if rows[i]["load"]["gpu_util_pct"] is not None)
            summary["parallel"][model]["load1_median"] = statistics.median(rows[i]["load"]["load1"] for i in manifest)
            print("| " + model + " | " + " | ".join(lat(v) for v in cols.values()) + " |")
            haas_final_text = {i: r["seq"]["haas_final"] for i, r in rows.items()}

    # 参考：ASRと整形の後の文に正解の用語が正表記で出た回数（課題の範囲外。整形の入力文はどちらもHaasのtwo-pass）
    if par_models:
        print(f"\n## 参考：正表記の用語の回数（{n_terms}回中）と、話していない用語の挿入\n")
        print("| 多言語ASR | Haas two-pass（今の選択） | Haas two-pass（2つの文から選択、同時B） | 整形 base | 整形 union | 挿入 base／union |")
        print("| --- | --- | --- | --- | --- | --- |")
        for model in par_models:
            rows = {r["id"]: r for r in read_jsonl(par_dir / f"{model}.jsonl")}

            def count(f) -> int:
                """全50件で正表記の用語の回数を足す。"""
                return sum(calculate_term_accuracy(r["terms"], r["glossary"], f(rows[i]))["correct"]
                           for i, r in manifest.items())

            def inserted(f) -> int:
                """全50件で、正解の回数を超えて出た用語集第1版の語の回数を足す。"""
                return sum(count_inserted_terms(r["terms"], glossary_records, f(rows[i])) for i, r in manifest.items())

            vals = {
                "haas2p": count(lambda r: r["seq"]["haas_final"]),
                "haas2p_union": count(lambda r: r["parB"]["haas_final"]),
                "format_base": count(lambda r: r["format"]["base"]["text"]),
                "format_union": count(lambda r: r["format"]["union"]["text"]),
                "inserted_base": inserted(lambda r: r["format"]["base"]["text"]),
                "inserted_union": inserted(lambda r: r["format"]["union"]["text"]),
            }
            summary["parallel"][model]["terms_after"] = vals
            print(f"| {model} | {vals['haas2p']}/{n_terms} | {vals['haas2p_union']}/{n_terms} | "
                  f"{vals['format_base']}/{n_terms} | {vals['format_union']}/{n_terms} | "
                  f"{vals['inserted_base']}／{vals['inserted_union']} |")

    # 課題3：用語の選択で正解が候補に入る件数
    glossary = load_glossary(GLOSSARY)
    index = GlossaryIndex(glossary)
    known = {e.surface for e in glossary}
    in_glossary = sum(1 for r in manifest.values() for t in r["terms"] if t in known)
    summary["terms_in_glossary_v1"] = in_glossary

    def recall(texts: dict[str, str], max_entries: int) -> tuple[int, float]:
        """各発話の文から選んだ語に、正解の用語が入った回数と、選んだ語の数の平均。"""
        hit, counts = 0, []
        for i, r in manifest.items():
            chosen = {e.surface for e in select_glossary(texts[i], glossary, max_entries, selection_index=index)}
            counts.append(len(chosen))
            hit += sum(1 for t in r["terms"] if t in chosen)
        return hit, float(np.mean(counts))

    print(f"\n## 課題3：用語集第1版から選んだ語に正解が入った回数（{n_terms}回中、うち第1版にある語は{in_glossary}回）\n")
    print("| 選択に使う文 | 上限16語 | 上限20語 | 選んだ語の数の平均（16／20） |")
    print("| --- | --- | --- | --- |")
    sources: dict[str, dict[str, str]] = {}
    if HAAS in single:
        haas1 = {i: single[HAAS][i]["hyp"] for i in manifest}
        sources["Haasの1回目"] = haas1
        for model in MULTI:
            if model in single:
                sources[f"Haasの1回目＋{model}"] = {i: haas1[i] + JOIN + single[model][i]["hyp"] for i in manifest}
    if haas_final_text:
        sources["Haasのtwo-pass（整形の今の選択）"] = haas_final_text
        for model in MULTI:
            if model in single:
                sources[f"Haasのtwo-pass＋{model}"] = {
                    i: haas_final_text[i] + JOIN + single[model][i]["hyp"] for i in manifest}
    for name, texts in sources.items():
        (h16, c16), (h20, c20) = recall(texts, 16), recall(texts, 20)
        summary.setdefault("selection", {})[name] = {"hit16": h16, "hit20": h20, "mean16": c16, "mean20": c20}
        print(f"| {name} | {h16}/{n_terms} | {h20}/{n_terms} | {c16:.1f}／{c20:.1f} |")

    (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
