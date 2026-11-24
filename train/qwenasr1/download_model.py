"""公式Qwen3-ASR-0.6Bを指定したHugging Face cacheへ取得する。"""

from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> None:
    """取得したsnapshot pathを実験directoryへ記録する。"""
    experiment_root = Path(__file__).resolve().parents[1]
    snapshot_path = snapshot_download("Qwen/Qwen3-ASR-0.6B")
    (experiment_root / "base-model.path").write_text(
        f"{snapshot_path}\n", encoding="utf-8"
    )
    print(snapshot_path, flush=True)


if __name__ == "__main__":
    main()
