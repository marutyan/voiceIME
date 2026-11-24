"""Haas-ja-v1.0（Third Intelligence）をMLXで動かす方式と、公式の`.nemo`からの重みの変換。

Haas-ja-v1.0はParakeet-TDTと同じFastConformerのencoder、TDTのjoint、greedyの復号を使い、
予測ネットワーク（直前のtokenを要約する部分）だけをLSTMからKimi Delta Attention（KDA）に替えている。
そこでencoder、joint、復号はparakeet-mlxをそのまま使い、予測ネットワークだけをここでMLXに書いた。
KDAの計算は、公式が使うflash-linear-attention 0.5.2の`KimiDeltaAttention`（1 tokenずつ進める
`fused_recurrent_kda`の経路）と、公式の`haas_asr.prednet`の構成に合わせている。

変換（手元のMac、作業ツリーで）：
    uv run python -m voiceime.asr.haas_backend convert \
        <Haas-ja-v1.0.nemoのpath> /Users/marutyan/PrivateDev/voiceIME/models/asr/haas-ja-v1.0-mlx
"""

from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
import time
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import numpy as np
import sentencepiece as spm
import yaml
from mlx.utils import tree_flatten
from parakeet_mlx import DecodingConfig
from parakeet_mlx.utils import from_config

from voiceime.asr.base import Term, Transcription

# l2正規化の分母に足す値。flash-linear-attentionの`fused_recurrent_kda`の値に合わせる。
L2NORM_EPS = 1e-6

# NeMoの`AudioToMelSpectrogramPreprocessor`の既定値のうち、Haasの設定に書かれていないもの。
# parakeet-mlxの前処理は窓の置き方、端の埋め方、振幅の計算、対数の下限、標準偏差の分母がNeMoと異なり、
# 公式の出力と一致しなかったため、NeMoと同じ計算をここで行う。
PREEMPH = 0.97
LOG_ZERO_GUARD = 2.0**-24
NORM_EPS = 1e-5
PAD_TO = 16


class ShortConvolution(nn.Module):
    """KDAのq、k、vにかける、チャネルごとの因果的な畳み込み（幅`kernel_size`）とSiLU。

    重みはPyTorchの`Conv1d(groups=dim)`と同じ(dim, 1, kernel_size)の形で持つ。
    """

    def __init__(self, dim: int, kernel_size: int) -> None:
        super().__init__()
        self.weight = mx.zeros((dim, 1, kernel_size))

    def __call__(self, x: mx.array, history: mx.array) -> tuple[mx.array, mx.array]:
        """1 token分の入力`x`（B, dim）と直前の入力の履歴（B, dim, kernel_size-1）から出力と新しい履歴を返す。"""
        window = mx.concatenate([history, x[:, :, None]], axis=2)
        out = nn.silu((window * self.weight[:, 0, :]).sum(axis=-1))
        return out, window[:, :, 1:]


