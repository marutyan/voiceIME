"""greedyとlookupを1件ずつ交互に測り、`runs/<実験名>/<系>.jsonl`の形式で2系の結果を書く。

同じモデルの1つのインスタンスでデコード方式だけを切り替え、負荷の変動が両方に同じように効くようにする。
件ごとに先に測る方式を入れ替え（偶数件はgreedyが先、奇数件はlookupが先）、順番の影響を打ち消す。
lookupが使えないモデル（巻き戻せないcache）では`--greedy-only`でgreedyだけを測る。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import voiceime.formatter.engine as engine
from voiceime.formatter.engine import MlxFormatter
from voiceime.formatter.prompt import render_prompt
from voiceime.formatter.glossary import DEFAULT_MAX_ENTRIES, DEFAULT_MIN_SCORE, load_glossary
from voiceime.formatter.run import build_inputs, choose_glossary


def snapshot_load(label: str) -> str:
    """CPU使用率の上位の処理と、MLXを使う他のpython処理を記録する。"""
    top = subprocess.run(["ps", "-Ao", "pid,%cpu,%mem,comm", "-r"], capture_output=True, text=True).stdout
    procs = subprocess.run(["ps", "-Ao", "pid,%cpu,etime,args"], capture_output=True, text=True).stdout
    others = [l for l in procs.splitlines() if ("voiceime" in l or "mlx" in l) and "alternate_bench" not in l]
    head = "\n".join(top.splitlines()[:8])
    return f"## {label} {time.strftime('%Y-%m-%d %H:%M:%S')}\n{head}\n# MLX/voiceime関連\n" + "\n".join(others) + "\n"


# 修正案の試算用：下書きを16 tokenに抑え、cacheがGemmaのsliding window（512）を超える下書きは出さない。
# コミット済みのコードは変えず、このスクリプトの中だけで`_lookup_draft_tokens`を差し替える。
SLIDING_WINDOW = 512
PROMPT_LEN = {"n": 0}
_original_draft = engine._lookup_draft_tokens


def fixed_draft(input_tokens, generated_tokens, max_tokens=engine.LOOKUP_MAX_DRAFT_TOKENS):
    """下書きの長さを16とwindowの残りで抑える。前向き計算後のcache長 = prompt長 + 生成済み + 下書き。"""
    room = SLIDING_WINDOW - 1 - PROMPT_LEN["n"] - len(generated_tokens)
    limit = max(0, min(max_tokens, engine.LOOKUP_MAX_DRAFT_TOKENS, room))
    return _original_draft(input_tokens, generated_tokens, limit)


def run_one(formatter: MlxFormatter, decode: str, item: dict, args, full_glossary, system: str) -> dict:
    """`voiceime.formatter.run`と同じ範囲（用語の選択から出力の確定まで）で1件を測る。"""
    formatter.decode = decode
    if args.fixed_lookup:
        g0 = choose_glossary(args, item["text"], item["row"], full_glossary)
        PROMPT_LEN["n"] = len(formatter._encode(render_prompt(formatter.tokenizer, item["text"], g0)))
    start = time.perf_counter()
    glossary = choose_glossary(args, item["text"], item["row"], full_glossary)
    result = formatter.format(item["text"], glossary)
    format_s = time.perf_counter() - start
    return {
        "id": item["id"],
        "system": system,
        "stage": "e2e",
        "hyp": result.text,
        "latency_s": item["asr_latency_s"] + format_s,
        "format_latency_s": format_s,
        "input_text": item["text"],
        "glossary": [e.surface for e in glossary],
        "prompt_tokens": result.prompt_tokens,
        "cached_tokens": result.cached_tokens,
        "generation_tokens": result.generation_tokens,
        "generation_tps": result.generation_tps,
        "finish_reason": result.finish_reason,
        "proposed_tokens": result.proposed_tokens,
        "accepted_tokens": result.accepted_tokens,
        "forward_passes": result.forward_passes,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--asr-run", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--glossary", nargs="+", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--name", required=True, help="系の名前の共通部分")
    p.add_argument("--greedy-only", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--fixed-lookup", action="store_true", help="修正案（下書き16 token、window内に限る）で試算する")
    args = p.parse_args()
    if args.fixed_lookup:
        engine._lookup_draft_tokens = fixed_draft
    # choose_glossaryが参照する引数を`voiceime.formatter.run`の既定値と同じにする。
    args.glossary_mode, args.max_glossary, args.min_score = "select", DEFAULT_MAX_ENTRIES, DEFAULT_MIN_SCORE
    args.input_field = "spoken_text"

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    load_log = out_dir / f"{args.name}.load.txt"
    load_log.write_text(snapshot_load("開始前"))

    inputs = build_inputs(args)[: args.limit]
    full_glossary = load_glossary(*args.glossary)
    formatter = MlxFormatter(args.model, use_prefix_cache=True)
    decodes = ["greedy"] if args.greedy_only else ["greedy", "lookup"]
    warm = inputs[0]
    for d in decodes:
        run_one(formatter, d, warm, args, full_glossary, "warmup")

    records = {d: [] for d in decodes}
    for i, item in enumerate(inputs):
        order = decodes if i % 2 == 0 else list(reversed(decodes))
        for d in order:
            records[d].append(run_one(formatter, d, item, args, full_glossary, f"{args.name}.{d}"))
        if (i + 1) % 25 == 0:
            with open(load_log, "a") as f:
                f.write(snapshot_load(f"{i + 1}件目の後"))
    with open(load_log, "a") as f:
        f.write(snapshot_load("終了後"))

    for d, recs in records.items():
        with open(out_dir / f"{args.name}.{d}.jsonl", "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("done", {d: len(r) for d, r in records.items()})


if __name__ == "__main__":
    main()
