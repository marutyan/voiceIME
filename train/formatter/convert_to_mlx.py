"""学習後のHugging Face形式の重みを、手元の推論用にMLXの4bit（group size 64）へ変換する。

手元のMacで、作業ツリーの直下から実行する。
    uv run python train/formatter/convert_to_mlx.py <HF形式の重みのdirかrepo> <出力dir>

transformersで文章部分だけを学習して保存すると、`model_type`が文章部分用の名前（例：`qwen3_5_text`）になり、
mlx-lmが読めない。その場合は設定ファイルだけを書き換えた一時dirを作って変換する（重みは変えない）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from mlx_lm import convert

# transformersの文章部分だけの`model_type`と、同じ重みを読めるmlx-lmの`model_type`の対応。
# mlx-lmの`qwen3_5`は`text_config`が無い設定を文章部分の設定として読む。
TEXT_ONLY_MODEL_TYPES = {"qwen3_5_text": "qwen3_5"}


def prepare_source(hf_path: str, tmp: Path) -> str:
    """変換元のpathを返す。`model_type`の書き換えが要る場合だけ、設定を直したリンクの集まりを`tmp`に作る。"""
    src = Path(hf_path)
    if not src.is_dir():
        return hf_path  # Hugging Faceのrepoはそのまま渡す
    config = json.loads((src / "config.json").read_text())
    if config.get("model_type") not in TEXT_ONLY_MODEL_TYPES:
        return hf_path
    for f in src.iterdir():
        if f.name != "config.json":
            (tmp / f.name).symlink_to(f.resolve())
    config["model_type"] = TEXT_ONLY_MODEL_TYPES[config["model_type"]]
    (tmp / "config.json").write_text(json.dumps(config, indent=2))
    return str(tmp)


def main() -> None:
    """引数を読み、必要なら設定を直してから4bitで変換する。出力先が既にあれば上書きせず止める。"""
    parser = argparse.ArgumentParser(description="HF形式の重みをMLXの4bitへ変換する")
    parser.add_argument("hf_path")
    parser.add_argument("mlx_path")
    args = parser.parse_args()
    if Path(args.mlx_path).exists():
        sys.exit(f"出力先が既にあります（上書きしません）: {args.mlx_path}")
    with tempfile.TemporaryDirectory() as tmp:
        source = prepare_source(args.hf_path, Path(tmp))
        convert(hf_path=source, mlx_path=args.mlx_path, quantize=True, q_bits=4, q_group_size=64)
    print(f"変換しました: {args.mlx_path}")


if __name__ == "__main__":
    main()
