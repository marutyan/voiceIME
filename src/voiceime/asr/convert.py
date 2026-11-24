"""Whisper系の重みをmlx-whisperで読める形式へ変換し、必要なら量子化する。

- `hf`：Hugging Face transformers形式のWhisper（kotoba-whisperなど）をMLX形式のfp16へ変換する。
- `quantize`：MLX形式のWhisperを、線形層と埋め込み層だけ指定のbit数へ量子化する。

変換の対応表はmlx-examplesの`whisper/convert.py`と同じ規則に従う。

実行例（手元のMac、作業ツリーで）：
    uv run python -m voiceime.asr.convert hf kotoba-tech/kotoba-whisper-v2.2 \
        /Users/marutyan/PrivateDev/voiceIME/models/asr/kotoba-whisper-v2.2
    uv run python -m voiceime.asr.convert quantize mlx-community/whisper-large-v3-turbo \
        /Users/marutyan/PrivateDev/voiceIME/models/asr/whisper-large-v3-turbo-q4 --bits 4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
from huggingface_hub import snapshot_download
from mlx.utils import tree_flatten, tree_unflatten
from mlx_whisper.load_models import load_model
from mlx_whisper.whisper import ModelDimensions, Whisper

# transformersの重みの名前を、mlx-whisperの名前へ置き換える規則。上から順に適用する。
HF_TO_MLX_RENAMES = [
    ("model.", ""),
    (".layers", ".blocks"),
    (".self_attn", ".attn"),
    (".attn_layer_norm", ".attn_ln"),
    (".encoder_attn.", ".cross_attn."),
    (".encoder_attn_layer_norm", ".cross_attn_ln"),
    (".final_layer_norm", ".mlp_ln"),
    (".q_proj", ".query"),
    (".k_proj", ".key"),
    (".v_proj", ".value"),
    (".out_proj", ".out"),
    (".fc1", ".mlp1"),
    (".fc2", ".mlp2"),
    ("embed_positions.weight", "positional_embedding"),
    ("decoder.embed_tokens", "decoder.token_embedding"),
    ("encoder.layer_norm", "encoder.ln_post"),
    ("decoder.layer_norm", "decoder.ln"),
]

# 量子化で1組の倍率を共有する重みの数。mlx-examplesとmlx-communityの既定値に合わせる。
QUANT_GROUP_SIZE = 64


def hf_config_to_dims(config: dict) -> ModelDimensions:
    """transformersの`config.json`から、mlx-whisperのモデルの寸法を作る。"""
    return ModelDimensions(
        n_mels=config["num_mel_bins"],
        n_audio_ctx=config["max_source_positions"],
        n_audio_state=config["d_model"],
        n_audio_head=config["encoder_attention_heads"],
        n_audio_layer=config["encoder_layers"],
        n_vocab=config["vocab_size"],
        n_text_ctx=config["max_target_positions"],
        n_text_state=config["d_model"],
        n_text_head=config["decoder_attention_heads"],
        n_text_layer=config["decoder_layers"],
    )


def rename_hf_key(key: str) -> str:
    """transformersの重みの名前1つを、mlx-whisperの名前へ置き換える。"""
    for old, new in HF_TO_MLX_RENAMES:
        key = key.replace(old, new)
    return key


def convert_hf_weights(weights: dict[str, mx.array]) -> dict[str, mx.array]:
    """transformersの重みを、名前と畳み込みの軸の順をmlx-whisperへ合わせたfp16の重みへ変える。"""
    converted = {}
    for key, value in weights.items():
        # 出力層はtoken埋め込みと重みを共有し、encoderの位置埋め込みはmlx-whisperが正弦波で作るため持たない。
        if key == "proj_out.weight" or key == "model.encoder.embed_positions.weight":
            continue
        new_key = rename_hf_key(key)
        # 畳み込みの重みはtransformersが(出力, 入力, 幅)、MLXが(出力, 幅, 入力)の順。
        if "conv" in new_key and value.ndim == 3:
            value = value.swapaxes(1, 2)
        converted[new_key] = value.astype(mx.float16)
    return converted


def save_mlx_whisper(model: Whisper, dims: ModelDimensions, out_dir: Path, quantization: dict | None) -> None:
    """mlx-whisperの`load_model`が読める形（`config.json`と`weights.safetensors`）で保存する。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    config = {**dims.__dict__, "model_type": "whisper"}
    if quantization is not None:
        config["quantization"] = quantization
    (out_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    mx.save_safetensors(str(out_dir / "weights.safetensors"), dict(tree_flatten(model.parameters())))


def convert_from_hf(repo: str, out_dir: Path) -> None:
    """Hugging Faceのtransformers形式のWhisperを取得し、MLX形式のfp16で保存する。"""
    src = Path(snapshot_download(repo, allow_patterns=["config.json", "model.safetensors"]))
    config = json.loads((src / "config.json").read_text())
    dims = hf_config_to_dims(config)
    weights = convert_hf_weights(mx.load(str(src / "model.safetensors")))

    model = Whisper(dims, mx.float16)
    # `alignment_heads`は単語のタイムスタンプ用の設定で、transformersの重みに無いためmlx-whisperの既定値のままにする。
    expected = {k: v for k, v in tree_flatten(model.parameters()) if k != "alignment_heads"}
    missing = sorted(set(expected) - set(weights))
    unexpected = sorted(set(weights) - set(expected))
    if missing or unexpected:
        raise ValueError(f"重みの名前が合わない：不足{missing[:5]}、余分{unexpected[:5]}")
    mismatched = [k for k in expected if expected[k].shape != weights[k].shape]
    if mismatched:
        raise ValueError(f"重みの形が合わない：{mismatched[:5]}")
    model.update(tree_unflatten(list(weights.items())))
    mx.eval(model.parameters())
    save_mlx_whisper(model, dims, out_dir, quantization=None)


def quantize(src: str, out_dir: Path, bits: int) -> None:
    """MLX形式のWhisper（directoryかrepo）を読み、線形層と埋め込み層を`bits`bitへ量子化して保存する。"""
    model = load_model(src, mx.float16)
    nn.quantize(model, group_size=QUANT_GROUP_SIZE, bits=bits)
    mx.eval(model.parameters())
    save_mlx_whisper(model, model.dims, out_dir, quantization={"group_size": QUANT_GROUP_SIZE, "bits": bits})


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper系の重みをMLX形式へ変換、量子化する")
    sub = parser.add_subparsers(dest="command", required=True)
    hf = sub.add_parser("hf", help="transformers形式からMLX形式のfp16へ変換する")
    hf.add_argument("repo")
    hf.add_argument("out_dir", type=Path)
    q = sub.add_parser("quantize", help="MLX形式のWhisperを量子化する")
    q.add_argument("src")
    q.add_argument("out_dir", type=Path)
    q.add_argument("--bits", type=int, required=True, choices=[4, 8])
    args = parser.parse_args()
    if args.command == "hf":
        convert_from_hf(args.repo, args.out_dir)
    else:
        quantize(args.src, args.out_dir, args.bits)
    print(f"{args.out_dir}へ保存した")


if __name__ == "__main__":
    main()
