"""10秒の発話相当の入力で、prefill時間とdecode速度を固定長で測り、整形の遅延を見積もる（一時的な計測、commitしない）。

10秒の発話 ≒ 話し言葉60文字（約6文字/秒と仮定）、整形後 ≒ 50文字と仮定する。
遅延の見積もり = プロンプトのprefill時間 + (整形後のtoken数 + 終端1) / decode速度。
"""
import copy, json, statistics, sys, time
import mlx.core as mx
from mlx_lm import load
from mlx_lm.generate import generate_step
from mlx_lm.models.cache import make_prompt_cache
from voiceime.formatter.engine import MlxFormatter
from voiceime.formatter.glossary import load_glossary, select_glossary
from voiceime.formatter.prompt import render_prompt

SPOKEN = ("あの、昨日話したデータローダーの件なんですけど、なんか、ワーカー数を増やしても速くならなくて、えーと、たぶんディスクの読み込みが律速")[:60]
TARGET = ("昨日話したDataLoaderの件なんですけど、ワーカー数を増やしても速くならなくて、たぶんディスクの読み込みが律速になっていると思います。")[:50]
REPS = 7
DECODE_N = 48

name, path, gloss_path = sys.argv[1], sys.argv[2], sys.argv[3]
glossary = select_glossary(SPOKEN, load_glossary(gloss_path))
f = MlxFormatter(path, use_prefix_cache=True)
tok = f.tokenizer
prompt_tokens = f._encode(render_prompt(tok, SPOKEN, glossary))
n_target = len(tok.encode(TARGET, add_special_tokens=False))
n_prefix = len(f._prefix_tokens)


def prefill_and_decode(tokens, cache):
    """最初のtokenが出るまでの時間と、続くDECODE_N tokenのdecode速度を返す。"""
    t0 = time.perf_counter()
    gen = generate_step(mx.array(tokens), f.model, max_tokens=DECODE_N + 1, prompt_cache=cache)
    next(gen)
    t1 = time.perf_counter()
    for _ in gen:
        pass
    t2 = time.perf_counter()
    return t1 - t0, DECODE_N / (t2 - t1)


# warm-up
prefill_and_decode(prompt_tokens, make_prompt_cache(f.model))
res = {"full": [], "cached": []}
for _ in range(REPS):
    res["full"].append(prefill_and_decode(prompt_tokens, make_prompt_cache(f.model)))
    t0 = time.perf_counter()
    cache = copy.deepcopy(f._prefix_cache)
    copy_s = time.perf_counter() - t0
    p, d = prefill_and_decode(prompt_tokens[n_prefix:], cache)
    res["cached"].append((p + copy_s, d))
out = {"model": name, "prompt_tokens": len(prompt_tokens), "prefix_tokens": n_prefix, "target_tokens_50chars": n_target,
       "chars_per_token": round(len(TARGET) / n_target, 2)}
for k, v in res.items():
    pre = statistics.median(x[0] for x in v)
    tps = statistics.median(x[1] for x in v)
    out[f"{k}_prefill_s"] = round(pre, 4)
    out[f"{k}_decode_tps"] = round(tps, 1)
    out[f"{k}_est_latency_10s_s"] = round(pre + (n_target + 1) / tps, 3)
out["peak_memory_gb"] = round(mx.get_peak_memory() / 1e9, 3)
out["weights_gb"] = round(sum(v.nbytes for _, v in __import__("mlx.utils", fromlist=["tree_flatten"]).tree_flatten(f.model.parameters())) / 1e9, 3)
print(json.dumps(out, ensure_ascii=False))
