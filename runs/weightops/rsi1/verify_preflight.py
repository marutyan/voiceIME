"""CPUで差し替え・漏えい検査・selector・学習損失の同等性を確認する。"""

import json
import random
import tempfile
from pathlib import Path

import torch
from transformers import (
    Qwen3_5Config, Qwen3_5ForCausalLM, Qwen3_5ForConditionalGeneration,
    Qwen3_5TextConfig, Trainer, TrainingArguments,
)

from prepare_rsi import base_input, blocked_index, has_spaced_asr_term, replacement_pattern, replace_at_matches
from train_support import ProjectedLossTrainer
from voiceime.formatter.glossary import GlossaryIndex, load_glossary, select_glossary
from voiceime.formatter.prompt import FormatterInput, formatter_input_text


def check_spans():
    """Qwenの字間空白と、対象語を含む取り消し済みの別用語で反例を確かめる。"""
    blocked = blocked_index({"zx", "CNCF"})
    assert has_spaced_asr_term("あの Z X を使う", blocked)
    assert has_spaced_asr_term("C N C F の", blocked)
    assert not has_spaced_asr_term("XZX がある", blocked)
    terms = {"Java": ("ジャバ",), "Java EE": ("ジャバイーイー",)}
    p = replacement_pattern("Java", terms["Java"], terms)
    assert replace_at_matches("Java EE、いやJavaを使う", p, "コトリン") == ("Java EE、いやコトリンを使う", 1)
    terms = {"API": ("エーピーアイ",), "AWS API": ("エーダブリューエスエーピーアイ",)}
    p = replacement_pattern("API", terms["API"], terms, qwen=True)
    assert replace_at_matches("A W S A P Iを確認後、A P Iを使う", p, "SDK") == ("A W S A P Iを確認後、SDKを使う", 1)


def check_selector():
    """固定seedで選んだ条件Dの元データから、既存selectorとの一致を確認する。"""
    inputs = Path.home() / "voiceime-work-fr3/inputs"
    pool = load_glossary(inputs / "d-multiasr-20261123/legacy/training-glossary.jsonl")
    indexed = GlossaryIndex(pool)
    rng = random.Random(0)
    train = inputs / "sft3-20261122/train-sft3.jsonl"
    with train.open() as handle:
        picked = set(rng.sample(range(95_934), 128))
        rows = [json.loads(line) for i, line in enumerate(handle) if i in picked]
    for row in rows:
        src = base_input(row, {"first_pass": {}}, indexed, rng)
        text = formatter_input_text(FormatterInput(first_pass=src["first_pass"], combined_text=src["combined_text"]))
        assert indexed.select(text, 20) == select_glossary(text, pool, 20), row["id"]
    return len(rows)


def check_loss():
    """2モデルのクラスで、既存損失との値・全勾配の一致をFP32の小さなモデルで検査する。"""
    torch.manual_seed(0)
    torch.set_num_threads(2)
    args = {
        "vocab_size": 128, "hidden_size": 32, "intermediate_size": 64, "num_hidden_layers": 2,
        "num_attention_heads": 4, "num_key_value_heads": 2, "head_dim": 8,
        "layer_types": ["full_attention", "full_attention"], "pad_token_id": 0,
    }
    models = [
        Qwen3_5ForCausalLM(Qwen3_5TextConfig(**args)),
        Qwen3_5ForConditionalGeneration(Qwen3_5Config(
            text_config=args, vision_config={
                "depth": 1, "hidden_size": 16, "intermediate_size": 32, "num_heads": 2, "out_hidden_size": 32,
            },
        )),
    ]
    prepared = {
        "input_ids": torch.tensor([[1, 2, 3, 4, 5], [6, 7, 8, 0, 0]]),
        "attention_mask": torch.tensor([[1, 1, 1, 1, 1], [1, 1, 1, 0, 0]]),
        "labels": torch.tensor([[-100, -100, 3, 4, 5], [-100, -100, 8, -100, -100]]),
    }
    checked = []
    with tempfile.TemporaryDirectory(dir=Path.home() / "voiceime-work-wops/rsi1") as scratch:
        options = TrainingArguments(output_dir=scratch, use_cpu=True, report_to="none")
        for model in models:
            original = Trainer(model=model, args=options)
            projected = ProjectedLossTrainer(model=model, args=options)
            count = torch.tensor(7)
            stock_loss = original.compute_loss(model, prepared.copy(), num_items_in_batch=count)
            stock_loss.backward()
            stock_gradients = {name: p.grad.clone() for name, p in model.named_parameters() if p.grad is not None}
            model.zero_grad(set_to_none=True)
            work_loss = projected.compute_loss(model, prepared.copy(), num_items_in_batch=count)
            work_loss.backward()
            torch.testing.assert_close(stock_loss, work_loss, rtol=1e-6, atol=1e-6)
            assert stock_gradients.keys() == {name for name, p in model.named_parameters() if p.grad is not None}
            for name, param in model.named_parameters():
                if name in stock_gradients:
                    torch.testing.assert_close(param.grad, stock_gradients[name], rtol=1e-5, atol=2e-6, msg=name)
            checked.append({"model": type(model).__name__, "gradients": len(stock_gradients),
                            "original_loss": stock_loss.item(), "projected_loss": work_loss.item()})
    return checked


if __name__ == "__main__":
    check_spans()
    loss = check_loss()
    print(json.dumps({"span_counterexamples_passed": True, "loss": loss}, ensure_ascii=False), flush=True)
    print(json.dumps({"selector_same_rows": check_selector()}, ensure_ascii=False), flush=True)
