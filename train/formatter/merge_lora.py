"""Colabで学習したLoRAのadapterを、手元で元の重みへ統合してHugging Face形式で保存する。

統合した重みをColabから持ち帰ると大きい（Gemma 4 E2Bで約10GB）ため、adapterだけを持ち帰り手元で統合する。
torchなどは学習のときと同じ版を一時的な環境に入れて使う（手元のMacで、作業ツリーの直下から実行する）:
    uv run --with torch==2.15.0 --with transformers==5.23.0 --with peft==0.22.0 --with accelerate \\
        python train/formatter/merge_lora.py --base google/gemma-4-E2B-it --adapter <adapter dir> --out <hf dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    """元の重みをbf16でCPUへ読み込み、adapterを統合して保存する。"""
    parser = argparse.ArgumentParser(description="LoRAのadapterを元の重みへ統合する")
    parser.add_argument("--base", required=True, help="学習に使った元のモデル（Hugging Faceのrepoかpath）")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if Path(args.out).exists():
        sys.exit(f"出力先が既にあります（上書きしません）: {args.out}")
    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    model.save_pretrained(args.out, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.adapter).save_pretrained(args.out)
    print(f"統合しました: {args.out}")


if __name__ == "__main__":
    main()
