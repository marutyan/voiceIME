"""文章データ（JSONL）を合成音声で読み上げ、16kHzモノラル16bitのWAVとmanifestを作る。

行ごとの割り当て（行IDとseedから決まり、何度実行しても同じになる）:
- 声: `split` が `test-synth` の行は voices.json の `use: test-synth` の声から、
  それ以外（`train`、`val`）は `use: train-val` の声から選ぶ。学習とtest-synthで声が重ならない。
- TTS: 約20%の行は多言語TTS（Qwen3-TTS）で `spoken_text_mixed` を読み、
  残りは日本語TTS（Irodori-TTS）で `spoken_text_kana` を読む。manifestの `source` に残す。
- 速さと抑揚: 速さを±8%の範囲で揺らす。日本語TTSでは抑揚の指示（キャプション）も3通りから選ぶ。

二つのTTSは依存関係が異なるため、TTSごとに別の仮想環境で `run --engine ja|multi` を実行し、
最後に `merge` で入力の順にmanifestをまとめる。

再開: `run` は出力先の `parts/<engine>.jsonl` に書き終えた行を記録し、次回はその行を飛ばす。
WAVは一時ファイルに書いてから名前を変え、記録はWAVの後に追記するため、途中で止まっても
記録された行の音声は必ず完全である。

使い方（ColabのGPU上。手元から一式を動かす手順は colab_run.sh を参照）:
    <Irodori-TTSの環境のpython> synthesize.py run --engine ja --input X.jsonl --voices voices.json \
        --voice-dir <参照音声> --out <出力先>
    <Qwen3-TTSの環境のpython> synthesize.py run --engine multi ...（同じ引数）
    python synthesize.py merge --input X.jsonl --out <出力先>
"""

import argparse
import hashlib
import json
import os
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

from make_voices import REF_TEXT, load_voices

