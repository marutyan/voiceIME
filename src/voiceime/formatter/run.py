"""整形の系をmanifestまたはASRの推論結果に対して実行し、`runs/<実験名>/<系>.jsonl`へ書くCLI。

例（手元のMacで実行する）:
    uv run python -m voiceime.formatter.run --manifest data/text/pilot.jsonl --input-field spoken_text \\
        --model mlx-community/Qwen3.5-0.8B-MLX-4bit --out runs/formatter-zeroshot/qwen3.5-0.8b.jsonl
    uv run python -m voiceime.formatter.run --manifest data/dev/manifest.jsonl --asr-run runs/asr/whisper.jsonl \\
        --model rules --out runs/e2e/whisper+rules.jsonl

`--asr-run`を渡した場合、入力はASRの`hyp`、`latency_s`はASRの`latency_s`と整形の時間の和とする
（`docs/PLAN.md`の遅延の定義で、音声を読み込み終えた時点から整形済みの文が出るまで）。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from voiceime.formatter.glossary import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_MIN_SCORE,
    GlossaryIndex,
    GlossaryEntry,
    entry_from_record,
    exclude_glossary,
    glossary_from_rows,
    load_glossary,
    load_term_list,
    select_glossary,
)
from voiceime.formatter.prompt import FormatterInput, formatter_input_text
from voiceime.formatter.rules import format_with_rules

# `--model`にこの値を渡すと、LLMを使わない規則ベースの系で整形する。
RULES_MODEL = "rules"


def read_jsonl(path: str | Path) -> list[dict]:
    """1行1件のJSONLを読み込む。"""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_inputs(args: argparse.Namespace) -> list[dict]:
    """各行の入力文と、利用したASR結果の遅延をidで対応づける。"""
    rows = read_jsonl(args.manifest)
    if not any((args.asr_run, args.asr_run_first, args.asr_run_combined)):
        return [{"id": r["id"], "text": r[args.input_field], "row": r, "asr_latency_s": 0.0} for r in rows]

    runs = {
        "first": {r["id"]: r for r in read_jsonl(args.asr_run_first)} if args.asr_run_first else None,
        "second": {r["id"]: r for r in read_jsonl(args.asr_run)} if args.asr_run else None,
        "combined": {r["id"]: r for r in read_jsonl(args.asr_run_combined)} if args.asr_run_combined else None,
    }
    if args.asr_run and args.asr_run_combined:
        raise ValueError("--asr-runと--asr-run-combinedは同時に指定できません")

    def available(sample_id: str) -> bool:
        return all(run is None or sample_id in run for run in runs.values())

    missing = [r["id"] for r in rows if not available(r["id"])]
    if missing:
        print(f"警告: ASRの結果が無い{len(missing)}件を飛ばします（例: {missing[:3]}）", file=sys.stderr)
    inputs = []
    for row in rows:
        sample_id = row["id"]
        if not available(sample_id):
            continue
        first_run, second_run, combined_run = (runs[key] for key in ("first", "second", "combined"))
        if first_run is not None and second_run is not None:
            text: str | FormatterInput = FormatterInput(
                first_pass=first_run[sample_id]["hyp"], second_pass=second_run[sample_id]["hyp"]
            )
            latency_row = second_run[sample_id]
        elif first_run is not None and combined_run is not None:
            text = FormatterInput(
                first_pass=first_run[sample_id]["hyp"], combined_text=combined_run[sample_id]["hyp"]
            )
            latency_row = combined_run[sample_id]
        elif first_run is not None:
            text = FormatterInput(first_pass=first_run[sample_id]["hyp"])
            latency_row = first_run[sample_id]
        elif combined_run is not None:
            text = FormatterInput(combined_text=combined_run[sample_id]["hyp"])
            latency_row = combined_run[sample_id]
        else:
            text = second_run[sample_id]["hyp"]
            latency_row = second_run[sample_id]
        inputs.append(
            {
                "id": sample_id,
                "text": text,
                "row": row,
                "asr_latency_s": latency_row.get("latency_s", 0.0),
            }
        )
    return inputs


def choose_glossary(
    args: argparse.Namespace,
    text: str | FormatterInput,
    row: dict,
    full: list[GlossaryEntry],
    exclude_terms: Iterable[str] | None = None,
    selection_index: GlossaryIndex | None = None,
) -> list[GlossaryEntry]:
    """`--glossary-mode`に従い、プロンプトへ渡す用語を決める。`exclude_terms`の語はどの方式でも除く。"""
    if args.glossary_mode == "none":
        return []
    if args.glossary_mode == "row":
        # 各行の正解の用語だけを渡す（絞り込みが完全な場合の上限を測るため）。
        return exclude_glossary(
            (entry_from_record(g) for g in row.get("glossary", [])), exclude_terms
        )
    candidates = exclude_glossary(full, exclude_terms) if exclude_terms else full
    return select_glossary(
        formatter_input_text(text),
        candidates,
        args.max_glossary,
        args.min_score,
        selection_index=selection_index,
    )


def percentile(values: list[float], q: float) -> float:
    """線形補間の分位点（`q`は0〜1）。"""
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を読む。"""
    p = argparse.ArgumentParser(description="整形の系を実行して推論結果のJSONLを書く")
    p.add_argument("--manifest", required=True, help="`id`、`glossary`、入力の欄を持つJSONL")
    p.add_argument("--input-field", default="spoken_text", help="`--asr-run`が無いときに入力に使う欄")
    p.add_argument("--asr-run", help="ASRの推論結果のJSONL。指定すると`hyp`を入力にする")
    p.add_argument("--asr-run-first", help="1回目（ヒントなし）のASR結果。`--asr-run`または`--asr-run-combined`と併用できる")
    p.add_argument("--asr-run-combined", help="区間単位の結合文のASR結果。`--asr-run-first`と併用して条件Cを作る")
    p.add_argument("--model", required=True, help=f"MLXのモデルのpathかHugging Faceのrepo。`{RULES_MODEL}`で規則ベースの系")
    p.add_argument("--system", help="出力の`system`の名前。省略時は`--out`のファイル名")
    p.add_argument("--out", required=True, help="runs/<実験名>/<系>.jsonl")
    p.add_argument(
        "--glossary", nargs="+", help="用語集全体のファイル（複数可）。省略時はmanifestの全行の`glossary`の和集合"
    )
    p.add_argument(
        "--exclude-terms",
        default=None,
        help="用語集から除く用語の一覧ファイル（1行1語）。指定した語は整形の参考へ渡さない",
    )
    p.add_argument("--glossary-mode", choices=["select", "row", "none"], default="select",
                   help="select: 用語集全体から絞り込む / row: 各行の正解の用語だけ / none: 渡さない")
    p.add_argument("--max-glossary", type=int, default=DEFAULT_MAX_ENTRIES)
    p.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    p.add_argument("--prefix-cache", action="store_true", help="指示文のKVキャッシュを事前に作って使い回す")
    p.add_argument("--limit", type=int, help="先頭からこの件数だけ実行する（動作確認用）")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """入力を読み、warm-upの1回の後に全件を整形して、結果と要約を書く。"""
    args = parse_args(argv)
    out_path = Path(args.out)
    system = args.system or out_path.stem
    inputs = build_inputs(args)[: args.limit]
    excluded_terms = load_term_list(args.exclude_terms) if args.exclude_terms else None
    full_glossary = (
        load_glossary(*args.glossary, exclude_terms=excluded_terms)
        if args.glossary
        else glossary_from_rows(read_jsonl(args.manifest), exclude_terms=excluded_terms)
    )
    selection_index = GlossaryIndex(full_glossary)

    load_start = time.perf_counter()
    if args.model == RULES_MODEL:
        formatter = None
    else:
        from voiceime.formatter.engine import MlxFormatter  # mlxが要るため、LLMの系を使うときだけ読み込む

        formatter = MlxFormatter(args.model, use_prefix_cache=args.prefix_cache)
        warm = inputs[0]
        formatter.format(
            warm["text"],
            choose_glossary(
                args,
                warm["text"],
                warm["row"],
                full_glossary,
                excluded_terms,
                selection_index,
            ),
        )
    load_s = time.perf_counter() - load_start

    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with open(out_path, "w", encoding="utf-8") as f:
        for item in inputs:
            start = time.perf_counter()
            glossary = choose_glossary(
                args,
                item["text"],
                item["row"],
                full_glossary,
                excluded_terms,
                selection_index,
            )
            record = {"id": item["id"], "system": system, "stage": "e2e"}
            if formatter is None:
                hyp = format_with_rules(formatter_input_text(item["text"]), glossary)
                format_s = time.perf_counter() - start
                extra = {}
            else:
                result = formatter.format(item["text"], glossary)
                hyp = result.text
                format_s = time.perf_counter() - start
                extra = {
                    "prompt_tokens": result.prompt_tokens,
                    "cached_tokens": result.cached_tokens,
                    "generation_tokens": result.generation_tokens,
                    "generation_tps": result.generation_tps,
                    "finish_reason": result.finish_reason,
                }
            record.update(
                hyp=hyp,
                latency_s=item["asr_latency_s"] + format_s,
                format_latency_s=format_s,
                input_text=asdict(item["text"]) if isinstance(item["text"], FormatterInput) else item["text"],
                glossary=[e.surface for e in glossary],
                **extra,
            )
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            records.append(record)

    format_latencies = [r["format_latency_s"] for r in records]
    summary = {
        "system": system,
        "model": args.model,
        "args": vars(args),
        "n": len(records),
        "glossary_size": len(full_glossary),
        "load_and_warmup_s": load_s,
        "format_latency_median_s": statistics.median(format_latencies),
        "format_latency_p90_s": percentile(format_latencies, 0.9),
        "latency_median_s": statistics.median(r["latency_s"] for r in records),
        "mean_glossary_entries": statistics.mean(len(r["glossary"]) for r in records),
    }
    if formatter is not None:
        import mlx.core as mx

        summary.update(
            generation_tps_median=statistics.median(r["generation_tps"] for r in records),
            peak_memory_gb=mx.get_peak_memory() / 1e9,
            truncated=sum(r["finish_reason"] == "length" for r in records),
        )
    out_path.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "args"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
