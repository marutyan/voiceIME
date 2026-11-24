"""本人のscripted 50件をヒントあり・なしの評価用JSONLへ整える。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

import soundfile as sf


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONLを読み、各行がobjectであることを確認する。"""
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSON objectが必要です")
            rows.append(value)
    return rows


def unique_surfaces(entries: list[dict[str, Any]]) -> list[str]:
    """glossaryから空欄を除き、元の順序を保ってsurfaceを重複除去する。"""
    return list(
        dict.fromkeys(
            entry["surface"]
            for entry in entries
            if isinstance(entry.get("surface"), str) and entry["surface"]
        )
    )


def check_audio(path: Path) -> int:
    """音声全体を読み切り、16 kHz WAVとして使えることを確認する。"""
    with sf.SoundFile(path, mode="r") as audio:
        if audio.format not in {"WAV", "WAVEX"} or audio.samplerate != 16_000:
            raise ValueError(f"16 kHz WAVではありません: {audio.format}/{audio.samplerate}")
        frames_read = 0
        while True:
            block = audio.read(65_536, dtype="float32", always_2d=True)
            if block.shape[0] == 0:
                break
            frames_read += block.shape[0]
        if frames_read != audio.frames:
            raise ValueError(f"音声の末尾まで読めません: {frames_read}/{audio.frames}")
        return path.stat().st_size


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """親directoryを作り、UTF-8のJSONLを保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")


def remote_audio_path(
    row: dict[str, Any], manifest_path: Path, remote_audio_root: PurePosixPath
) -> str:
    """manifest相対音声pathを確認し、facultyのaudio directoryへ写す。"""
    relative = PurePosixPath(row["audio_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"音声pathはmanifest相対pathが必要です: {row['id']}")
    local_path = manifest_path.parent.joinpath(*relative.parts)
    if not local_path.is_file():
        raise FileNotFoundError(f"{row['id']}: {local_path}")
    return str(remote_audio_root.joinpath(*relative.parts[1:]))


def main() -> None:
    """scripted 50件と評価manifestを作り、ヒントからunseen語を除く。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--unseen-terms", required=True, type=Path)
    parser.add_argument("--remote-audio-root", required=True, type=PurePosixPath)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-rows", type=int, default=50)
    args = parser.parse_args()

    rows = [
        row
        for row in read_jsonl(args.manifest)
        if row.get("prompt_kind") == "scripted"
    ]
    if len(rows) != args.expected_rows:
        raise ValueError(f"scripted行数が想定と異なります: {len(rows)}")
    unseen_terms = {
        line.strip()
        for line in args.unseen_terms.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not unseen_terms:
        raise ValueError("unseen termsが空です")

    nohint_inputs = []
    hint_inputs = []
    manifest_rows = []
    unseen_manifest_rows = []
    audio_bytes = 0
    unseen_occurrences = 0
    hinted_surfaces = 0

    for row in rows:
        audio_path = remote_audio_path(
            row, args.manifest, args.remote_audio_root
        )
        audio_bytes += check_audio(
            args.manifest.parent.joinpath(*PurePosixPath(row["audio_path"]).parts)
        )
        surfaces = unique_surfaces(row.get("glossary", []))
        visible_surfaces = [surface for surface in surfaces if surface not in unseen_terms]
        hinted_surfaces += len(visible_surfaces)
        unseen_occurrences += sum(
            term in unseen_terms for term in row.get("terms", [])
        )
        base_input = {"id": row["id"], "audio": audio_path}
        nohint_inputs.append({**base_input, "prompt": ""})
        hint_inputs.append({**base_input, "prompt": ", ".join(visible_surfaces)})

        full_manifest_row = {
            "id": row["id"],
            "audio_path": audio_path,
            "target_text": row["target_text"],
            "fillers": row["fillers"],
            "terms": row.get("terms", []),
            "glossary": row.get("glossary", []),
            "tags": row.get("tags", []),
        }
        unseen_manifest_rows.append(
            {
                **full_manifest_row,
                "terms": [term for term in row.get("terms", []) if term in unseen_terms],
                "glossary": [
                    entry
                    for entry in row.get("glossary", [])
                    if entry.get("surface") in unseen_terms
                ],
            }
        )
        manifest_rows.append(full_manifest_row)

    if unseen_occurrences == 0:
        raise ValueError("scripted正解にunseen termsがありません")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "devuser50-nohint.jsonl", nohint_inputs)
    write_jsonl(args.output_dir / "devuser50-hints.jsonl", hint_inputs)
    write_jsonl(args.output_dir / "devuser50-manifest.jsonl", manifest_rows)
    write_jsonl(
        args.output_dir / "devuser50-unseen-manifest.jsonl",
        unseen_manifest_rows,
    )
    print(
        json.dumps(
            {
                "rows": len(rows),
                "unseen_terms": len(unseen_terms),
                "unseen_target_occurrences": unseen_occurrences,
                "unseen_terms_removed_from_hints": True,
                "visible_hint_surfaces": hinted_surfaces,
                "audio_bytes": audio_bytes,
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
