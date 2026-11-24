"""faculty上の合成評価2 splitを照合し、今回の集計に必要な項目だけ標準出力へ出す。"""

import hashlib
import json
from collections import Counter
from pathlib import Path


def collect() -> dict:
    """合成manifestと2モデルの保存済み出力を順序付きIDで結ぶ。"""
    base = Path("/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123")
    inputs = Path.home() / "voiceime-work-fr3/inputs"
    manifests = {
        "val": inputs / "manifest-val-no-audio.jsonl",
        "test-novel": inputs / "test-novel-20261122/test-novel.jsonl",
    }
    glossary_runs = {
        "val": inputs / "d-multiasr-20261123/val-runs/formatter-glossary.jsonl",
        "test-novel": Path.home() / "voiceime-work-asr/r3-multiasr-20261122/outputs"
        / "formatter-glossary-qwen06-test-novel.jsonl",
    }
    models = ("D-0.8B-drop0", "D-2B-drop0.075")
    synthetic_sources = {"synthetic-tts", "synthetic-tts-ja", "synthetic-tts-multi"}
    response = {}
    for split, manifest in manifests.items():
        paths = [base / model / "multiasr" / f"{split}-segment-merge.jsonl" for model in models]
        gold, left, right = [
            [json.loads(line) for line in path.read_text().splitlines()]
            for path in (manifest, *paths)
        ]
        glossary_path = glossary_runs[split]
        glossaries = [json.loads(line) for line in glossary_path.read_text().splitlines()]
        glossary_by_id = {row["id"]: row["glossary"] for row in glossaries}
        ids = [row["id"] for row in gold]
        source_counts = Counter(row["source"] for row in gold)
        if source_counts.keys() - synthetic_sources or len(ids) != len(set(ids)):
            raise ValueError(f"{split}: 合成データの条件または一意のIDを確認できません")
        if len(glossaries) != len(ids) or glossary_by_id.keys() != set(ids):
            raise ValueError(f"{split}: 保存済み用語一覧のIDが一致しません")
        rows = []
        for target, a, b in zip(gold, left, right, strict=True):
            if target["id"] != a["id"] or a["id"] != b["id"]:
                raise ValueError(f"{split}: 評価の行が一致しません")
            if any(a[key] != b[key] for key in ("input_text", "glossary", "prompt_token_count")):
                raise ValueError(f"{split}/{a['id']}: 2モデルの入力が一致しません")
            entries = glossary_by_id[a["id"]]
            if [entry["surface"] for entry in entries] != a["glossary"]:
                raise ValueError(f"{split}/{a['id']}: 保存済み用語一覧と一致しません")
            rows.append({
                "id": target["id"], "terms": target["terms"], "target_text": target["target_text"],
                "gold_glossary": [entry for entry in target["glossary"]
                                  if entry["surface"] in target["terms"]],
                "input": a["input_text"], "glossary": a["glossary"],
                "glossary_entries": entries if any(term not in a["hyp"] for term in target["terms"]) else [],
                "drop0": a["hyp"], "2b": b["hyp"],
            })
        response[split] = {
            "source_counts": source_counts,
            "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (manifest, glossary_path, *paths)},
            "rows": rows,
        }
    return response


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, separators=(",", ":")))
