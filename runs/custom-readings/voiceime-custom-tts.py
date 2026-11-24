"""既存のTTSを同じ話者・エンジンで再生し、読むテキストだけを差し替える。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "voiceime-work-tts/datagen/tts"))
import synthesize as tts

# 話速・抑揚は元IDから得る。話者とエンジンは元manifestの実際の割当を優先する。
original_plan = tts.plan_row


def planned(row: dict, voices: list[dict], seed: int) -> dict:
    """元の発話と同じ話者とTTSに、新しい読みの文を渡す。"""
    original_id = row["custom"]["source_id"]
    plan = original_plan({**row, "id": original_id}, voices, seed)
    engine = {"synthetic-tts-ja": "ja", "synthetic-tts-multi": "multi"}[row["source"]]
    voice, = (v for v in voices if v["speaker"] == row["speaker"])
    intonation = tts.JA_INTONATION[int(tts.unit_hash(seed, "intonation", original_id) * len(tts.JA_INTONATION))]
    return {**plan, "engine": engine, "voice": voice, "text": row[tts.TEXT_FIELD[engine]],
            "intonation": intonation if engine == "ja" else None}


if __name__ == "__main__":
    # モデル名で渡すと、tokenizerがオフラインでもHubのモデル情報を問い合わせる版がある。
    hub = Path.home() / "voiceime-work-tts/cache/huggingface/hub"
    tts.TTS_MODEL["multi"] = str(
        hub / "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base/snapshots"
        / "fd4b254389122332181a7c3db7f27e918eec64e3"
    )
    tts.plan_row = planned
    tts.main()
