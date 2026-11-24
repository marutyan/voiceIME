"""Transformersで整形モデルを一括推論し、`voiceime.eval.report`用のJSONLを作る。"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import torch
import transformers
from transformers.generation.logits_process import LogitsProcessor, LogitsProcessorList

from voiceime.formatter.glossary import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_MIN_SCORE,
    GlossaryEntry,
    entry_from_record,
    load_glossary,
    select_glossary,
)
from voiceime.formatter.prompt import (
    FormatterInput,
    formatter_input_text,
    formatter_output_reference_text,
    needs_special_tokens,
    render_prompt,
)
from voiceime.formatter.style import apply_output_style
from model_loader import load_formatter_model

MIN_MAX_TOKENS = 64
MAX_TOKENS_PER_INPUT_TOKEN = 1.5
THINK_PATTERN = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)


@dataclass
class EvaluationJob:
    """1種類のASR入力、manifest、用語集除外条件をまとめる。"""

    name: str
    manifest: Path
    asr_run: Path | None
    excluded_terms: Path | None
    first_pass_run: Path | None = None
    combined_run: Path | None = None
    qwen_run: Path | None = None


@dataclass
class PreparedJob:
    """推論に必要なprompt、語彙、ASR遅延を準備した評価一式。"""

    name: str
    items: list[dict[str, Any]]
    glossary_size: int
    excluded_count: int


class PerRowLengthCap(LogitsProcessor):
    """各入力に対応する出力上限で行ごとにEOSを出し、長い行の終了を待たせない。"""

    def __init__(self, prompt_width: int, limits: list[int], eos_token_id: int):
        self.prompt_width = prompt_width
        self.limits = torch.tensor(limits, dtype=torch.long, device="cuda")
        self.eos_token_id = eos_token_id

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        generated = input_ids.shape[1] - self.prompt_width
        stop_rows = self.limits <= generated
        scores[stop_rows] = -torch.inf
        scores[stop_rows, self.eos_token_id] = 0
        return scores


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、行番号とともに構文エラーを知らせる。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: JSONを読めません") from error
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(row)
    return rows


def read_excluded_terms(path: Path | None) -> set[str]:
    """1行1語の一覧を読み、表記が完全一致する用語を除く。"""
    if path is None:
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def read_glossary_lists(sources: list[tuple[str, Path]]) -> dict[str, dict[str, list[str | dict[str, Any]]]]:
    """評価jobごとに、既存runでモデルへ渡した用語の順序と読みを読み込む。"""
    glossary_by_job: dict[str, dict[str, list[str | dict[str, Any]]]] = {}
    for job_name, path in sources:
        glossary_by_id = glossary_by_job.setdefault(job_name, {})
        for line_number, row in enumerate(read_jsonl(path), start=1):
            sample_id = row.get("id")
            glossary = row.get("glossary")
            if (
                not isinstance(sample_id, str)
                or not isinstance(glossary, list)
                or not all(
                    isinstance(entry, str)
                    or (
                        isinstance(entry, dict)
                        and isinstance(entry.get("surface"), str)
                        and isinstance(entry.get("readings", []), list)
                        and all(isinstance(reading, str) for reading in entry.get("readings", []))
                    )
                    for entry in glossary
                )
            ):
                raise ValueError(f"{path}:{line_number}: idと用語文字列または用語objectの配列が必要です")
            previous = glossary_by_id.get(sample_id)
            if previous is not None and previous != glossary:
                raise ValueError(f"{job_name}/{sample_id}: 複数runのglossary一覧が一致しません")
            glossary_by_id[sample_id] = glossary
    return glossary_by_job


def prepare_job(
    job: EvaluationJob,
    tokenizer: Any,
    full_glossary: list[GlossaryEntry],
    max_glossary: int,
    min_score: float,
    glossary_lists_by_id: dict[str, list[str | dict[str, Any]]] | None = None,
) -> PreparedJob:
    """manifestとASR runをidで結び、既定または保存済みの用語一覧でpromptを作る。"""
    manifest_rows = read_jsonl(job.manifest)
    manifest_ids = [row.get("id") for row in manifest_rows]
    if any(not isinstance(sample_id, str) for sample_id in manifest_ids):
        raise ValueError(f"{job.manifest}: idがありません")
    if len(set(manifest_ids)) != len(manifest_ids):
        raise ValueError(f"{job.manifest}: idが重複しています")

    if job.asr_run is not None and job.combined_run is not None:
        raise ValueError("2回目のASR runと結合文runは同時に指定できません")
    if job.asr_run is None and job.first_pass_run is None and job.combined_run is None:
        raise ValueError("評価jobにはASR runを1つ以上指定してください")

    asr_runs: dict[str, dict[str, dict[str, Any]] | None] = {}
    for name, path in (
        ("first", job.first_pass_run),
        ("second", job.asr_run),
        ("combined", job.combined_run),
        ("qwen", job.qwen_run),
    ):
        if path is None:
            asr_runs[name] = None
            continue
        asr_by_id: dict[str, dict[str, Any]] = {}
        for row in read_jsonl(path):
            sample_id = row.get("id")
            if not isinstance(sample_id, str):
                continue
            if sample_id in asr_by_id:
                raise ValueError(f"{path}: idが重複しています: {sample_id}")
            asr_by_id[sample_id] = row
        missing_ids = [sample_id for sample_id in manifest_ids if sample_id not in asr_by_id]
        if missing_ids:
            raise ValueError(f"{path}: manifestの入力が{len(missing_ids)}件ありません")
        asr_runs[name] = asr_by_id

    excluded = read_excluded_terms(job.excluded_terms)
    candidates = [entry for entry in full_glossary if entry.surface not in excluded]
    entries_by_surface = {entry.surface: entry for entry in candidates}
    items = []
    for index, row in enumerate(manifest_rows):
        sample_id = row["id"]
        first = asr_runs["first"][sample_id] if asr_runs["first"] is not None else None
        second = asr_runs["second"][sample_id] if asr_runs["second"] is not None else None
        combined = asr_runs["combined"][sample_id] if asr_runs["combined"] is not None else None
        qwen = asr_runs["qwen"][sample_id] if asr_runs["qwen"] is not None else None
        for source, source_row in (("1回目", first), ("2回目", second), ("結合文", combined), ("Qwen", qwen)):
            if source_row is not None and not isinstance(source_row.get("hyp"), str):
                raise ValueError(f"{sample_id} の{source}にhypがありません")
        if first is not None and second is not None:
            text: str | FormatterInput = FormatterInput(
                first_pass=first["hyp"], second_pass=second["hyp"],
                qwen_hypothesis=(qwen["hyp"] or None) if qwen is not None else None,
            )
        elif first is not None and combined is not None:
            text = FormatterInput(
                first_pass=first["hyp"], combined_text=combined["hyp"],
                qwen_hypothesis=(qwen["hyp"] or None) if qwen is not None else None,
            )
        elif first is not None:
            text = FormatterInput(first_pass=first["hyp"])
        elif combined is not None:
            text = FormatterInput(combined_text=combined["hyp"])
        else:
            text = second["hyp"]
        latency_row = second or combined or qwen or first
        assert latency_row is not None
        raw_input_text = formatter_input_text(text)
        if glossary_lists_by_id is None:
            glossary = select_glossary(raw_input_text, candidates, max_glossary, min_score)
        else:
            listed_entries = glossary_lists_by_id.get(sample_id)
            if listed_entries is None:
                raise ValueError(f"保存済み用語一覧にidがありません: {sample_id}")
            if len(listed_entries) > max_glossary:
                raise ValueError(f"{sample_id}: 保存済み用語一覧が上限{max_glossary}件を超えています")
            glossary = []
            missing_surfaces = []
            for listed in listed_entries:
                entry = entries_by_surface.get(listed) if isinstance(listed, str) else entry_from_record(listed)
                if entry is None or entry.surface not in entries_by_surface:
                    missing_surfaces.append(listed if isinstance(listed, str) else listed["surface"])
                else:
                    glossary.append(entry)
            if missing_surfaces:
                raise ValueError(
                    f"{sample_id}: 保存済み一覧に評価用語集で使えない表記が{len(missing_surfaces)}件あります"
                )
        prompt = render_prompt(tokenizer, text, glossary)
        prompt_ids = tokenizer.encode(
            prompt, add_special_tokens=needs_special_tokens(tokenizer, prompt)
        )
        input_token_count = len(tokenizer.encode(raw_input_text, add_special_tokens=False))
        output_reference_tokens = len(
            tokenizer.encode(formatter_output_reference_text(text), add_special_tokens=False)
        )
        asr_latency = latency_row.get("latency_s", 0.0)
        if not isinstance(asr_latency, (int, float)) or isinstance(asr_latency, bool):
            asr_latency = 0.0
        items.append(
            {
                "index": index,
                "id": sample_id,
                "text": text,
                "input_token_count": input_token_count,
                "output_reference_token_count": output_reference_tokens,
                "prompt_token_count": len(prompt_ids),
                "asr_latency_s": float(asr_latency),
                "glossary": glossary,
                "prompt_ids": prompt_ids,
                "max_new_tokens": max(
                    MIN_MAX_TOKENS, int(output_reference_tokens * MAX_TOKENS_PER_INPUT_TOKEN)
                ),
            }
        )
    return PreparedJob(job.name, items, len(candidates), len(full_glossary) - len(candidates))


def parse_args() -> argparse.Namespace:
    """一度のモデル読み込みで複数の比較条件を受け取る。"""
    parser = argparse.ArgumentParser(description="整形モデルをTransformersで一括評価します")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument(
        "--use-model-loader",
        action="store_true",
        help="Qwen3.5の構成に応じたmodel_loaderを使う",
    )
    parser.add_argument("--glossary", required=True, nargs="+", type=Path)
    parser.add_argument(
        "--glossary-run",
        action="append",
        nargs=2,
        metavar=("JOB_NAME", "RUN_JSONL"),
        default=None,
        help="指定jobのidごとに固定するglossary配列を持つ既存run JSONL",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--job",
        action="append",
        nargs=4,
        metavar=("NAME", "MANIFEST", "ASR_RUN", "EXCLUDE_TERMS"),
        help="1件の評価条件。除外語ファイルが無い場合は`-`を指定",
    )
    parser.add_argument(
        "--job-both",
        action="append",
        nargs=5,
        metavar=("NAME", "MANIFEST", "FIRST_ASR_RUN", "SECOND_ASR_RUN", "EXCLUDE_TERMS"),
        help="1回目と2回目のASR結果を使う評価条件",
    )
    parser.add_argument(
        "--job-combined-first",
        action="append",
        nargs=5,
        metavar=("NAME", "MANIFEST", "FIRST_ASR_RUN", "COMBINED_RUN", "EXCLUDE_TERMS"),
        help="1回目と区間ごとの結合文を使う評価条件",
    )
    parser.add_argument(
        "--job-multiasr",
        action="append",
        nargs=6,
        metavar=("NAME", "MANIFEST", "FIRST_ASR_RUN", "COMBINED_RUN", "QWEN_RUN", "EXCLUDE_TERMS"),
        help="1回目、区間結合文、任意のQwen ASR仮説を使う評価条件。QWEN_RUNが無い場合は`-`",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-glossary", type=int, default=DEFAULT_MAX_ENTRIES)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    args = parser.parse_args()
    if not (args.job or args.job_both or args.job_combined_first or args.job_multiasr):
        parser.error("jobを1件以上指定してください")
    if args.batch_size < 1 or args.max_glossary < 1:
        parser.error("batch-sizeとmax-glossaryは1以上にしてください")
    all_specs = [
        *(args.job or []), *(args.job_both or []),
        *(args.job_combined_first or []), *(args.job_multiasr or []),
    ]
    if any(Path(spec[0]).name != spec[0] for spec in all_specs):
        parser.error("job名にpathを指定できません")
    available_jobs = {spec[0] for spec in all_specs}
    unknown_glossary_jobs = {
        name for name, _ in (args.glossary_run or []) if name not in available_jobs
    }
    if unknown_glossary_jobs:
        parser.error("glossary-runのjob名が評価jobにありません")
    return args


def run_job(
    job: PreparedJob,
    model: Any,
    tokenizer: Any,
    args: argparse.Namespace,
    eos_ids: list[int],
    pad_token_id: int,
) -> dict[str, Any]:
    """長さが近いpromptをbatch化し、1条件分の結果と処理量を保存する。"""
    out_path = args.out_dir / f"{job.name}.jsonl"
    summary_path = out_path.with_suffix(".summary.json")
    if out_path.exists() or summary_path.exists():
        raise FileExistsError(f"出力先が既にあります: {out_path}")

    ordered_items = sorted(job.items, key=lambda item: len(item["prompt_ids"]))
    outputs: dict[int, dict[str, Any]] = {}
    total_generation_s = 0.0
    total_generation_tokens = 0
    batch_count = 0
    forced_lengths = 0

    for start in range(0, len(ordered_items), args.batch_size):
        batch = ordered_items[start : start + args.batch_size]
        encoded = tokenizer.pad(
            {"input_ids": [item["prompt_ids"] for item in batch]},
            padding=True,
            return_tensors="pt",
        )
        prompt_width = encoded["input_ids"].shape[1]
        limits = [item["max_new_tokens"] for item in batch]
        max_new_tokens = max(limits) + 1
        length_cap_eos_id = tokenizer.eos_token_id or eos_ids[0]
        stopper = PerRowLengthCap(prompt_width, limits, length_cap_eos_id)

        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            sequences = model.generate(
                input_ids=encoded["input_ids"].to("cuda"),
                attention_mask=encoded["attention_mask"].to("cuda"),
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=1.0,
                top_k=50,
                top_p=1.0,
                num_beams=1,
                use_cache=True,
                eos_token_id=eos_ids,
                pad_token_id=pad_token_id,
                logits_processor=LogitsProcessorList([stopper]),
            )
        torch.cuda.synchronize()
        batch_seconds = time.perf_counter() - started
        total_generation_s += batch_seconds
        batch_count += 1
        generated_batch = sequences[:, prompt_width:].tolist()
        amortized_s = batch_seconds / len(batch)

        for item, token_ids in zip(batch, generated_batch, strict=True):
            eos_position = next(
                (position for position, token_id in enumerate(token_ids) if token_id in eos_ids),
                None,
            )
            visible_ids = token_ids if eos_position is None else token_ids[:eos_position]
            hypothesis = tokenizer.decode(visible_ids, skip_special_tokens=True)
            hypothesis = apply_output_style(THINK_PATTERN.sub("", hypothesis).strip())
            hit_length_limit = eos_position is None or eos_position >= item["max_new_tokens"]
            forced_lengths += int(hit_length_limit)
            total_generation_tokens += len(visible_ids)
            row = {
                "id": item["id"],
                "system": job.name,
                "stage": "e2e",
                "hyp": hypothesis,
                "latency_s": item["asr_latency_s"] + amortized_s,
                "format_latency_s": amortized_s,
                "input_text": asdict(item["text"]) if isinstance(item["text"], FormatterInput) else item["text"],
                "input_token_count": item["input_token_count"],
                "output_reference_token_count": item["output_reference_token_count"],
                "prompt_token_count": item["prompt_token_count"],
                "glossary": [entry.surface for entry in item["glossary"]],
                "generation_tokens": len(visible_ids),
                "finish_reason": "length" if hit_length_limit else "eos",
                "batch_size": len(batch),
                "batch_elapsed_s": batch_seconds,
                "latency_kind": "amortized_batch_throughput",
            }
            outputs[item["index"]] = row

        print(
            f"{job.name}: {min(start + len(batch), len(ordered_items))}/{len(ordered_items)} "
            f"items, batch={batch_seconds:.2f}s",
            flush=True,
        )

    records = [outputs[index] for index in range(len(job.items))]
    temporary_path = out_path.with_suffix(".jsonl.partial")
    with temporary_path.open("x", encoding="utf-8") as target:
        for record in records:
            target.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary_path.replace(out_path)

    summary = {
        "system": job.name,
        "model": str(args.model),
        "runtime": "Transformers",
        "runtime_dtype": "bfloat16",
        "decoding": "greedy",
        "max_new_tokens_rule": "max(64, floor(output_reference_tokens * 1.5))",
        "repetition_stop": "not applied during batched inference",
        "n": len(records),
        "glossary_size": job.glossary_size,
        "excluded_term_count": job.excluded_count,
        "mean_glossary_entries": statistics.mean(len(row["glossary"]) for row in records),
        "mean_input_tokens": statistics.mean(row["input_token_count"] for row in records),
        "mean_output_reference_tokens": statistics.mean(
            row["output_reference_token_count"] for row in records
        ),
        "mean_prompt_tokens": statistics.mean(row["prompt_token_count"] for row in records),
        "batch_size": args.batch_size,
        "batches": batch_count,
        "generation_wall_s": total_generation_s,
        "generation_tokens": total_generation_tokens,
        "generation_tokens_per_second": total_generation_tokens / total_generation_s,
        "format_latency_mean_s_amortized": total_generation_s / len(records),
        "length_limited": forced_lengths,
        "max_memory_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
        "latency_note": "latency_sはbatch wall timeを件数で割ったthroughput換算値で、単発遅延ではない",
    }
    temporary_summary = summary_path.with_suffix(".json.partial")
    temporary_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_summary.replace(summary_path)
    return summary


def main() -> None:
    """モデルをbf16で一度読み込み、指定した全条件を一括推論する。"""
    args = parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDAが使えません。CUDA_VISIBLE_DEVICESを確認してください")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if any(args.out_dir.iterdir()):
        raise FileExistsError(f"出力dirが空ではありません: {args.out_dir}")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    wall_started = time.perf_counter()
    load_started = time.perf_counter()
    tokenizer = transformers.AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    if args.use_model_loader:
        model = load_formatter_model(
            args.model, dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")
    else:
        model = transformers.AutoModelForCausalLM.from_pretrained(
            args.model, dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")
    model.eval()
    model.config.use_cache = True
    if hasattr(model.config, "text_config"):
        model.config.text_config.use_cache = True
    model_load_s = time.perf_counter() - load_started
    torch.cuda.reset_peak_memory_stats()

    # Qwenの学習ラベルはtokenizerのEOSで終わるため、generation configと異なる場合も両方で停止する。
    eos_ids: list[int] = []
    for eos_value in (tokenizer.eos_token_id, model.generation_config.eos_token_id):
        if eos_value is None:
            continue
        values = [eos_value] if isinstance(eos_value, int) else list(eos_value)
        for token_id in values:
            if int(token_id) not in eos_ids:
                eos_ids.append(int(token_id))
    if not eos_ids:
        raise ValueError("EOS token idが設定されていません")
    pad_token_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_ids[0]
    full_glossary = load_glossary(*args.glossary)
    glossary_lists_by_job = (
        read_glossary_lists(
            [(job_name, Path(run_path)) for job_name, run_path in args.glossary_run]
        )
        if args.glossary_run
        else {}
    )

    jobs = []
    for name, manifest, asr_run, excluded_terms in args.job or []:
        jobs.append(
            prepare_job(
                EvaluationJob(
                    name,
                    Path(manifest),
                    Path(asr_run),
                    None if excluded_terms == "-" else Path(excluded_terms),
                ),
                tokenizer,
                full_glossary,
                args.max_glossary,
                args.min_score,
                glossary_lists_by_job.get(name),
            )
        )
    for name, manifest, first_run, second_run, excluded_terms in args.job_both or []:
        jobs.append(
            prepare_job(
                EvaluationJob(
                    name,
                    Path(manifest),
                    Path(second_run),
                    None if excluded_terms == "-" else Path(excluded_terms),
                    first_pass_run=Path(first_run),
                ),
                tokenizer,
                full_glossary,
                args.max_glossary,
                args.min_score,
                glossary_lists_by_job.get(name),
            )
        )
    for name, manifest, first_run, combined_run, excluded_terms in args.job_combined_first or []:
        jobs.append(
            prepare_job(
                EvaluationJob(
                    name,
                    Path(manifest),
                    None,
                    None if excluded_terms == "-" else Path(excluded_terms),
                    first_pass_run=Path(first_run),
                    combined_run=Path(combined_run),
                ),
                tokenizer,
                full_glossary,
                args.max_glossary,
                args.min_score,
                glossary_lists_by_job.get(name),
            )
        )
    for name, manifest, first_run, combined_run, qwen_run, excluded_terms in args.job_multiasr or []:
        jobs.append(
            prepare_job(
                EvaluationJob(
                    name,
                    Path(manifest),
                    None,
                    None if excluded_terms == "-" else Path(excluded_terms),
                    first_pass_run=Path(first_run),
                    combined_run=Path(combined_run),
                    qwen_run=None if qwen_run == "-" else Path(qwen_run),
                ),
                tokenizer,
                full_glossary,
                args.max_glossary,
                args.min_score,
                glossary_lists_by_job.get(name),
            )
        )

    summaries = [run_job(job, model, tokenizer, args, eos_ids, pad_token_id) for job in jobs]
    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    wall_seconds = time.perf_counter() - wall_started
    runner_summary = {
        "model": str(args.model),
        "runtime": "Transformers",
        "runtime_dtype": "bfloat16",
        "decoding": "greedy",
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "gpu": torch.cuda.get_device_name(0),
        "batch_size": args.batch_size,
        "max_glossary": args.max_glossary,
        "min_score": args.min_score,
        "jobs": [summary["system"] for summary in summaries],
        "samples": sum(summary["n"] for summary in summaries),
        "model_load_s": model_load_s,
        "generation_wall_s": sum(summary["generation_wall_s"] for summary in summaries),
        "wall_seconds": wall_seconds,
        "started_at": started_at,
        "finished_at": finished_at,
        "max_memory_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
        "latency_note": "batch推論のwall timeを件数で割ったthroughput換算。単発遅延やMLX 4bitとの直接比較には使わない",
        "repetition_stop_note": "MLXの逐次生成で使う反復による途中停止は、batch推論では適用していない",
        "results": summaries,
    }
    summary_path = args.out_dir / "transformers-bf16-summary.json"
    summary_path.write_text(json.dumps(runner_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(runner_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
