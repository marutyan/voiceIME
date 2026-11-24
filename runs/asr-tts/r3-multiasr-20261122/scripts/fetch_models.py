#!/usr/bin/env python3
"""facultyの実験用cacheへ公式ASR checkpointを取得し、revisionを記録する。"""

from __future__ import annotations

import json
import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path.home() / "voiceime-work-asr/r3-multiasr-20261122"
QWEN_CACHE = (
    Path.home()
    / "voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/cache/huggingface/hub"
)


def resolve_cached(repo_id: str, cache_dir: Path) -> dict[str, str]:
    """既存または新規snapshotの実体パスとrevisionを返す。"""
    path = Path(
        snapshot_download(
            repo_id=repo_id,
            cache_dir=str(cache_dir),
            local_files_only=True,
        )
    )
    return {"repo_id": repo_id, "revision": path.name, "path": str(path)}


def download(repo_id: str, cache_dir: Path) -> dict[str, str]:
    """公式Hubのmainを取得し、解決したcommit hashを記録する。"""
    path = Path(snapshot_download(repo_id=repo_id, cache_dir=str(cache_dir)))
    return {"repo_id": repo_id, "revision": path.name, "path": str(path)}


def main() -> None:
    """3つの公式モデルsnapshotを解決し、実行に使うmetadataを保存する。"""
    model_cache = ROOT / "models/hf-cache"
    model_cache.mkdir(parents=True, exist_ok=True)
    models = {
        "qwen3-asr-0.6b": resolve_cached("Qwen/Qwen3-ASR-0.6B", QWEN_CACHE),
        "qwen3-asr-1.7b": download("Qwen/Qwen3-ASR-1.7B", model_cache),
        "whisper-large-v3-turbo": download(
            "openai/whisper-large-v3-turbo", model_cache
        ),
    }
    metadata = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "qwen_asr_source_commit": "7c6daf77a2421100f5fb066495372c00129d39ff",
        "environment_versions": {
            package: importlib.metadata.version(package)
            for package in (
                "qwen-asr",
                "torch",
                "transformers",
                "huggingface-hub",
                "accelerate",
                "soundfile",
                "safetensors",
            )
        },
        "models": models,
    }
    destination = ROOT / "models/models.json"
    destination.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name, model in models.items():
        print(f"{name}: revision={model['revision']} path={model['path']}", flush=True)


if __name__ == "__main__":
    main()
