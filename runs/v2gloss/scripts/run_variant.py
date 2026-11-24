"""two-passのヒントの上限と選ぶ閾値を一時的に差し替えて`voiceime.asr.run`を動かす計測用の包み。

リポジトリのコードは変えず、`voiceime.engine`のmodule定数と`select_glossary`の既定値だけをこのプロセス内で差し替える。
あわせて、発話ごとの1回目の認識結果、選んだ語、ASRへ渡したヒント、選択にかかった時間を`<out>.hints.jsonl`へ残す。

使い方:
    uv run python run_variant.py --label v2-t16-s75 --max-terms 16 --max-chars 240 --min-score 75 -- <voiceime.asr.runの引数>
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time
from pathlib import Path

import voiceime.engine as eng
from voiceime.asr import run as asr_run
from voiceime.formatter import glossary as gl


def main() -> None:
    """差し替えの値を読み、記録用の包みを付けてASRの実行へ渡し、終了後に名前とメタ情報を書き足す。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="結果の`system`に付ける名前")
    parser.add_argument("--max-terms", type=int, default=eng.ASR_GLOSSARY_MAX_TERMS)
    parser.add_argument("--max-chars", type=int, default=eng.ASR_GLOSSARY_MAX_CHARS)
    parser.add_argument("--min-score", type=float, default=gl.DEFAULT_MIN_SCORE)
    parser.add_argument("--select-max", type=int, default=gl.DEFAULT_MAX_ENTRIES)
    args, rest = parser.parse_known_args()
    if rest and rest[0] == "--":
        rest = rest[1:]

    eng.ASR_GLOSSARY_MAX_TERMS = args.max_terms
    eng.ASR_GLOSSARY_MAX_CHARS = args.max_chars

    log: list[dict] = []
    original_select = gl.select_glossary
    original_hints = eng.asr_hints
    original_two_pass = eng.transcribe_two_pass

    def timed_select(text, entries, *a, **k):
        """選択の時間と選んだ語を記録する。"""
        start = time.perf_counter()
        result = original_select(text, entries, max_entries=args.select_max, min_score=args.min_score)
        log[-1]["select_s"] = time.perf_counter() - start
        log[-1]["selected"] = [e.surface for e in result]
        return result

    def recorded_hints(glossary, hint_format):
        """ASRへ実際に渡したヒントを記録する。"""
        hints = original_hints(glossary, hint_format)
        log[-1]["hints"] = [t.surface for t in hints] if hints else []
        return hints

    def recorded_two_pass(*a, **k):
        """1回目と2回目の認識結果を記録する。"""
        log.append({})
        first, final = original_two_pass(*a, **k)
        log[-1]["first_pass"] = first.text
        log[-1]["final"] = final.text
        return first, final

    eng.select_glossary = timed_select
    eng.asr_hints = recorded_hints
    eng.transcribe_two_pass = recorded_two_pass

    ns = asr_run.parse_args(rest)
    asr_run.main(rest)

    out = Path(ns.out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        row["system"] = args.label
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    measured = log[ns.warmup :]
    assert len(measured) == len(rows), (len(measured), len(rows))
    with open(out.with_name(out.stem + ".hints.jsonl"), "w", encoding="utf-8") as f:
        for row, entry in zip(rows, measured):
            assert entry["final"] == row["hyp"]
            f.write(json.dumps({"id": row["id"], **entry}, ensure_ascii=False) + "\n")
    meta_path = out.with_name(out.stem + ".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["system"] = args.label
    meta["hint_variant"] = {
        "asr_glossary_max_terms": args.max_terms,
        "asr_glossary_max_chars": args.max_chars,
        "select_min_score": args.min_score,
        "select_max_entries": args.select_max,
        "how": "scratchpad/metal-v2gloss/run_variant.pyでvoiceime.engineの定数とselect_glossaryの引数をプロセス内で差し替えた",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.label}: {len(rows)}件", file=sys.stderr)


if __name__ == "__main__":
    main()
