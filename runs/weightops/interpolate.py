"""条件Dの0.8B親モデルをCPUで補間し、評価用の最終重みを保存する。"""

import argparse
import shutil
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file


def interpolate(drop0: Path, drop0075: Path, alpha: float, output: Path) -> None:
    """同じキーと形の全浮動小数点テンソルを補間し、元のdtypeで保存する。"""
    assets = ("config.json", "generation_config.json", "tokenizer_config.json",
              "tokenizer.json", "chat_template.jinja")
    for asset in assets:
        if (drop0 / asset).read_bytes() != (drop0075 / asset).read_bytes():
            raise ValueError(f"親モデルの設定またはtokenizerに差があります: {asset}")

    torch.set_num_threads(2)
    tensors = {}
    floating = 0
    with (
        safe_open(drop0 / "model.safetensors", framework="pt", device="cpu") as left,
        safe_open(drop0075 / "model.safetensors", framework="pt", device="cpu") as right,
    ):
        if left.keys() != right.keys() or left.metadata() != right.metadata():
            raise ValueError("親モデルのテンソルキーまたはメタデータが一致しません")
        metadata = left.metadata()
        for name in left.keys():
            a, b = left.get_tensor(name), right.get_tensor(name)
            if a.shape != b.shape or a.dtype != b.dtype:
                raise ValueError(f"親モデルのテンソル形状またはdtypeが異なります: {name}")
            if a.is_floating_point():
                # BF16などで積を丸めず、補間結果だけを保存時のdtypeに戻す。
                compute_dtype = torch.promote_types(a.dtype, torch.float32)
                blended = (1.0 - alpha) * a.to(compute_dtype) + alpha * b.to(compute_dtype)
                tensors[name] = blended.to(a.dtype)
                floating += 1
            else:
                tensors[name] = a

    output.mkdir(parents=True, exist_ok=False)
    for asset in assets:
        shutil.copyfile(drop0 / asset, output / asset)
    save_file(tensors, output / "model.safetensors", metadata=metadata)
    print(f"{output}: alpha={alpha}, floating={floating}, other={len(tensors) - floating}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drop0", type=Path)
    parser.add_argument("drop0075", type=Path)
    parser.add_argument("alpha", type=float, choices=(0.25, 0.5, 0.75))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    interpolate(args.drop0, args.drop0075, args.alpha, args.output)
