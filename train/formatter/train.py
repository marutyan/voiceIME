"""整形用LLMの教師あり学習（蒸留）。ColabのGPUで実行する。

入力は`data/text/train.jsonl`と`val.jsonl`（`docs/PLAN.md`の形式で、`spoken_text`、`target_text`、`glossary`を持つ）。
プロンプトは`voiceime.formatter.prompt`で作り、手元の推論と同じ形式にする。
LoRAと全パラメータ学習を`--method`で選び、valの損失が最小のcheckpointを`<output-dir>/final`へ保存する
（LoRAの場合は元の重みへ統合して保存し、そのままMLXへ変換できる形にする。`--save-adapter-only`ではadapterだけを
`<output-dir>/adapter`へ保存し、手元の`merge_lora.py`で統合する）。
入力はASRの実出力（`--train-asr-run`、確率`--nohint-prob`でヒント無しの`--train-asr-run-nohint`）を使う。
`--input-passes both`では1回目と2回目を両方渡し、`combined_first`では1回目と区間単位の結合文を渡す。
`--allow-partial-asr`を付けると、ASRの結果が無い行（音声の無い文）は、`--asr-noise-prob`の確率で`spoken_marked`から
`asr_noise.py`の加工でASRに似せた入力にする（同じ確率`--nohint-prob`でヒント無しの加工にする）。
さらに確率`--user-punct-prob`で、句読点を本人の声での付き方へ寄せる。

例（Colab上で実行する。`voiceime`の`src`を`PYTHONPATH`へ入れておく）:
    python train/formatter/train.py --model Qwen/Qwen3.5-0.8B --train data/text/train.jsonl \\
        --val data/text/val.jsonl --method lora --output-dir /content/out
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
from transformers import AutoTokenizer, Trainer, TrainingArguments

from model_loader import load_formatter_model

from model_loader import load_formatter_model

from voiceime.formatter.glossary import (
    DEFAULT_MAX_ENTRIES,
    GlossaryEntry,
    entry_from_record,
    glossary_from_rows,
    load_glossary,
    merge_entries,
    select_glossary,
)
from voiceime.formatter.prompt import FormatterInput, formatter_input_text, needs_special_tokens, render_training_pair
from voiceime.formatter.style import apply_output_style

from asr_noise import (
    HAAS_NOHINT,
    HAAS_TWOPASS,
    plan_two_pass_error_overrides,
    simulate_asr_noise,
    to_user_punctuation,
)  # 同じdirの train/formatter/asr_noise.py

# 損失を計算しない位置のラベル（PyTorchのcross entropyが無視する値）。
IGNORE_INDEX = -100


def read_jsonl(path: str | Path) -> list[dict]:
    """1行1件のJSONLを読み込む。"""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_hyps_by_id(asr_run: str | None) -> dict[str, str]:
    """ASR runをidで引ける形にし、重複IDや空でない文字列以外のhypを拒否する。"""
    if not asr_run:
        return {}
    hyps = {}
    for row in read_jsonl(asr_run):
        sample_id, hyp = row.get("id"), row.get("hyp")
        if not isinstance(sample_id, str) or not isinstance(hyp, str):
            raise ValueError(f"{asr_run}: idとhypは文字列である必要があります")
        if sample_id in hyps:
            raise ValueError(f"{asr_run}: idが重複しています: {sample_id}")
        hyps[sample_id] = hyp
    return hyps


def load_inputs(rows: list[dict], input_field: str, asr_run: str | None, allow_missing: bool = False) -> list[str]:
    """各行の入力文を返す。`asr_run`があればASRの`hyp`、無ければ`input_field`の欄を使う。

    `allow_missing`が真なら、ASRの結果が無い行は`input_field`の欄を使う（学習では加工の対象にする）。
    """
    if not asr_run:
        return [r[input_field] for r in rows]
    hyp_by_id = load_hyps_by_id(asr_run)
    missing = [r["id"] for r in rows if r["id"] not in hyp_by_id]
    if missing and not allow_missing:
        raise ValueError(f"ASRの結果が無い行が{len(missing)}件あります（例: {missing[:3]}）")
    print(f"{asr_run}: ASRの結果がある行 {len(rows) - len(missing)}件、無い行 {len(missing)}件", flush=True)
    return [hyp_by_id.get(r["id"], r[input_field]) for r in rows]


def load_optional_hyps(rows: list[dict], asr_run: str | None) -> list[str | None]:
    """各行のASRの`hyp`を返す（結果が無い行と、`asr_run`が無い場合は`None`）。加工するかどうかの判定と、別の系の入力に使う。"""
    hyp_by_id = load_hyps_by_id(asr_run)
    return [hyp_by_id.get(r["id"]) for r in rows]


def load_optional_glossaries(rows: list[dict], glossary_run: str | None) -> list[list[GlossaryEntry] | None]:
    """selector runをidで引き、未収録IDはASRが無い行用にNoneで返す。"""
    if not glossary_run:
        return [None] * len(rows)
    glossaries: dict[str, list[GlossaryEntry]] = {}
    for record in read_jsonl(glossary_run):
        sample_id, entries = record.get("id"), record.get("glossary")
        if not isinstance(sample_id, str) or not isinstance(entries, list):
            raise ValueError(f"{glossary_run}: idとglossary配列が必要です")
        if sample_id in glossaries:
            raise ValueError(f"{glossary_run}: idが重複しています: {sample_id}")
        if not all(isinstance(entry, dict) for entry in entries):
            raise ValueError(f"{glossary_run}: glossaryは用語objectの配列が必要です")
        glossaries[sample_id] = [entry_from_record(entry) for entry in entries]
    return [glossaries.get(row["id"]) for row in rows]


def validate_selected_glossaries(
    rows: list[dict], selected: list[list[GlossaryEntry] | None], pool: list[GlossaryEntry], max_entries: int
) -> None:
    """selector出力が指定上限内で、splitごとの用語集から漏れていないことを確かめる。"""
    available = {entry.surface for entry in pool}
    for row, entries in zip(rows, selected, strict=True):
        if entries is None:
            continue
        if len(entries) > max_entries:
            raise ValueError(f"{row['id']}: selector用語一覧が上限{max_entries}件を超えています")
        missing = [entry.surface for entry in entries if entry.surface not in available]
        if missing:
            raise ValueError(f"{row['id']}: split用語集に無いselector語があります: {missing[:3]}")


def augment_glossary(
    retrieved: list[GlossaryEntry],
    gold: list[GlossaryEntry],
    pool: list[GlossaryEntry],
    rng: random.Random,
    drop_prob: float,
    max_distractors: int,
    max_entries: int,
) -> list[GlossaryEntry]:
    """絞り込みの結果から正解の用語を確率`drop_prob`で抜き、無関係な語を混ぜて順序を入れ替える。

    推論時の用語集は、絞り込みの取りこぼしや無関係な語を含む。学習でもその状態を作り、
    用語集に無い語を推測する力と、無関係な語を使わない判断を学ばせる。
    """
    gold_surfaces = {e.surface for e in gold}
    kept = [e for e in retrieved if e.surface not in gold_surfaces or rng.random() >= drop_prob]
    used = {e.surface for e in kept}
    candidates = [e for e in pool if e.surface not in used and e.surface not in gold_surfaces]
    n_distract = min(rng.randint(0, max_distractors), len(candidates), max(0, max_entries - len(kept)))
    kept += rng.sample(candidates, n_distract)
    rng.shuffle(kept)
    return kept[:max_entries]


def tokenize_pair(tokenizer, input_text: str | FormatterInput, glossary: list[GlossaryEntry], target: str, max_length: int) -> dict:
    """プロンプトと応答をtoken化し、応答部分だけに損失がかかるラベルを作る。

    プロンプトは推論時と同じく単独でtoken化し、応答は続きとしてtoken化する。
    """
    prompt, completion = render_training_pair(tokenizer, input_text, glossary, apply_output_style(target))
    prompt_ids = tokenizer(prompt, add_special_tokens=needs_special_tokens(tokenizer, prompt))["input_ids"]
    completion_ids = tokenizer(completion, add_special_tokens=False)["input_ids"]
    input_ids = (prompt_ids + completion_ids)[:max_length]
    labels = ([IGNORE_INDEX] * len(prompt_ids) + completion_ids)[:max_length]
    return {"input_ids": input_ids, "labels": labels}


class FormatterDataset(torch.utils.data.Dataset):
    """整形の学習例を作るDataset。学習用は取り出すたびに入力の選び方、加工、用語集の混ぜ方を変える。

    `single`では実出力を確率`nohint_prob`で選び、ASRが無い行は確率`asr_noise_prob`で`spoken_marked`から加工する。
    `both`では2つの実出力、`combined_first`では1回目と結合文、`multiasr`では1回目・結合文・Qwen仮説を渡す。
    最後に確率`user_punct_prob`で句読点を本人の声での付き方へ寄せる。

    検証用（`train=False`）は加工をかけず、推論時と同じ絞り込みの結果だけを渡して、checkpoint間で比べられるようにする。
    乱数はtorchの乱数から引く。DataLoaderのworkerごとにtorchの乱数が別のseedで初期化されるため、
    workerを増やしても同じ乱数列が重ならず、`--seed`とworker数が同じなら再現できる。
    """

    def __init__(
        self, rows, inputs, pool, tokenizer, args, train: bool,
        asr_hyps=None, nohint_hyps=None, combined_hyps=None, qwen_hyps=None, selected_glossaries=None,
    ):
        self.rows, self.inputs, self.pool, self.tokenizer, self.args, self.train = rows, inputs, pool, tokenizer, args, train
        # 学習用だけで使う。各行の実出力（two-passとヒント無し）。`None`の行は音声が無い。
        self.asr_hyps = asr_hyps or [None] * len(rows)
        self.nohint_hyps = nohint_hyps or [None] * len(rows)
        self.combined_hyps = combined_hyps or [None] * len(rows)
        self.qwen_hyps = qwen_hyps or [None] * len(rows)
        self.selected_glossaries = selected_glossaries or [None] * len(rows)
        self.input_passes = getattr(args, "input_passes", "single")
        if self.input_passes in {"both", "combined_first", "multiasr"}:
            mismatched = [
                i for i, (second, first, combined) in enumerate(
                    zip(self.asr_hyps, self.nohint_hyps, self.combined_hyps, strict=True)
                )
                if (
                    self.input_passes == "both" and ((second is None) != (first is None))
                ) or (
                    self.input_passes in {"combined_first", "multiasr"}
                    and ((combined is None) != (first is None))
                )
            ]
            if mismatched:
                raise ValueError(f"入力に使うASR結果の有無が行ごとに異なります: {mismatched[:3]}")

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict:
        row, text = self.rows[index], self.inputs[index]
        if not self.train:
            asr_input: str | FormatterInput = text
            if self.input_passes == "both":
                first, second = self.nohint_hyps[index], self.asr_hyps[index]
                if first is None or second is None:
                    raise ValueError(f"valでASRの両方の結果がありません: {row['id']}")
                asr_input = FormatterInput(first_pass=first, second_pass=second)
            elif self.input_passes == "combined_first":
                first, combined = self.nohint_hyps[index], self.combined_hyps[index]
                if first is None or combined is None:
                    raise ValueError(f"valで1回目と結合文の両方の結果がありません: {row['id']}")
                asr_input = FormatterInput(first_pass=first, combined_text=combined)
            elif self.input_passes == "multiasr":
                first, combined = self.nohint_hyps[index], self.combined_hyps[index]
                if first is None or combined is None:
                    raise ValueError(f"valで1回目と区間結合文の両方の結果がありません: {row['id']}")
                asr_input = FormatterInput(
                    first_pass=first,
                    combined_text=combined,
                    qwen_hypothesis=self.qwen_hyps[index],
                )
            selected = self.selected_glossaries[index]
            glossary = (
                selected
                if self.input_passes == "multiasr" and selected is not None
                else [entry_from_record(entry) for entry in row.get("glossary", [])]
                if self.input_passes != "multiasr" and row.get("glossary_fixed") is True
                else selected
                if selected is not None
                else select_glossary(formatter_input_text(asr_input), self.pool, self.args.max_glossary)
            )
            return tokenize_pair(self.tokenizer, asr_input, glossary, row["target_text"], self.args.max_length)
        sample_seed = int(torch.randint(0, 2**31 - 1, (1,)).item())
        # A/Bで同じsample_seedなら、実効上の介入ではない加工の乱数列を揃える。
        rng = random.Random(sample_seed)
        nohint = (
            self.input_passes == "single"
            and random.Random(sample_seed + 307).random() < self.args.nohint_prob
        )
        if self.input_passes == "both":
            first, second = self.nohint_hyps[index], self.asr_hyps[index]
            if first is not None:
                asr_input = FormatterInput(first_pass=first, second_pass=second)
            elif row.get("spoken_marked"):
                hinted = {g["surface"] for g in row.get("glossary", [])}
                if random.Random(sample_seed + 401).random() < self.args.asr_noise_prob:
                    first_overrides, second_overrides = ({}, {})
                    if row.get("glossary_fixed") is True:
                        first_overrides, second_overrides, _ = plan_two_pass_error_overrides(
                            row["spoken_marked"], row.get("glossary", []), random.Random(sample_seed + 701)
                        )
                    first = simulate_asr_noise(
                        row["spoken_marked"], random.Random(sample_seed + 101), HAAS_NOHINT, hinted,
                        term_overrides=first_overrides,
                    )
                    second = simulate_asr_noise(
                        row["spoken_marked"], random.Random(sample_seed + 211), HAAS_TWOPASS, hinted,
                        term_overrides=second_overrides,
                    )
                else:
                    first = second = text
                asr_input = FormatterInput(first_pass=first, second_pass=second)
            else:
                asr_input = FormatterInput(first_pass=text, second_pass=text)
        elif self.input_passes == "combined_first":
            first, combined = self.nohint_hyps[index], self.combined_hyps[index]
            if first is None and row.get("spoken_marked"):
                hinted = {g["surface"] for g in row.get("glossary", [])}
                if random.Random(sample_seed + 401).random() < self.args.asr_noise_prob:
                    first_overrides, combined_overrides = ({}, {})
                    if row.get("glossary_fixed") is True:
                        first_overrides, combined_overrides, _ = plan_two_pass_error_overrides(
                            row["spoken_marked"], row.get("glossary", []), random.Random(sample_seed + 701)
                        )
                    first = simulate_asr_noise(
                        row["spoken_marked"], random.Random(sample_seed + 101), HAAS_NOHINT, hinted,
                        term_overrides=first_overrides,
                    )
                    combined = simulate_asr_noise(
                        row["spoken_marked"], random.Random(sample_seed + 211), HAAS_TWOPASS, hinted,
                        term_overrides=combined_overrides,
                    )
                else:
                    first = combined = text
            elif first is None:
                first = combined = text
            asr_input = FormatterInput(first_pass=first, combined_text=combined)
        elif self.input_passes == "multiasr":
            first, combined, qwen = (
                self.nohint_hyps[index], self.combined_hyps[index], self.qwen_hyps[index]
            )
            if first is None and row.get("spoken_marked"):
                hinted = {g["surface"] for g in row.get("glossary", [])}
                if random.Random(sample_seed + 401).random() < self.args.asr_noise_prob:
                    first_overrides, combined_overrides = ({}, {})
                    if row.get("glossary_fixed") is True:
                        first_overrides, combined_overrides, _ = plan_two_pass_error_overrides(
                            row["spoken_marked"], row.get("glossary", []), random.Random(sample_seed + 701)
                        )
                    first = simulate_asr_noise(
                        row["spoken_marked"], random.Random(sample_seed + 101), HAAS_NOHINT, hinted,
                        term_overrides=first_overrides,
                    )
                    combined = simulate_asr_noise(
                        row["spoken_marked"], random.Random(sample_seed + 211), HAAS_TWOPASS, hinted,
                        term_overrides=combined_overrides,
                    )
                else:
                    first = combined = text
            elif first is None:
                first = combined = text
            asr_input = FormatterInput(
                first_pass=first,
                combined_text=combined,
                qwen_hypothesis=qwen,
            )
        else:
            asr_input = text
            if self.asr_hyps[index] is not None:
                if nohint and self.nohint_hyps[index] is not None:
                    asr_input = self.nohint_hyps[index]
            elif (
                row.get("spoken_marked")
                and random.Random(sample_seed + 401).random() < self.args.asr_noise_prob
            ):
                hinted = {g["surface"] for g in row.get("glossary", [])}
                term_overrides = {}
                if not nohint and row.get("glossary_fixed") is True:
                    _, term_overrides, _ = plan_two_pass_error_overrides(
                        row["spoken_marked"], row.get("glossary", []), random.Random(sample_seed + 701)
                    )
                asr_input = simulate_asr_noise(
                    row["spoken_marked"],
                    random.Random(sample_seed + (101 if nohint else 211)),
                    HAAS_NOHINT if nohint else HAAS_TWOPASS,
                    hinted,
                    term_overrides=term_overrides,
                )
        if random.Random(sample_seed + 503).random() < self.args.user_punct_prob:
            if isinstance(asr_input, FormatterInput):
                asr_input = FormatterInput(
                    first_pass=(to_user_punctuation(asr_input.first_pass, random.Random(sample_seed + 601))
                                if asr_input.first_pass is not None else None),
                    second_pass=(to_user_punctuation(asr_input.second_pass, random.Random(sample_seed + 602))
                                 if asr_input.second_pass is not None else None),
                    combined_text=(to_user_punctuation(asr_input.combined_text, random.Random(sample_seed + 603))
                                   if asr_input.combined_text is not None else None),
                    qwen_hypothesis=(to_user_punctuation(asr_input.qwen_hypothesis, random.Random(sample_seed + 604))
                                     if asr_input.qwen_hypothesis is not None else None),
                )
            else:
                asr_input = to_user_punctuation(
                    asr_input, random.Random(sample_seed + (601 if nohint else 602))
                )
        # Dでは実ASR行は外部selectorを使い、音声が無い行は合成ASR文から同じselectorで一覧を作る。
        selected = self.selected_glossaries[index]
        if row.get("glossary_fixed") is True and self.input_passes != "multiasr":
            glossary = [entry_from_record(entry) for entry in row.get("glossary", [])]
            return tokenize_pair(self.tokenizer, asr_input, glossary, row["target_text"], self.args.max_length)
        # 正解の用語：その行の用語集のうち、読みが話し言葉に現れる語（言い直しで取り消した部分の語も含む）。
        spoken = row.get("spoken_text_kana", row.get("spoken_text", ""))
        gold = [e for e in map(entry_from_record, row.get("glossary", [])) if any(r in spoken for r in e.readings)]
        retrieved = selected
        if retrieved is None:
            retrieved = select_glossary(formatter_input_text(asr_input), self.pool, self.args.max_glossary)
        glossary = augment_glossary(
            retrieved, gold, self.pool, rng,
            self.args.glossary_drop_prob, self.args.max_distractors, self.args.max_glossary,
        )
        return tokenize_pair(self.tokenizer, asr_input, glossary, row["target_text"], self.args.max_length)


def make_collator(pad_id: int):
    """右詰めでpaddingし、paddingの位置は損失から外すcollatorを作る。"""

    def collate(batch: list[dict]) -> dict:
        length = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), length), pad_id, dtype=torch.long)
        labels = torch.full((len(batch), length), IGNORE_INDEX, dtype=torch.long)
        mask = torch.zeros((len(batch), length), dtype=torch.long)
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            ids[i, :n] = torch.tensor(b["input_ids"])
            labels[i, :n] = torch.tensor(b["labels"])
            mask[i, :n] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": mask}

    return collate


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を読む。"""
    p = argparse.ArgumentParser(description="整形用LLMの教師あり学習")
    p.add_argument("--model", required=True, help="Hugging Faceのrepoかpath")
    p.add_argument(
        "--use-model-loader",
        action="store_true",
        help="Qwen3.5の構成に応じたmodel_loaderを使う",
    )
    p.add_argument("--train", required=True)
    p.add_argument("--val", required=True)
    p.add_argument("--input-field", default="spoken_text", help="入力に使う欄（ASRの出力を入れた欄に差し替えられる）")
    p.add_argument("--train-asr-run", help="学習の入力をASRの推論結果の`hyp`にする")
    p.add_argument("--val-asr-run", help="検証の入力をASRの推論結果の`hyp`にする")
    p.add_argument("--train-asr-run-nohint", help="singleでは確率`--nohint-prob`で使い、bothでは1回目として使うASR結果")
    p.add_argument("--val-asr-run-nohint", help="`both`または`combined_first`で使う検証用の1回目（ヒント無し）のASR結果")
    p.add_argument("--train-asr-run-combined", help="`combined_first`で使う学習用の区間単位の結合文")
    p.add_argument("--val-asr-run-combined", help="`combined_first`で使う検証用の区間単位の結合文")
    p.add_argument("--train-asr-run-qwen", help="`multiasr`で使う学習用Qwen ASR仮説")
    p.add_argument("--val-asr-run-qwen", help="`multiasr`で使う検証用Qwen ASR仮説")
    p.add_argument("--train-glossary-run", help="学習行ごとのselector候補用語一覧(JSONL)")
    p.add_argument("--val-glossary-run", help="検証行ごとのselector用語一覧(JSONL)")
    p.add_argument("--input-passes", choices=["single", "both", "combined_first", "multiasr"], default="single",
                   help="入力形式: 1本文、1回目+2回目、1回目+結合文、または1回目+結合文+Qwen仮説")
    p.add_argument("--nohint-prob", type=float, default=0.0,
                   help="ヒント無しの実出力、またはヒント無し相当の加工を使う確率")
    p.add_argument("--allow-partial-asr", action="store_true",
                   help="`--train-asr-run`に結果が無い行を許し、その行は`--asr-noise-prob`の加工の対象にする")
    p.add_argument("--asr-noise-prob", type=float, default=0.0,
                   help="ASRの実出力が無い学習例の入力を`spoken_marked`からASRに似せて作る確率（残りは`--input-field`の文のまま）")
    p.add_argument("--user-punct-prob", type=float, default=0.0,
                   help="学習例の入力の句読点を本人の声での付き方（文末の句点が多く読点が少ない）へ寄せる確率")
    p.add_argument("--glossary", help="学習で使う用語集全体（held-out-termsを含めない）。省略時はtrainの`glossary`の和集合")
    p.add_argument("--max-glossary", type=int, default=DEFAULT_MAX_ENTRIES)
    p.add_argument("--glossary-drop-prob", type=float, default=0.15, help="正解の用語を用語集から抜く確率")
    p.add_argument("--max-distractors", type=int, default=8, help="混ぜる無関係な語の最大数")
    p.add_argument("--method", choices=["lora", "full"], default="lora")
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument("--lora-target-regex",
                   help="LoRAを付ける層の正規表現。省略時は全ての線形層。画像や音声の部分を持つモデルで文章の部分に限るために使う")
    p.add_argument("--learning-rate", type=float, help="省略時はLoRAで2e-4、全パラメータで1e-5")
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--grad-accum", type=int, default=1)
    p.add_argument("--max-length", type=int, default=1024)
    p.add_argument("--eval-steps", type=int, default=50)
    p.add_argument("--gradient-checkpointing", action="store_true")
    p.add_argument("--resume-from-checkpoint",
                   help="Trainerのcheckpointからoptimizer、scheduler、乱数状態を復元して続行する")
    p.add_argument(
        "--disable-cudnn-sdp",
        action="store_true",
        help="scaled dot product attentionでcuDNN backendを使わない",
    )
    p.add_argument("--dataloader-workers", type=int, default=4, help="学習例を作るworker数（用語集の絞り込みが重いため）")
    p.add_argument("--save-adapter-only", action="store_true",
                   help="LoRAで、統合した重みでなくadapterだけを保存する（持ち帰る量を減らし、手元で統合する）")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def main() -> None:
    """データを読み、学習し、valの損失が最小のcheckpointを統合して保存する。"""
    args = parse_args()
    # cuDNN SDPAが可変長batchで失敗する場合、PyTorchの他のSDPA backendへ切り替える。
    if args.disable_cudnn_sdp:
        torch.backends.cuda.enable_cudnn_sdp(False)
    torch.manual_seed(args.seed)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    train_rows, val_rows = read_jsonl(args.train), read_jsonl(args.val)
    train_input_run = (
        args.train_asr_run_combined
        if args.input_passes in {"combined_first", "multiasr"}
        else args.train_asr_run
    )
    val_input_run = (
        args.val_asr_run_combined
        if args.input_passes in {"combined_first", "multiasr"}
        else args.val_asr_run
    )
    train_inputs = load_inputs(train_rows, args.input_field, train_input_run, args.allow_partial_asr)
    train_asr_hyps = load_optional_hyps(train_rows, args.train_asr_run)
    train_nohint_hyps = load_optional_hyps(train_rows, args.train_asr_run_nohint)
    train_combined_hyps = load_optional_hyps(train_rows, args.train_asr_run_combined)
    train_qwen_hyps = [hyp or None for hyp in load_optional_hyps(train_rows, args.train_asr_run_qwen)]
    train_selected_glossaries = load_optional_glossaries(train_rows, args.train_glossary_run)
    val_inputs = load_inputs(val_rows, args.input_field, val_input_run)
    val_asr_hyps = load_optional_hyps(val_rows, args.val_asr_run)
    val_nohint_hyps = load_optional_hyps(val_rows, args.val_asr_run_nohint)
    val_combined_hyps = load_optional_hyps(val_rows, args.val_asr_run_combined)
    val_qwen_hyps = [hyp or None for hyp in load_optional_hyps(val_rows, args.val_asr_run_qwen)]
    val_selected_glossaries = load_optional_glossaries(val_rows, args.val_glossary_run)
    if args.input_passes == "both":
        if not all((args.train_asr_run, args.train_asr_run_nohint, args.val_asr_run, args.val_asr_run_nohint)):
            raise ValueError("--input-passes bothには学習・検証用の1回目と2回目のASR結果が必要です")
        load_inputs(val_rows, args.input_field, args.val_asr_run_nohint)
    if args.input_passes == "combined_first":
        if not all((
            args.train_asr_run_combined, args.train_asr_run_nohint,
            args.val_asr_run_combined, args.val_asr_run_nohint,
        )):
            raise ValueError("--input-passes combined_firstには学習・検証用の1回目と結合文が必要です")
        load_inputs(val_rows, args.input_field, args.val_asr_run_nohint)
    if args.input_passes == "multiasr":
        if not all((
            args.train_asr_run_nohint, args.train_asr_run_combined,
            args.train_asr_run_qwen, args.val_asr_run_nohint,
            args.val_asr_run_combined, args.val_asr_run_qwen,
            args.train_glossary_run, args.val_glossary_run,
        )):
            raise ValueError(
                "--input-passes multiasrには学習・検証用の1回目、区間結合、Qwen仮説、用語一覧が必要です"
            )
        load_inputs(val_rows, args.input_field, args.val_asr_run_nohint)
        missing_train_support = [
            row["id"] for index, row in enumerate(train_rows)
            if train_nohint_hyps[index] is not None
            and (train_qwen_hyps[index] is None or train_selected_glossaries[index] is None)
        ]
        missing_val_support = [
            row["id"] for index, row in enumerate(val_rows)
            if val_nohint_hyps[index] is None
            or val_qwen_hyps[index] is None
            or val_selected_glossaries[index] is None
        ]
        if missing_train_support or missing_val_support:
            raise ValueError(
                "実ASR行にQwen仮説または選択用語がありません: "
                f"train={len(missing_train_support)} {missing_train_support[:3]}, "
                f"val={len(missing_val_support)} {missing_val_support[:3]}"
            )
    # 学習で混ぜる用語はtrainの用語集（または`--glossary`）から選び、valだけにある用語（held-out-termsなど）を学習の入力に出さない。
    # valでは推論時と同じく、全体の用語集からの絞り込みにするため、valの用語を足した集合を使う。
    pool = load_glossary(args.glossary) if args.glossary else glossary_from_rows(train_rows)
    val_pool = merge_entries(pool + glossary_from_rows(val_rows))
    validate_selected_glossaries(train_rows, train_selected_glossaries, pool, args.max_glossary)
    validate_selected_glossaries(val_rows, val_selected_glossaries, val_pool, args.max_glossary)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    # 全パラメータ学習とbf16が無いGPU（T4）では重みをfp32で持ち、計算だけ自動混合精度にする。
    # bf16の重みを直接更新すると、学習率1e-5程度の小さな更新が丸めで消えるため。LoRAは元の重みを更新しないのでbf16で持つ。
    weights_dtype = torch.bfloat16 if use_bf16 and args.method == "lora" else torch.float32
    model = (
        load_formatter_model(args.model, dtype=weights_dtype)
        if args.use_model_loader
        else AutoModelForCausalLM.from_pretrained(args.model, dtype=weights_dtype)
    )
    if args.gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        if hasattr(model.config, "text_config"):
            model.config.text_config.use_cache = False
    if args.method == "lora":
        from peft import LoraConfig, get_peft_model

        lora = LoraConfig(r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
                          target_modules=args.lora_target_regex or "all-linear", task_type="CAUSAL_LM")
        model = get_peft_model(model, lora)
        if args.gradient_checkpointing:
            model.enable_input_require_grads()
        model.print_trainable_parameters()
    learning_rate = args.learning_rate or (2e-4 if args.method == "lora" else 1e-5)

    train_set = FormatterDataset(train_rows, train_inputs, pool, tokenizer, args, train=True,
                                 asr_hyps=train_asr_hyps, nohint_hyps=train_nohint_hyps,
                                 combined_hyps=train_combined_hyps, qwen_hyps=train_qwen_hyps,
                                 selected_glossaries=train_selected_glossaries)
    val_set = FormatterDataset(val_rows, val_inputs, val_pool, tokenizer, args, train=False,
                               asr_hyps=val_asr_hyps, nohint_hyps=val_nohint_hyps,
                               combined_hyps=val_combined_hyps, qwen_hyps=val_qwen_hyps,
                               selected_glossaries=val_selected_glossaries)
    training_args = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=0.05,  # 1未満の値は全step数に対する割合（transformers 5系）
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.eval_steps,
        save_total_limit=2,
        # Qwen3.5の保存keyはロード時に接頭辞が正規化されるため、Trainerの直接読込を避ける。
        load_best_model_at_end=False,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=use_bf16,
        fp16=torch.cuda.is_available() and not use_bf16,
        seed=args.seed,
        data_seed=args.seed,
        dataloader_num_workers=args.dataloader_workers,
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=train_set, eval_dataset=val_set,
                      data_collator=make_collator(pad_id))
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    best_checkpoint = trainer.state.best_model_checkpoint
    if best_checkpoint is None or not Path(best_checkpoint).is_dir():
        raise RuntimeError("val損失で選ばれたcheckpointが見つかりません")
    # from_pretrainedを通してkey名をモデル形式へ合わせてから、学習済みモデルへ厳密に反映する。
    best_model = (
        load_formatter_model(best_checkpoint, dtype=weights_dtype)
        if args.use_model_loader
        else AutoModelForCausalLM.from_pretrained(best_checkpoint, dtype=weights_dtype)
    )
    trainer.model.load_state_dict(best_model.state_dict(), strict=True)
    del best_model
    best_eval = trainer.evaluate()

    final = trainer.model
    if args.method == "lora" and args.save_adapter_only:
        final.save_pretrained(out / "adapter", safe_serialization=True)
        tokenizer.save_pretrained(out / "adapter")
    else:
        if args.method == "lora":
            final = final.merge_and_unload()
        # 持ち帰る量を半分にするためbf16で保存する（手元ではさらに4bitへ量子化する）。
        final.to(torch.bfloat16).save_pretrained(out / "final", safe_serialization=True)
        tokenizer.save_pretrained(out / "final")
    summary = {
        "args": vars(args),
        "cudnn_sdp_enabled": torch.backends.cuda.cudnn_sdp_enabled(),
        "learning_rate": learning_rate,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "best_eval_loss": best_eval["eval_loss"],
        "log_history": trainer.state.log_history,
    }
    (out / "train_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({k: summary[k] for k in ("best_checkpoint", "best_eval_loss")}, indent=2))


if __name__ == "__main__":
    main()
