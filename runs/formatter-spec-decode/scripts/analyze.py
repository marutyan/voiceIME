"""交互計測の結果から、出力の一致、整形時間、前向き計算の回数、採用率をまとめる。

lookupを実行できないモデルでは、greedyの出力token列に対してlookupの手順を再現し、
必要になる前向き計算の回数と採用率を見積もる（実行時間は測れないので回数だけ）。
再現の正しさは、実際にlookupを走らせたモデルの実測値と突き合わせて確かめる。
"""

from __future__ import annotations

import json
import statistics
import sys
import wave
from pathlib import Path

from voiceime.formatter.engine import LOOKUP_MAX_DRAFT_TOKENS, MAX_TOKENS_PER_INPUT_TOKEN, MIN_MAX_TOKENS, _lookup_draft_tokens

V = Path("/Users/marutyan/PrivateDev/voiceIME")
RUNS = V / "runs/formatter-spec-decode"
# 10秒前後の発話として扱う音声長の範囲（秒）。
TEN_S_RANGE = (8.0, 12.0)
# Gemma 4 E2Bのsliding windowの層のcache長（RotatingKVCacheのmax_size）。
GEMMA_WINDOW = 512


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def pct(values: list[float], q: float) -> float:
    o = sorted(values)
    pos = (len(o) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(o) - 1)
    return o[lo] + (o[hi] - o[lo]) * (pos - lo)


def audio_seconds(manifest: list[dict]) -> dict[str, float]:
    out = {}
    for r in manifest:
        with wave.open(str(V / "data/dev-user" / r["audio_path"])) as w:
            out[r["id"]] = w.getnframes() / w.getframerate()
    return out


def simulate_lookup(tokenizer, rec: dict) -> dict:
    """greedyの出力を正解の続きとみなし、lookupが何回の前向き計算で同じ出力に達するかを再現する。"""
    input_ids = tokenizer.encode(rec["input_text"], add_special_tokens=False)
    target = tokenizer.encode(rec["hyp"], add_special_tokens=False)
    if rec["finish_reason"] == "stop":
        target = target + [-1]  # 終端token（値は比較にしか使わない）
    max_tokens = max(MIN_MAX_TOKENS, int(len(input_ids) * MAX_TOKENS_PER_INPUT_TOKEN))
    gen: list[int] = []
    passes = proposed = accepted = 0
    while len(gen) < len(target):
        draft = _lookup_draft_tokens(input_ids, gen, min(LOOKUP_MAX_DRAFT_TOKENS, max_tokens - len(gen)))
        proposed += len(draft)
        passes += 1
        k = 0
        while k < len(draft) and len(gen) + k < len(target) and draft[k] == target[len(gen) + k]:
            k += 1
        accepted += k
        gen += target[len(gen) : len(gen) + k + 1]
    return {"decode_passes": passes, "proposed": proposed, "accepted": accepted}


def summarize(recs: list[dict]) -> dict:
    lat = [r["format_latency_s"] for r in recs]
    return {
        "n": len(recs),
        "format_median_s": statistics.median(lat),
        "format_p90_s": pct(lat, 0.9),
        "forward_passes_mean": statistics.mean(r["forward_passes"] for r in recs),
        "generation_tokens_mean": statistics.mean(r["generation_tokens"] for r in recs),
        "proposed_total": sum(r["proposed_tokens"] for r in recs),
        "accepted_total": sum(r["accepted_tokens"] for r in recs),
    }


def main() -> None:
    manifest = read_jsonl(V / "data/dev-user/manifest.jsonl")
    kind = {r["id"]: r["prompt_kind"] for r in manifest}
    secs = audio_seconds(manifest)
    report: dict = {"ten_s_range": TEN_S_RANGE}
    from transformers import AutoTokenizer

    for name, model_dir in [
        ("devuser-haas2p+sft1-gemma", "sft1-gemma-4-e2b-lora"),
        ("devuser-haas2p+sft1-gemma-fixtrial", "sft1-gemma-4-e2b-lora"),
        ("devuser-haas2p+sft1-gemma-underload", "sft1-gemma-4-e2b-lora"),
        ("devuser-haas2p+sft2-qwen-underload", "sft2-qwen3.5-0.8b-full"),
        ("devuser-haas2p+sft2-qwen", "sft2-qwen3.5-0.8b-full"),
    ]:
        g = read_jsonl(RUNS / f"{name}.greedy.jsonl")
        lk_path = RUNS / f"{name}.lookup.jsonl"
        lk = read_jsonl(lk_path) if lk_path.exists() else None
        tok = AutoTokenizer.from_pretrained(str(V / "models/formatter" / model_dir / "mlx-4bit"))
        m: dict = {}
        subsets = {
            "all": lambda i: True,
            "scripted": lambda i: kind[i] == "scripted",
            "free": lambda i: kind[i] == "free",
            "10s": lambda i: TEN_S_RANGE[0] <= secs[i] <= TEN_S_RANGE[1],
        }
        sims = {r["id"]: simulate_lookup(tok, r) for r in g}
        prefill_passes = {r["id"]: r["forward_passes"] - r["generation_tokens"] - 1 for r in g}
        for sname, f in subsets.items():
            gs = [r for r in g if f(r["id"])]
            entry = {"greedy": summarize(gs)}
            if lk:
                ls = [r for r in lk if f(r["id"])]
                entry["lookup"] = summarize(ls)
                entry["hyp_match"] = sum(a["hyp"] == b["hyp"] for a, b in zip(gs, ls))
                entry["speedup_median"] = entry["greedy"]["format_median_s"] / entry["lookup"]["format_median_s"]
                entry["speedup_p90"] = entry["greedy"]["format_p90_s"] / entry["lookup"]["format_p90_s"]
                entry["paired_ratio_median"] = statistics.median(
                    a["format_latency_s"] / b["format_latency_s"] for a, b in zip(gs, ls)
                )
            sim = [sims[r["id"]] for r in gs]
            entry["simulated_lookup"] = {
                "forward_passes_mean": statistics.mean(s["decode_passes"] + prefill_passes[r["id"]] for s, r in zip(sim, gs)),
                "proposed_total": sum(s["proposed"] for s in sim),
                "accepted_total": sum(s["accepted"] for s in sim),
            }
            m[sname] = entry
        if lk:
            mism = [(a, b) for a, b in zip(g, lk) if a["hyp"] != b["hyp"]]
            m["mismatches"] = [
                {"id": a["id"], "greedy": a["hyp"], "lookup": b["hyp"], "prompt_tokens": a["prompt_tokens"],
                 "greedy_gen": a["generation_tokens"], "lookup_gen": b["generation_tokens"],
                 "finish": [a["finish_reason"], b["finish_reason"]]}
                for a, b in mism
            ]
            # 再現の検証：実測のlookupの前向き計算回数と再現した回数が一致した件数。
            m["simulation_exact"] = sum(
                sims[b["id"]]["decode_passes"] + prefill_passes[b["id"]] == b["forward_passes"] for b in lk
            )
            m["over_window"] = sum(a["prompt_tokens"] + a["generation_tokens"] > GEMMA_WINDOW for a in g)
            m["max_prompt_plus_gen"] = max(a["prompt_tokens"] + a["generation_tokens"] for a in g)
        m["n_10s"] = sum(1 for r in g if subsets["10s"](r["id"]))
        report[name] = m
    out = RUNS / "summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
