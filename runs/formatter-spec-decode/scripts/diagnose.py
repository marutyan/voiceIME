"""greedyとlookupの出力が食い違った件で、最初に分かれたtokenの位置と原因を調べる。

1. 1 tokenずつ前向き計算するgreedyを再現し、分かれた位置での1位と2位のlogitの差を出す。
2. 同じ位置のlogitを、まとめて前向き計算した場合（lookupの検証と同じ形）と比べる。
3. その時点のcacheの長さが、Gemmaのsliding window（512）を超えているかを見る。
"""

from __future__ import annotations

import copy
import json
import sys
from argparse import Namespace

import mlx.core as mx
from mlx_lm.models.cache import make_prompt_cache

from voiceime.formatter.engine import MlxFormatter
from voiceime.formatter.glossary import DEFAULT_MAX_ENTRIES, DEFAULT_MIN_SCORE, load_glossary
from voiceime.formatter.prompt import render_prompt
from voiceime.formatter.run import build_inputs, choose_glossary

V = "/Users/marutyan/PrivateDev/voiceIME"
import os
NAME = os.environ.get("NAME", "devuser-haas2p+sft1-gemma")


def fresh_cache(fm: MlxFormatter, tokens: list[int]):
    """formatterと同じ方法で、prefix cacheの複製と残りのprompt tokenを返す。"""
    n = len(fm._prefix_tokens)
    assert tokens[:n] == fm._prefix_tokens
    return copy.deepcopy(fm._prefix_cache), tokens[n:]


def logits_last(fm, cache, ids):
    out = fm.model(mx.array(ids)[None], cache=cache)
    mx.eval(out)
    return out[0]


def main() -> None:
    ids = sys.argv[1:]
    args = Namespace(manifest=f"{V}/data/dev-user/manifest.jsonl",
                     asr_run=f"{V}/runs/asr-dev-user/haas-ja-v1.0-speechcpp-q8_0+twopass.jsonl",
                     glossary_mode="select", max_glossary=DEFAULT_MAX_ENTRIES, min_score=DEFAULT_MIN_SCORE,
                     input_field="spoken_text")
    items = {it["id"]: it for it in build_inputs(args)}
    full = load_glossary(f"{V}/data/text/glossary.jsonl")
    fm = MlxFormatter(f"{V}/models/formatter/sft1-gemma-4-e2b-lora/mlx-4bit", use_prefix_cache=True)
    tok = fm.tokenizer
    lk = {json.loads(l)["id"]: json.loads(l) for l in open(f"{V}/runs/formatter-spec-decode/{NAME}.lookup.jsonl")}
    for i in ids:
        it = items[i]
        prompt = fm._encode(render_prompt(tok, it["text"], choose_glossary(args, it["text"], it["row"], full)))
        # 1 tokenずつのgreedy（各位置のlogitと1位-2位の差を記録）
        cache, rest = fresh_cache(fm, prompt)
        logits = logits_last(fm, cache, rest)[-1]
        seq, margins = [], []
        for _ in range(80):
            top2 = mx.topk(logits, 2).tolist()
            t = int(mx.argmax(logits).item())
            margins.append(abs(top2[0] - top2[1]) if len(top2) == 2 else None)
            seq.append(t)
            if t in tok.eos_token_ids:
                break
            logits = logits_last(fm, cache, [t])[-1]
        greedy_text = tok.decode([t for t in seq if t not in tok.eos_token_ids])
        lk_ids = tok.encode(lk[i]["hyp"], add_special_tokens=False)
        d = next((k for k in range(min(len(seq), len(lk_ids))) if seq[k] != lk_ids[k]), min(len(seq), len(lk_ids)))
        # 同じ位置のlogitを、promptの後に生成済みtokenをまとめて渡して計算する（lookupの検証と同じ形）。
        cache2, rest2 = fresh_cache(fm, prompt)
        logits_last(fm, cache2, rest2[:-1])
        block_logits = logits_last(fm, cache2, [rest2[-1], *seq[:d]])[-1]
        block_arg = int(mx.argmax(block_logits).item())
        # 1 tokenずつの場合のlogit（再計算）との差
        cache3, rest3 = fresh_cache(fm, prompt)
        lg = logits_last(fm, cache3, rest3)[-1]
        for t in seq[:d]:
            lg = logits_last(fm, cache3, [t])[-1]
        max_abs = float(mx.max(mx.abs(lg.astype(mx.float32) - block_logits.astype(mx.float32))).item())
        top_seq = mx.topk(lg, 2).tolist()
        print(json.dumps({
            "id": i, "prompt_tokens": len(prompt), "diverge_at": d, "cache_len_at_diverge": len(prompt) + d,
            "seq_text": greedy_text[:80],
            "seq_token": tok.decode([seq[d]]) if d < len(seq) else None,
            "lookup_token": tok.decode([lk_ids[d]]) if d < len(lk_ids) else "<eos>",
            "margin_top1_top2_at_d": margins[d] if d < len(margins) else None,
            "block_forward_argmax": tok.decode([block_arg]),
            "block_vs_seq_max_abs_logit_diff": max_abs,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
