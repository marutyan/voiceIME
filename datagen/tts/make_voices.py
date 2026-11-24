"""声の一覧（voices.json）の説明文から、声ごとの参照音声を作る。

合成音声の話者は、実在の人の録音ではなく、説明文から声を設計するTTS
（Qwen3-TTS VoiceDesign、Apache-2.0）で作った参照音声を複製して用意する。
こうすると参照音声の権利の問題が無く、声の数を説明文の追加だけで増やせる。
synthesize.py はここで作った参照音声と同じ文（REF_TEXT）を使って声を複製する。

ColabのGPU上で実行する。出力先に同じ話者の参照音声があれば作り直さない。
作り直す場合は、該当するWAVを消すか、voices.json の design_seed を変える。

使い方:
    python make_voices.py --voices voices.json --out <出力先>/voices
"""

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

# 参照音声で読ませる文。フィラーと読点を含めて、話し言葉の調子が複製先へ移るようにする。
# synthesize.py が声の複製で同じ文を書き起こしとして渡すため、ここだけで定義する。
REF_TEXT = "えっと、今日はですね、先週の実験の結果について少しお話しします。思ったより精度が上がっていて、正直ちょっと驚きました。"

DESIGN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"


def load_voices(path: Path) -> list[dict]:
    """voices.json を読み、話者IDの重複が無いことを確かめて返す。"""
    voices = json.loads(path.read_text())
    ids = [v["speaker"] for v in voices]
    if len(ids) != len(set(ids)):
        raise ValueError(f"voices.json に重複した話者IDがある: {path}")
    return voices


def design_reference(model, voice: dict) -> tuple[np.ndarray, int]:
    """説明文から声を設計し、REF_TEXT を読んだ参照音声を1本返す。"""
    import torch

    torch.manual_seed(int(voice.get("design_seed", 0)))
    wavs, sr = model.generate_voice_design(text=REF_TEXT, language="Japanese", instruct=voice["description_en"])
    return wavs[0], sr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="参照音声を置くディレクトリ")
    args = parser.parse_args()

    voices = load_voices(args.voices)
    args.out.mkdir(parents=True, exist_ok=True)
    pending = [v for v in voices if not (args.out / f"{v['speaker']}.wav").exists()]
    print(f"参照音声: 全{len(voices)}件、作成{len(pending)}件")
    if not pending:
        return

    import torch
    from qwen_tts import Qwen3TTSModel

    model = Qwen3TTSModel.from_pretrained(DESIGN_MODEL, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
    for v in pending:
        wav, sr = design_reference(model, v)
        # 途中で止まっても壊れたWAVが残らないよう、一時ファイルへ書いてから名前を変える。
        tmp = args.out / f"{v['speaker']}.tmp.wav"
        sf.write(tmp, np.asarray(wav, dtype=np.float32), sr)
        tmp.rename(args.out / f"{v['speaker']}.wav")
        print(f"{v['speaker']}: {len(wav) / sr:.1f}秒", flush=True)


if __name__ == "__main__":
    main()