class KimiDeltaAttention(nn.Module):
    """KDAの1層。1 tokenずつ、状態（B, heads, head_dim, head_dim）を更新しながら出力を返す。"""

    def __init__(self, hidden_size: int, num_heads: int, head_dim: int, conv_size: int, norm_eps: float) -> None:
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = head_dim
        self.norm_eps = norm_eps
        dim = num_heads * head_dim
        self.q_proj = nn.Linear(hidden_size, dim, bias=False)
        self.k_proj = nn.Linear(hidden_size, dim, bias=False)
        self.v_proj = nn.Linear(hidden_size, dim, bias=False)
        self.q_conv1d = ShortConvolution(dim, conv_size)
        self.k_conv1d = ShortConvolution(dim, conv_size)
        self.v_conv1d = ShortConvolution(dim, conv_size)
        self.f_proj = [nn.Linear(hidden_size, head_dim, bias=False), nn.Linear(head_dim, dim, bias=False)]
        self.b_proj = nn.Linear(hidden_size, num_heads, bias=False)
        self.A_log = mx.zeros((num_heads,))
        self.dt_bias = mx.zeros((dim,))
        self.g_proj = [nn.Linear(hidden_size, head_dim, bias=False), nn.Linear(head_dim, dim, bias=True)]
        self.o_norm = nn.RMSNorm(head_dim, eps=norm_eps)
        self.o_proj = nn.Linear(dim, hidden_size, bias=False)

    def step(self, x: mx.array, state: tuple[mx.array, mx.array]) -> tuple[mx.array, tuple[mx.array, mx.array]]:
        """入力`x`（B, hidden）と状態（記憶 B,H,K,V と畳み込みの履歴 3,B,dim,conv-1）から出力と新しい状態を返す。"""
        memory, conv_history = state
        batch = x.shape[0]
        heads, k_dim = self.num_heads, self.head_dim
        q, q_hist = self.q_conv1d(self.q_proj(x), conv_history[0])
        k, k_hist = self.k_conv1d(self.k_proj(x), conv_history[1])
        v, v_hist = self.v_conv1d(self.v_proj(x), conv_history[2])

        # 以降は、flash-linear-attentionの計算と同じくfloat32で行う。shape: (B, H, K)
        q = q.astype(mx.float32).reshape(batch, heads, k_dim)
        k = k.astype(mx.float32).reshape(batch, heads, k_dim)
        v = v.astype(mx.float32).reshape(batch, heads, k_dim)
        q = q / mx.sqrt((q * q).sum(axis=-1, keepdims=True) + L2NORM_EPS) * (k_dim**-0.5)
        k = k / mx.sqrt((k * k).sum(axis=-1, keepdims=True) + L2NORM_EPS)
        # 忘却の度合い（対数）：-exp(A_log) * softplus(f + dt_bias)。shape: (B, H, K)
        f = (self.f_proj[1](self.f_proj[0](x)).astype(mx.float32) + self.dt_bias).reshape(batch, heads, k_dim)
        log_decay = -mx.exp(self.A_log.astype(mx.float32))[None, :, None] * nn.softplus(f)
        beta = mx.sigmoid(self.b_proj(x).astype(mx.float32))  # shape: (B, H)

        # delta rule：記憶を減衰させ、kで読んだ値とvの差だけを書き込み、qで読み出す。memory shape: (B, H, K, V)
        memory = memory * mx.exp(log_decay)[..., None]
        delta = (v - (memory * k[..., None]).sum(axis=-2)) * beta[..., None]
        memory = memory + k[..., None] * delta[..., None, :]
        out = (memory * q[..., None]).sum(axis=-2)  # shape: (B, H, V)

        gate = self.g_proj[1](self.g_proj[0](x)).astype(mx.float32).reshape(batch, heads, k_dim)
        out = self.o_norm(out) * mx.sigmoid(gate)
        out = self.o_proj(out.reshape(batch, heads * k_dim))
        return out, (memory, mx.stack([q_hist, k_hist, v_hist]))


class KDAStack(nn.Module):
    """KDAの層を、事前の正規化つきの残差接続で積み、最後に正規化する（公式の`KDAPredictionNetwork`と同じ構成）。"""

    def __init__(self, hidden_size: int, num_layers: int, prednet: dict, norm_eps: float = 1e-5) -> None:
        super().__init__()
        self.layers = [
            KimiDeltaAttention(
                hidden_size, prednet["kda_num_heads"], prednet["kda_head_dim"], prednet["kda_conv_size"], norm_eps
            )
            for _ in range(num_layers)
        ]
        self.norms = [nn.LayerNorm(hidden_size, eps=norm_eps) for _ in range(num_layers)]
        self.final_norm = nn.LayerNorm(hidden_size, eps=norm_eps) if prednet["kda_final_norm"] else None


