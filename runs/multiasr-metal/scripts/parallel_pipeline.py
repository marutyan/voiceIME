"""課題2：Haasのtwo-passと多言語ASRの1回目を、同じMacで順に動かした場合と同時に動かした場合の時間を比べる。

1発話ごとに次の条件を、順番を発話ごとにずらして測る（時間とともに変わる負荷の偏りを条件間で打ち消すため）。
- seq：Haasのtwo-pass（1回目→選択→2回目→区間ごとの採否）を単独で動かし、終わってから多言語ASRを単独で動かす。
- parA：Haasのtwo-passと多言語ASRの1回目を同時に始め、両方が終わるまでの時間を測る。多言語ASRの出力は整形の用語選択にだけ使う。
- parB：Haasの1回目と多言語ASRの1回目を同時に始め、両方が終わってから2つの文をつないだ文字列で語を選び、
  Haasの2回目と区間ごとの採否を行う。多言語ASRをHaasの2回目のヒントにも使う場合の時間。
- format：parAの後に、整形LLM（prefix cache）を、Haasのtwo-passの文だけで選んだ用語（base）と、
  Haasのtwo-passと多言語ASRの文をつないで選んだ用語（union）の2通りで動かす。整形の入力文はどちらもHaasのtwo-passの文。

speech.cppのHaasは別processのworker（Metal）で動き、Python側のthreadは標準入出力を待つだけなので、
MLXの多言語ASR（このprocessのmain thread）と実際に同時にGPUを使う。

実行場所：手元のMac、リポジトリの直下で
    HF_HUB_OFFLINE=1 uv run python runs/multiasr-metal/scripts/parallel_pipeline.py --multi qwen3-asr-0.6b-8bit
"""

from __future__ import annotations

import argparse
import json
import platform
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import mlx.core as mx

from voiceime.asr.base import load_audio
from voiceime.asr.batch import TimedTranscriber
from voiceime.asr.run import git_commit, read_manifest, sample_load, top_processes
from voiceime.asr.systems import MODELS, asr_hint_format, build_transcriber
from voiceime.engine import asr_hints, merge_two_pass_text, transcribe_two_pass
from voiceime.formatter.engine import MlxFormatter
from voiceime.formatter.glossary import GlossaryIndex, load_glossary, select_glossary

REPO = Path("/Users/marutyan/PrivateDev/voiceIME")
MANIFEST = REPO / "data/dev-user/manifest.jsonl"
# 今の既定の構成（`voiceime.engine.__main__`）：Haas Q8_0、用語集第1版、整形はsft2のMLX 4bit。
HAAS = "haas-ja-v1.0-speechcpp-q8_0"
GLOSSARY = REPO / "data/text/glossary.jsonl"
FORMATTER = REPO / "models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit"
# 本人の読み上げはmanifestの先頭50行（dev-user-s000〜s049）。
N_SCRIPTED = 50
# 2つのASRの文をつなぐ区切り。文字種の区間の境目になり、つないだ所で語が誤って一致しないようにする。
JOIN = "\n"
CONDITIONS = ("seq", "parA", "parB")


def run_in_thread(fn, *args):
    """`fn(*args)`を別threadで始め、結果と終了時刻を受け取る関数を返す。"""
    box: dict = {}

    def target() -> None:
        try:
            box["result"] = fn(*args)
        except BaseException as error:  # main threadで再送出し、失敗を握り潰さない
            box["error"] = error
        box["end"] = time.perf_counter()

    thread = threading.Thread(target=target)
    thread.start()

    def join():
        thread.join()
        if "error" in box:
            raise box["error"]
        return box["result"], box["end"]

    return join