OUT_SR = 16000
# 多言語TTSで英字を残した文を読ませる行の割合。
MULTI_RATIO = 0.2
# 話す速さの倍率の範囲（1.0が元の速さ）。
SPEED_RANGE = (0.92, 1.08)
SOURCE = {"ja": "synthetic-tts-ja", "multi": "synthetic-tts-multi"}
TEXT_FIELD = {"ja": "spoken_text_kana", "multi": "spoken_text_mixed"}
TTS_MODEL = {"ja": "Aratako/Irodori-TTS-v4.1-Small", "multi": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"}
# 日本語TTSへ渡す抑揚の指示。声の説明文の後ろに付ける。
JA_INTONATION = ["普段どおりの抑揚で話している。", "抑揚をやや大きくつけて話している。", "抑揚を抑えて淡々と話している。"]
VALID_SPLITS = ("train", "val", "test-synth")
# 生成する順（小さいほど先）。
SPLIT_ORDER = {"test-synth": 0, "val": 1, "train": 2}
# 生成の失敗（無音、途中で切れる、同じ音の繰り返し）を見分けるための、1秒あたりの文字数の許容範囲。
# 日本語の会話はおよそ6〜10文字/秒。英字は1文字を0.4文字として数える（英単語は文字数の割に短く読むため）。
CHARS_PER_SEC_RANGE = (3.0, 16.0)
# manifestの先頭に置く項目（docs/PLAN.mdの形式の順）。入力の他の欄はこの後ろへそのまま引き継ぐ。
MANIFEST_KEYS = ["id", "split", "audio_path", "spoken_text", "target_text", "terms", "glossary", "speaker", "source", "domain", "fillers"]


def unit_hash(*parts) -> float:
    """引数から[0, 1)の値を決定的に作る。Pythonのhash()と違い、実行ごとに変わらない。"""
    digest = hashlib.sha256("\x1f".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def read_rows(path: Path, default_split: str | None) -> list[dict]:
    """入力JSONLを読み、各行の `split` を確定させて返す。"""
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        split = row.get("split", default_split)
        if split not in VALID_SPLITS:
            raise ValueError(f"{row.get('id')}: split が無いか不正（{split}）。入力に split を入れるか --default-split を指定する")
        row["split"] = split
        rows.append(row)
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("入力に重複したidがある")
    return rows


def plan_row(row: dict, voices: list[dict], seed: int) -> dict:
    """1行に、使うTTS、声、速さ、抑揚の指示を割り当てる。"""
    use = "test-synth" if row["split"] == "test-synth" else "train-val"
    pool = [v for v in voices if v["use"] == use]
    voice = pool[int(unit_hash(seed, "voice", row["id"]) * len(pool))]
    engine = "multi" if unit_hash(seed, "engine", row["id"]) < MULTI_RATIO else "ja"
    lo, hi = SPEED_RANGE
    # 速さは0.01刻みにする。多言語TTSのリサンプリングで周波数が整数になるようにするため。
    speed = round(lo + (hi - lo) * unit_hash(seed, "speed", row["id"]), 2)
    intonation = JA_INTONATION[int(unit_hash(seed, "intonation", row["id"]) * len(JA_INTONATION))]
    return {"engine": engine, "voice": voice, "speed": speed, "intonation": intonation if engine == "ja" else None,
            "text": row[TEXT_FIELD[engine]]}


def spoken_length(text: str) -> float:
    """読み上げる長さの目安として、句読点と空白を除いた文字数を数える（英字は0.4文字）。"""
    n = 0.0
    for ch in unicodedata.normalize("NFKC", text):
        if ch.isspace() or unicodedata.category(ch).startswith(("P", "S")):
            continue
        n += 0.4 if ch.isascii() and ch.isalpha() else 1.0
    return n


def length_problem(text: str, duration_s: float) -> str | None:
    """音声の長さが文の長さに見合わなければ理由を返す。外れたものは生成の失敗とみなして作り直す。"""
    cps = spoken_length(text) / max(duration_s, 1e-3)
    if CHARS_PER_SEC_RANGE[0] <= cps <= CHARS_PER_SEC_RANGE[1]:
        return None
    return f"長さが文に見合わない（{duration_s:.1f}秒、{cps:.1f}文字/秒）"


def to_16k(wav: np.ndarray, sr: int, speed: float = 1.0) -> np.ndarray:
    """16kHzへ変換する。speed≠1のときは、元の音声を sr*speed で録ったものとみなして変換し、
    速さと声の高さを同じ割合で変える（音声認識の学習で広く使われる速度摂動と同じ方法）。"""
    import torch
    import torchaudio.functional as AF

    x = torch.from_numpy(np.asarray(wav, dtype=np.float32)).reshape(1, -1)
    y = AF.resample(x, orig_freq=int(round(sr * speed)), new_freq=OUT_SR)[0].numpy()
    peak = float(np.abs(y).max()) if y.size else 0.0
    # 16bitへ書くときに割れないよう、振幅が上限に近い場合だけ縮める。
    return y * (0.95 / peak) if peak > 0.95 else y


def write_wav_atomic(path: Path, wav16k: np.ndarray) -> None:
    """一時ファイルへ書いてから名前を変え、途中で止まっても壊れたWAVを残さない。"""
    tmp = path.with_suffix(".tmp.wav")
    sf.write(tmp, wav16k, OUT_SR, subtype="PCM_16")
    os.replace(tmp, path)


def append_record(path: Path, record: dict) -> None:
    """書き終えた行の記録を1行追記し、ディスクへ確実に書き出す。"""
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def done_ids(path: Path) -> set[str]:
    """記録済みの行IDを返す。最後の行が途中で切れていれば無視する（その行は作り直す）。"""
    ids = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                ids.add(json.loads(line)["manifest"]["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


class IrodoriEngine:
    """日本語TTS（Irodori-TTS v4.1-Small、MIT）。参照音声で声を複製し、速さと抑揚を指示する。"""

    def __init__(self):
        import torch
        from irodori_tts.inference_runtime import InferenceRuntime, RuntimeKey, download_hf_checkpoint

        self.torch = torch
        ckpt = download_hf_checkpoint(TTS_MODEL["ja"])
        self.rt = InferenceRuntime.from_key(RuntimeKey(checkpoint=ckpt, model_device="cuda", model_precision="bf16",
                                                       codec_device="cuda", codec_precision="fp32"))

    def generate(self, plans: list[dict], voice_dir: Path, seed: int) -> tuple[list[np.ndarray], int]:
        from irodori_tts.inference_runtime import SamplingRequest

        reqs = [SamplingRequest(text=p["text"], ref_wav=str(voice_dir / f"{p['voice']['speaker']}.wav"),
                                caption=p["voice"]["description_ja"] + p["intonation"],
                                duration_scale=1.0 / p["speed"], seed=seed) for p in plans]
        results = self.rt.synthesize_batch(reqs)
        return [r.audio.squeeze().float().cpu().numpy() for r in results], results[0].sample_rate


class QwenEngine:
    """多言語TTS（Qwen3-TTS 1.7B Base、Apache-2.0）。参照音声と同じ文を渡して声を複製する。"""

    def __init__(self):
        import torch
        from qwen_tts import Qwen3TTSModel

        self.torch = torch
        self.model = Qwen3TTSModel.from_pretrained(TTS_MODEL["multi"], device_map="cuda:0", dtype=torch.bfloat16,
                                                   attn_implementation="sdpa")
        self.prompts = {}

    def _prompt(self, speaker: str, voice_dir: Path):
        if speaker not in self.prompts:
            self.prompts[speaker] = self.model.create_voice_clone_prompt(ref_audio=str(voice_dir / f"{speaker}.wav"), ref_text=REF_TEXT)
        return self.prompts[speaker]

    def generate(self, plans: list[dict], voice_dir: Path, seed: int) -> tuple[list[np.ndarray], int]:
        self.torch.manual_seed(seed)
        prompts = [self._prompt(p["voice"]["speaker"], voice_dir)[0] for p in plans]
        # 日本人が話す日英混在の発話に近づけるため、言語は日本語として読ませる。
        wavs, sr = self.model.generate_voice_clone(text=[p["text"] for p in plans], language=["Japanese"] * len(plans),
                                                   voice_clone_prompt=prompts)
        return wavs, sr


def build_record(row: dict, plan: dict, duration_s: float, attempt: int) -> dict:
    """manifestの1行と、分析用のTTSの設定をまとめた記録を作る。
    manifestは入力の行の欄をすべて引き継ぎ、spoken_text（実際に読んだ文）、audio_path、speaker、source を上書きする。"""
    full = {**row, "audio_path": f"audio/{row['id']}.wav", "spoken_text": plan["text"],
            "speaker": plan["voice"]["speaker"], "source": SOURCE[plan["engine"]]}
    manifest = {k: full[k] for k in MANIFEST_KEYS if k in full}
    manifest.update({k: v for k, v in full.items() if k not in manifest})
    meta = {"id": row["id"], "tts_model": TTS_MODEL[plan["engine"]], "speed": plan["speed"],
            "intonation": plan["intonation"], "duration_s": round(duration_s, 3), "attempt": attempt}
    return {"manifest": manifest, "meta": meta}


def synthesize_rows(engine, rows: list[dict], plans: dict, args: argparse.Namespace, attempt: int) -> list[tuple]:
    """行をまとめて生成し、行ごとに (行, 16kHzの音声または None, 失敗の理由) を返す。
    一括生成が例外で落ちた場合は、1件の不具合で他の行まで失わないよう1件ずつやり直す。"""
    seed = int(unit_hash(args.seed, "gen", rows[0]["id"], attempt) * 2**31)
    try:
        wavs, sr = engine.generate([plans[r["id"]] for r in rows], args.voice_dir, seed)
    except Exception as e:  # noqa: BLE001  モデル内部の例外の種類は事前に分からないため広く受ける
        print(f"[{args.engine}] 生成の例外（{len(rows)}件）: {type(e).__name__}: {str(e)[:200]}", flush=True)
        if len(rows) == 1:
            return [(rows[0], None, f"生成の例外: {type(e).__name__}: {str(e)[:200]}")]
        engine.torch.cuda.empty_cache()
        return [res for r in rows for res in synthesize_rows(engine, [r], plans, args, attempt)]
    results = []
    for row, wav in zip(rows, wavs):
        plan = plans[row["id"]]
        # 日本語TTSは生成時に速さを指示済み。多言語TTSは16kHzへの変換時に速さを変える。
        wav16k = to_16k(wav, sr, speed=plan["speed"] if args.engine == "multi" else 1.0)
        problem = length_problem(plan["text"], len(wav16k) / OUT_SR)
        results.append((row, None if problem else wav16k, problem))
    return results


def run(args: argparse.Namespace) -> None:
    """指定したTTSに割り当てられた行のうち、未完了のものを生成して記録する。"""
    rows = read_rows(args.input, args.default_split)
    voices = load_voices(args.voices)
    plans = {r["id"]: plan_row(r, voices, args.seed) for r in rows}
    (args.out / "audio").mkdir(parents=True, exist_ok=True)
    (args.out / "parts").mkdir(exist_ok=True)
    record_path = args.out / "parts" / f"{args.engine}.jsonl"
    failed_path = args.out / "parts" / f"{args.engine}.failed.jsonl"
    finished = done_ids(record_path)
    todo = [r for r in rows if plans[r["id"]]["engine"] == args.engine and r["id"] not in finished]
    if args.limit:
        todo = todo[: args.limit]
    print(f"[{args.engine}] 割り当て{sum(p['engine'] == args.engine for p in plans.values())}件、完了{len(finished)}件、今回{len(todo)}件", flush=True)
    if not todo:
        return

    engine = IrodoriEngine() if args.engine == "ja" else QwenEngine()
    # 時間の上限で止まっても評価用の集合が欠けないよう、test-synth、val、trainの順に作る。
    # 各集合の中では長さの近い文をまとめると、一括生成での詰め物が減って速くなる。
    todo.sort(key=lambda r: (SPLIT_ORDER[r["split"]], spoken_length(plans[r["id"]]["text"])))
    t_start, audio_total = time.time(), 0.0
    for b in range(0, len(todo), args.batch_size):
        batch = todo[b : b + args.batch_size]
        pending, attempt, reasons = batch, 0, {}
        while pending and attempt <= args.retries:
            retry = []
            for row, wav16k, problem in synthesize_rows(engine, pending, plans, args, attempt):
                if wav16k is None:
                    retry.append(row)
                    reasons[row["id"]] = problem
                    continue
                duration = len(wav16k) / OUT_SR
                write_wav_atomic(args.out / "audio" / f"{row['id']}.wav", wav16k)
                append_record(record_path, build_record(row, plans[row["id"]], duration, attempt))
                audio_total += duration
            pending, attempt = retry, attempt + 1
        for row in pending:
            append_record(failed_path, {"id": row["id"], "split": row["split"], "text": plans[row["id"]]["text"],
                                        "reason": reasons[row["id"]]})
        elapsed = time.time() - t_start
        print(f"[{args.engine}] {min(b + args.batch_size, len(todo))}/{len(todo)} 音声{audio_total:.0f}秒 経過{elapsed:.0f}秒 "
              f"RTF={elapsed / max(audio_total, 1e-6):.3f} 失敗{len(pending)}", flush=True)


def read_parts(out: Path, failed: bool) -> dict[str, dict]:
    """parts/ の記録（failed=True なら捨てた行の記録）をidごとに読む。途中で切れた行は無視する。"""
    records = {}
    for part in sorted((out / "parts").glob("*.jsonl")):
        if part.name.endswith(".failed.jsonl") != failed:
            continue
        for line in part.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            records[rec["id"] if failed else rec["manifest"]["id"]] = rec
    return records


def write_set(dest: Path, ids: list[str], records: dict, discarded: list[dict], audio_src: Path | None) -> None:
    """1つの集合のmanifest、TTSの設定、捨てた行を書く。audio_src があれば音声をハードリンクで置く。
    コピーでなくハードリンクにするのは、作業用の出力（再開に使う）を残したまま容量を増やさないため。"""
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / "manifest.jsonl").open("w") as fm, (dest / "tts_meta.jsonl").open("w") as ft:
        for i in ids:
            fm.write(json.dumps(records[i]["manifest"], ensure_ascii=False) + "\n")
            ft.write(json.dumps(records[i]["meta"], ensure_ascii=False) + "\n")
    with (dest / "discarded.jsonl").open("w") as fd:
        for d in discarded:
            fd.write(json.dumps(d, ensure_ascii=False) + "\n")
    if audio_src is not None:
        (dest / "audio").mkdir(exist_ok=True)
        for i in ids:
            target = dest / "audio" / f"{i}.wav"
            if not target.exists():
                os.link(audio_src / f"{i}.wav", target)


def merge(args: argparse.Namespace) -> None:
    """TTSごとの記録を入力の順に並べ、manifest.jsonl、tts_meta.jsonl、discarded.jsonl を書く。
    --split-out を指定すると、<split-out>/<split>/ に集合ごとに分けて書き、音声も置く。"""
    records = read_parts(args.out, failed=False)
    failed = read_parts(args.out, failed=True)
    rows = read_rows(args.input, args.default_split)
    done = [r for r in rows if r["id"] in records]
    discarded = [failed[r["id"]] for r in rows if r["id"] not in records and r["id"] in failed]
    if args.split_out is None:
        write_set(args.out, [r["id"] for r in done], records, discarded, None)
    else:
        for split in VALID_SPLITS:
            ids = [r["id"] for r in done if r["split"] == split]
            if ids or any(r["split"] == split for r in rows):
                write_set(args.split_out / split, ids, records, [d for d in discarded if d.get("split") == split],
                          args.out / "audio")
    for split in VALID_SPLITS:
        n_in = sum(r["split"] == split for r in rows)
        if n_in:
            n_ok = sum(r["split"] == split for r in done)
            n_ng = sum(d.get("split") == split for d in discarded)
            sec = sum(records[r["id"]]["meta"]["duration_s"] for r in done if r["split"] == split)
            print(f"{split}: 入力{n_in}件、生成{n_ok}件（{sec / 3600:.2f}時間）、捨てた{n_ng}件、未生成{n_in - n_ok - n_ng}件")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "merge"):
        p = sub.add_parser(name)
        p.add_argument("--input", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--default-split", choices=VALID_SPLITS, help="入力の行に split が無いときに使う値")
    sub.choices["merge"].add_argument("--split-out", type=Path, help="集合ごとに分けて書く先（<split-out>/<split>/）")
    p_run = sub.choices["run"]
    p_run.add_argument("--engine", choices=("ja", "multi"), required=True)
    p_run.add_argument("--voices", type=Path, required=True)
    p_run.add_argument("--voice-dir", type=Path, required=True, help="make_voices.py で作った参照音声のディレクトリ")
    p_run.add_argument("--seed", type=int, default=0, help="割り当てと生成の乱数のseed（docs/PLAN.mdの既定は0）")
    p_run.add_argument("--batch-size", type=int, default=16)
    p_run.add_argument("--retries", type=int, default=2, help="長さが文に見合わない音声を作り直す回数")
    p_run.add_argument("--limit", type=int, default=0, help="今回生成する最大件数（0は全件）")
    args = parser.parse_args()
    run(args) if args.command == "run" else merge(args)


if __name__ == "__main__":
    main()
