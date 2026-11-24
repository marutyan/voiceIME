"""lookupを全件もう一度走らせ、sliding windowのcacheを壊す巻き戻しが起きた件を記録する。

RotatingKVCacheは長さがwindow（512）を超えた後に巻き戻すと、捨てたはずのtokenが過去の文脈として残る。
巻き戻した直後に`_idx < offset`（リングバッファの扱いに入る状態）になった件を、壊れた件として数える。
指定した件では、各前向き計算の位置ごとの予測と1位-2位の差も記録する。
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace

import mlx.core as mx
from mlx_lm.models import cache as cache_mod

from voiceime.formatter.engine import MlxFormatter
from voiceime.formatter.glossary import DEFAULT_MAX_ENTRIES, DEFAULT_MIN_SCORE, load_glossary
from voiceime.formatter.run import build_inputs, choose_glossary

V = "/Users/marutyan/PrivateDev/voiceIME"
NAME = "devuser-haas2p+sft1-gemma"
CURRENT = {"id": None}
CORRUPTED: set[str] = set()

_orig_trim = cache_mod.RotatingKVCache.trim


def checked_trim(self, n):
    out = _orig_trim(self, n)
    if n > 0 and self._idx < self.offset:
        CORRUPTED.add(CURRENT["id"])
    return out


cache_mod.RotatingKVCache.trim = checked_trim


class LoggingModel:
    """前向き計算の入力tokenと各位置の上位2候補を記録する薄い包み。"""

    def __init__(self, model):
        self.model, self.log = model, []

    def __call__(self, x, cache=None):
        out = self.model(x, cache=cache)
        vals, idx = mx.topk(out[0], 2, axis=-1), mx.argpartition(-out[0], 1, axis=-1)[:, :2]
        self.log.append({"in": x[0].tolist(), "argmax": mx.argmax(out[0], axis=-1).tolist(),
                         "margin": (vals.max(-1) - vals.min(-1)).tolist(), "offset": cache[0].offset})
        return out

    def __getattr__(self, k):
        return getattr(self.model, k)


def main() -> None:
    watch = set(sys.argv[1:])
    args = Namespace(manifest=f"{V}/data/dev-user/manifest.jsonl",
                     asr_run=f"{V}/runs/asr-dev-user/haas-ja-v1.0-speechcpp-q8_0+twopass.jsonl",
                     glossary_mode="select", max_glossary=DEFAULT_MAX_ENTRIES, min_score=DEFAULT_MIN_SCORE,
                     input_field="spoken_text")
    full = load_glossary(f"{V}/data/text/glossary.jsonl")
    fm = MlxFormatter(f"{V}/models/formatter/sft1-gemma-4-e2b-lora/mlx-4bit", use_prefix_cache=True, decode="lookup")
    base_model = fm.model
    rec = {json.loads(l)["id"]: json.loads(l) for l in open(f"{V}/runs/formatter-spec-decode/{NAME}.lookup.jsonl")}
    same = 0
    for it in build_inputs(args):
        CURRENT["id"] = it["id"]
        fm.model = LoggingModel(base_model) if it["id"] in watch else base_model
        r = fm.format(it["text"], choose_glossary(args, it["text"], it["row"], full))
        same += r.text == rec[it["id"]]["hyp"]
        if it["id"] in watch:
            tok = fm.tokenizer
            for step in fm.model.log:
                print(json.dumps({"id": it["id"], "offset_before": step["offset"] - len(step["in"]),
                                  "in": tok.decode(step["in"]) if len(step["in"]) < 40 else f"<{len(step['in'])} tokens>",
                                  "pred": [tok.decode([t]) for t in step["argmax"]][-20:],
                                  "margin": [round(m, 3) for m in step["margin"]][-20:]}, ensure_ascii=False))
    print(json.dumps({"rerun_same_as_recorded_lookup": same, "corrupted_ids": sorted(CORRUPTED)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