class Pipeline:
    """Haas、多言語ASR、整形LLMを1つのprocessに読み込み、条件ごとの時間を測る。"""

    def __init__(self, multi_name: str) -> None:
        self.haas_spec = MODELS[HAAS]
        self.haas = TimedTranscriber(build_transcriber(self.haas_spec, "greedy"))
        self.multi = build_transcriber(MODELS[multi_name], "greedy")
        self.glossary = load_glossary(GLOSSARY)
        self.index = GlossaryIndex(self.glossary)
        self.formatter = MlxFormatter(str(FORMATTER), use_prefix_cache=True)
        self.hint_format = asr_hint_format(self.haas_spec)

    def haas_two_pass(self, audio):
        """今の既定のtwo-pass（segment-merge）。1回目と最終の文、呼び出しごとの時間を返す。"""
        self.haas.durations.clear()
        first, final = transcribe_two_pass(
            self.haas, audio, self.glossary, self.hint_format,
            two_pass_policy="segment-merge", selection_index=self.index,
        )
        return first.text, final.text, list(self.haas.durations)

    def multi_first(self, audio):
        """多言語ASRのヒント無しの1回目。"""
        start = time.perf_counter()
        text = self.multi.transcribe(audio, None).text
        return text, time.perf_counter() - start

    def run_seq(self, audio) -> dict:
        """Haasのtwo-passと多言語ASRを単独で順に動かす。"""
        start = time.perf_counter()
        h1, hfinal, durations = self.haas_two_pass(audio)
        haas_end = time.perf_counter()
        mtext, mlat = self.multi_first(audio)
        end = time.perf_counter()
        return {"wall_s": end - start, "haas_s": haas_end - start, "multi_s": mlat,
                "haas_calls_s": durations, "haas_first": h1, "haas_final": hfinal, "multi": mtext}

    def run_par_a(self, audio) -> dict:
        """Haasのtwo-passと多言語ASRを同時に動かす。"""
        start = time.perf_counter()
        join = run_in_thread(self.haas_two_pass, audio)
        mtext, mlat = self.multi_first(audio)
        multi_end = time.perf_counter()
        (h1, hfinal, durations), haas_end = join()
        end = max(haas_end, multi_end)
        return {"wall_s": end - start, "haas_s": haas_end - start, "multi_s": mlat,
                "haas_calls_s": durations, "haas_first": h1, "haas_final": hfinal, "multi": mtext}

    def run_par_b(self, audio) -> dict:
        """Haasの1回目と多言語ASRを同時に動かし、2つの文から選んだ語でHaasの2回目を行う。"""
        start = time.perf_counter()
        join = run_in_thread(self.haas.transcriber.transcribe, audio, None)
        mtext, mlat = self.multi_first(audio)
        first, first_end = join()
        both_end = time.perf_counter()
        selected = select_glossary(first.text + JOIN + mtext, self.glossary, selection_index=self.index)
        hints = asr_hints(selected, self.hint_format) if selected else None
        final_text = first.text
        if hints:
            by_surface = {entry.surface: entry for entry in selected}
            hinted = [by_surface[t.surface] for t in hints if t.surface in by_surface]
            second = self.haas.transcriber.transcribe(audio, hints)
            final_text = merge_two_pass_text(first.text, second.text, hinted).text
        end = time.perf_counter()
        return {"wall_s": end - start, "haas_first_s": first_end - start, "multi_s": mlat,
                "both_first_s": both_end - start, "haas_first": first.text, "haas_final": final_text,
                "multi": mtext, "n_hints": len(hints or [])}

    def run_format(self, haas_final: str, multi_text: str) -> dict:
        """整形LLMを、base（Haasの文だけで選ぶ）とunion（2つの文をつないで選ぶ）の用語で動かす。"""
        row = {}
        for name, selection_text in (("base", haas_final), ("union", haas_final + JOIN + multi_text)):
            start = time.perf_counter()
            selected = select_glossary(selection_text, self.glossary, selection_index=self.index)
            result = self.formatter.format(haas_final, selected)
            row[name] = {"s": time.perf_counter() - start, "text": result.text,
                         "glossary": [e.surface for e in selected], "finish_reason": result.finish_reason}
        return row

    def close(self) -> None:
        """speech.cppのworkerを止める。"""
        self.haas.transcriber.close()


# 条件の名前と、それを測るPipelineのmethod。
RUNNERS = {"seq": Pipeline.run_seq, "parA": Pipeline.run_par_a, "parB": Pipeline.run_par_b}


def main() -> None:
    """全発話で3条件と整形を測り、1発話1行のJSONLとmetaを書く。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--multi", required=True, choices=sorted(MODELS))
    parser.add_argument("--out-dir", type=Path, default=REPO / "runs/multiasr-metal/parallel")
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()

    records = read_manifest(MANIFEST)[:N_SCRIPTED]
    assert all(r["id"].startswith("dev-user-s") for r in records)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.multi}.jsonl"
    meta = {"multi": args.multi, "haas": HAAS, "glossary": str(GLOSSARY), "formatter": str(FORMATTER),
            "git_commit": git_commit(), "machine": platform.platform(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "top_processes_before": top_processes(), "load_before_model": sample_load()}

    mx.reset_peak_memory()
    load_start = time.perf_counter()
    pipe = Pipeline(args.multi)
    meta["model_load_s"] = time.perf_counter() - load_start
    warm_audio = load_audio(MANIFEST.parent / records[0]["audio_path"])
    for _ in range(args.warmup):
        for condition in CONDITIONS:
            row = RUNNERS[condition](pipe, warm_audio)
        pipe.run_format(row["haas_final"], row["multi"])

    with open(out_path, "w", encoding="utf-8") as out:
        for i, record in enumerate(records):
            audio = load_audio(MANIFEST.parent / record["audio_path"])
            row = {"id": record["id"], "duration_s": len(audio) / 16000, "load": sample_load()}
            # 条件の順番を発話ごとに1つずつずらす。
            order = CONDITIONS[i % 3:] + CONDITIONS[: i % 3]
            row["order"] = list(order)
            for condition in order:
                row[condition] = RUNNERS[condition](pipe, audio)
            row["format"] = pipe.run_format(row["parA"]["haas_final"], row["parA"]["multi"])
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
    pipe.close()
    meta["mlx_peak_memory_gb"] = mx.get_peak_memory() / 1e9
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta["top_processes_after"] = top_processes()
    out_path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(records)}件を{out_path}へ書いた")


if __name__ == "__main__":
    main()