class KDAPredictNetwork(nn.Module):
    """parakeet-mlxの`PredictNetwork`と同じ呼び出し方で使える、KDAの予測ネットワーク。

    状態はparakeet-mlxの復号が`(hidden, cell)`として受け渡す2つの配列に収める：
    1つ目に各層の記憶（L, B, H, K, V）、2つ目に各層の畳み込みの履歴（L, 3, B, dim, conv-1）を入れる。
    """

    def __init__(self, vocab_size: int, prednet: dict) -> None:
        super().__init__()
        hidden = prednet["pred_hidden"]
        self.pred_hidden = hidden
        self.num_layers = prednet["pred_rnn_layers"]
        self.num_heads = prednet["kda_num_heads"]
        self.head_dim = prednet["kda_head_dim"]
        self.conv_size = prednet["kda_conv_size"]
        # blankを詰め物として使うため、語彙より1つ多い埋め込みを持つ（blankの行は0）。
        self.prediction = {
            "embed": nn.Embedding(vocab_size + 1, hidden),
            "dec_rnn": KDAStack(hidden, self.num_layers, prednet),
        }

    def initial_state(self, batch: int) -> tuple[mx.array, mx.array]:
        """発話の始めの状態（すべて0）を返す。"""
        dim = self.num_heads * self.head_dim
        memory = mx.zeros((self.num_layers, batch, self.num_heads, self.head_dim, self.head_dim), dtype=mx.float32)
        conv = mx.zeros((self.num_layers, 3, batch, dim, self.conv_size - 1))
        return memory, conv

    def __call__(
        self, y: mx.array | None, state: tuple[mx.array, mx.array] | None = None
    ) -> tuple[mx.array, tuple[mx.array, mx.array]]:
        """直前のtoken（B, 1）か、発話の始めならNoneを受け取り、予測ネットワークの出力（B, 1, hidden）と状態を返す。"""
        batch = 1 if y is None else y.shape[0]
        if state is None:
            state = self.initial_state(batch)
        # 発話の始めは、NeMoと同じく0のベクトルを入力にする。
        x = self.prediction["embed"](y)[:, 0, :] if y is not None else mx.zeros((batch, self.pred_hidden))
        stack = self.prediction["dec_rnn"]
        memories, convs = [], []
        for i, (layer, norm) in enumerate(zip(stack.layers, stack.norms)):
            out, (memory, conv) = layer.step(norm(x), (state[0][i], state[1][i]))
            x = x + out
            memories.append(memory)
            convs.append(conv)
        if stack.final_norm is not None:
            x = stack.final_norm(x)
        return x[:, None, :], (mx.stack(memories), mx.stack(convs))


def parakeet_config_from_nemo(nemo_config: dict) -> dict:
    """NeMoの設定をparakeet-mlxの`from_config`が受け付ける形に直す。

    parakeet-mlxはモデルの種類を`target`と`model_defaults.tdt_durations`で判定し、前処理の`dither`と`pad_to`を必須とする。
    `dither`と`pad_to`はHaasの設定に書かれていないため、NeMoの既定値（1e-5、16）を入れる。
    """
    config = json.loads(json.dumps(nemo_config))
    config["target"] = "nemo.collections.asr.models.rnnt_bpe_models.EncDecRNNTBPEModel"
    config["model_defaults"]["tdt_durations"] = config["decoding"]["durations"]
    config["preprocessor"].setdefault("dither", 1e-5)
    config["preprocessor"].setdefault("pad_to", 16)
    return config


def build_model(config: dict) -> nn.Module:
    """parakeet-mlxのTDTモデルを作り、予測ネットワークをKDAへ差し替える（重みは未読み込み、float32）。"""
    model = from_config(parakeet_config_from_nemo(config))
    model.decoder = KDAPredictNetwork(config["decoder"]["vocab_size"], config["decoder"]["prednet"])
    return model


