"""lookupの各件で、巻き戻しが黙って飛ばされた回数（cacheがwindowを超えた後）と下書きの最大長を数える。

`trim_prompt_cache`はcacheが巻き戻せない状態だと何もせず0を返すため、捨てるべき下書きがcacheに残る。
"""
import json
from argparse import Namespace

from mlx_lm.models.cache import can_trim_prompt_cache

import voiceime.formatter.engine as eng
from voiceime.formatter.glossary import DEFAULT_MAX_ENTRIES, DEFAULT_MIN_SCORE, load_glossary
from voiceime.formatter.run import build_inputs, choose_glossary

V = "/Users/marutyan/PrivateDev/voiceIME"
CUR = {"id": None}
STATS: dict = {}
_trim, _draft = eng.trim_prompt_cache, eng._lookup_draft_tokens


def trim(cache, n):
    if n > 0 and not can_trim_prompt_cache(cache):
        STATS[CUR["id"]]["skipped_trims"] += 1
        STATS[CUR["id"]]["skipped_tokens"] += n
    return _trim(cache, n)


def draft(*a, **k):
    d = _draft(*a, **k)
    STATS[CUR["id"]]["max_draft"] = max(STATS[CUR["id"]]["max_draft"], len(d))
    return d


eng.trim_prompt_cache, eng._lookup_draft_tokens = trim, draft
args = Namespace(manifest=f"{V}/data/dev-user/manifest.jsonl",
                 asr_run=f"{V}/runs/asr-dev-user/haas-ja-v1.0-speechcpp-q8_0+twopass.jsonl",
                 glossary_mode="select", max_glossary=DEFAULT_MAX_ENTRIES, min_score=DEFAULT_MIN_SCORE, input_field="spoken_text")
full = load_glossary(f"{V}/data/text/glossary.jsonl")
fm = eng.MlxFormatter(f"{V}/models/formatter/sft1-gemma-4-e2b-lora/mlx-4bit", use_prefix_cache=True, decode="lookup")
g = {json.loads(l)["id"]: json.loads(l)["hyp"] for l in open(f"{V}/runs/formatter-spec-decode/devuser-haas2p+sft1-gemma.greedy.jsonl")}
for it in build_inputs(args):
    CUR["id"] = it["id"]
    STATS[it["id"]] = {"skipped_trims": 0, "skipped_tokens": 0, "max_draft": 0}
    r = fm.format(it["text"], choose_glossary(args, it["text"], it["row"], full))
    STATS[it["id"]]["match_greedy"] = r.text == g[it["id"]]
skipped = {k: v for k, v in STATS.items() if v["skipped_trims"]}
print(json.dumps({"items_with_skipped_trim": skipped,
                  "mismatch_without_skipped_trim": [k for k, v in STATS.items() if not v["match_greedy"] and not v["skipped_trims"]],
                  "items_draft_over_16": sum(v["max_draft"] > 16 for v in STATS.values()),
                  "max_draft": max(v["max_draft"] for v in STATS.values())}, ensure_ascii=False, indent=1))