def nemo_log_mel(audio: np.ndarray, filterbank: np.ndarray, window: np.ndarray, n_fft: int, hop: int) -> tuple[np.ndarray, int]:
    """NeMoの前処理と同じlog-melを作る。返り値は(フレーム数をPAD_TOの倍数へ埋めた(T, n_mels)の配列, 有効なフレーム数)。

    手順：高域強調、両端をn_fft/2の0で埋めたSTFT（長さwinの窓を中央に置く）、パワー、melへの射影、
    log(x + 2^-24)、有効なフレームでの特徴量ごとの正規化（標準偏差はn-1で割り1e-5を足す）、埋めたフレームは0。
    """
    x = audio.astype(np.float64)
    x = np.concatenate([x[:1], x[1:] - PREEMPH * x[:-1]])
    padded_window = np.zeros(n_fft)
    left = (n_fft - len(window)) // 2
    padded_window[left : left + len(window)] = window
    x = np.pad(x, (n_fft // 2, n_fft // 2))
    n_frames = 1 + len(audio) // hop
    # shape: (フレーム数, n_fft)
    frames = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop][:n_frames] * padded_window
    spectrum = np.fft.rfft(frames, axis=-1)
    power = spectrum.real**2 + spectrum.imag**2
    log_mel = np.log(power @ filterbank.T.astype(np.float64) + LOG_ZERO_GUARD)  # shape: (フレーム数, n_mels)
    mean = log_mel.mean(axis=0)
    std = np.sqrt(((log_mel - mean) ** 2).sum(axis=0) / max(n_frames - 1, 1)) + NORM_EPS
    log_mel = (log_mel - mean) / std
    total = -(-n_frames // PAD_TO) * PAD_TO
    log_mel = np.pad(log_mel, ((0, total - n_frames), (0, 0)))
    return log_mel.astype(np.float32), n_frames


def convert_nemo_weights(state_dict: dict) -> dict[str, mx.array]:
    """NeMoの重みを、名前と値の型はそのままに、畳み込みの軸の順だけMLXへ合わせて変換する。"""
    converted = {}
    for key, tensor in state_dict.items():
        # 前処理の窓とmelの係数は、モデルの重みとは別のファイル（frontend.safetensors）に置く。
        if key.endswith("num_batches_tracked") or key.startswith("preprocessor."):
            continue
        value = tensor.float().numpy()
        # encoderの畳み込み：PyTorchは(出力, 入力, 幅[, 高さ])、MLXは(出力, 幅[, 高さ], 入力)の順。
        # KDAの短い畳み込みは`ShortConvolution`がPyTorchの形のまま使う。
        if key.startswith("encoder.") and value.ndim == 3:
            value = value.transpose(0, 2, 1)
        elif key.startswith("encoder.") and value.ndim == 4:
            value = value.transpose(0, 2, 3, 1)
        # numpyにbfloat16が無いためfloat32を経由し、元の型へ戻す（値は変わらない）。
        dtype = mx.bfloat16 if str(tensor.dtype) == "torch.bfloat16" else mx.float32
        converted[key] = mx.array(value).astype(dtype)
    return converted


def convert(nemo_path: Path, out_dir: Path) -> None:
    """`.nemo`を展開し、`config.json`、`model.safetensors`、`frontend.safetensors`、`tokenizer.model`を書き出す。"""
    import torch

    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(nemo_path) as archive:
        archive.extractall(tmp, filter="data")
        root = Path(tmp)
        config = yaml.safe_load((root / "model_config.yaml").read_text())
        state_dict = torch.load(root / "model_weights.ckpt", map_location="cpu", weights_only=True)
        tokenizer = next(root.glob("*tokenizer.model"))
        (out_dir / "tokenizer.model").write_bytes(tokenizer.read_bytes())

    weights = convert_nemo_weights(state_dict)
    model = build_model(config)
    expected = dict(tree_flatten(model.parameters()))
    missing = sorted(set(expected) - set(weights))
    unexpected = sorted(set(weights) - set(expected))
    if missing or unexpected:
        raise ValueError(f"重みの名前が合わない：不足{missing[:8]}、余分{unexpected[:8]}")
    mismatched = [k for k in expected if expected[k].shape != weights[k].shape]
    if mismatched:
        raise ValueError(f"重みの形が合わない：{[(k, expected[k].shape, weights[k].shape) for k in mismatched[:5]]}")
    mx.save_safetensors(str(out_dir / "model.safetensors"), weights)
    # NeMoと同じ前処理に使う、学習時の窓（長さ400）とmelの係数（n_mels, n_fft/2+1）。
    frontend = {
        "window": mx.array(state_dict["preprocessor.featurizer.window"].float().numpy()),
        "filterbank": mx.array(state_dict["preprocessor.featurizer.fb"].float().numpy()[0]),
    }
    mx.save_safetensors(str(out_dir / "frontend.safetensors"), frontend)
    (out_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")


class HaasTranscriber:
    """変換済みのHaas-ja-v1.0を読み、parakeet-mlxのgreedyのTDT復号で書き起こす。用語集のヒントは使わない。"""

    def __init__(self, model_dir: str, dtype: mx.Dtype = mx.bfloat16) -> None:
        root = Path(model_dir)
        config = json.loads((root / "config.json").read_text())
        self.model = build_model(config)
        self.model.load_weights(str(root / "model.safetensors"), strict=True)
        # encoderとjointは指定の型で動かし、予測ネットワーク（約4M parameter）は記憶の精度を保つためfloat32のままにする。
        self.model.set_dtype(dtype)
        self.model.decoder.set_dtype(mx.float32)
        self.model.eval()
        self.dtype = dtype
        self.tokenizer = spm.SentencePieceProcessor(model_file=str(root / "tokenizer.model"))
        self.config = DecodingConfig()
        frontend = mx.load(str(root / "frontend.safetensors"))
        self.window = np.array(frontend["window"])
        self.filterbank = np.array(frontend["filterbank"])
        preprocessor = config["preprocessor"]
        self.n_fft = preprocessor["n_fft"]
        self.hop = int(preprocessor["window_stride"] * preprocessor["sample_rate"])

    def transcribe(self, audio: np.ndarray, glossary: list[Term] | None = None) -> Transcription:
        """log-mel、encoder、復号の時間を分けて測りながら書き起こす。"""
        start = time.perf_counter()
        log_mel, n_frames = nemo_log_mel(audio, self.filterbank, self.window, self.n_fft, self.hop)
        mel = mx.array(log_mel, dtype=self.dtype)[None]  # shape: (1, 埋めたフレーム数, n_mels)
        mx.eval(mel)
        mel_end = time.perf_counter()

        # 有効なフレーム数を渡し、埋めたフレームをattentionから除く（NeMoと同じ）。shape: (1, フレーム数/8, d_model)
        features, lengths = self.model.encoder(mel, mx.array([n_frames]))
        mx.eval(features, lengths)
        encoder_end = time.perf_counter()

        # parakeet-mlxの復号は予測ネットワークの状態を特徴量の型へ変換するため、float32で渡して記憶の丸めを防ぐ。
        hypotheses, _ = self.model.decode(features.astype(mx.float32), lengths, config=self.config)
        # 語彙に無い文字はbyteのtokenで表すため、parakeet-mlxの文字列化ではなくSentencePieceで文字へ戻す。
        text = self.tokenizer.decode([token.id for token in hypotheses[0]])
        decoder_end = time.perf_counter()
        return Transcription(
            text=text,
            details={
                "logmel_s": mel_end - start,
                "encoder_s": encoder_end - mel_end,
                "decoder_s": decoder_end - encoder_end,
                "n_tokens": float(len(hypotheses[0])),
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Haas-ja-v1.0の`.nemo`をMLXの形式へ変換する")
    sub = parser.add_subparsers(dest="command", required=True)
    conv = sub.add_parser("convert")
    conv.add_argument("nemo_path", type=Path)
    conv.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    convert(args.nemo_path, args.out_dir)
    print(f"{args.out_dir}へ保存した")


if __name__ == "__main__":
    main()
