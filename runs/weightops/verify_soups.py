"""facultyで補間テンソルと条件Dの評価結果を照合し、集計値だけを書き出す。"""

import json
from collections import Counter
from pathlib import Path

import torch
import transformers
from safetensors import safe_open


def verify_weights(parents: list[Path], model: Path, alpha: float) -> dict:
    """全テンソルの形と型を照合し、各テンソル内の等間隔の値を独立に再計算する。"""
    counts = Counter()
    sampled_values = 0
    with (
        safe_open(parents[0] / "model.safetensors", framework="pt", device="cpu") as left,
        safe_open(parents[1] / "model.safetensors", framework="pt", device="cpu") as right,
        safe_open(model / "model.safetensors", framework="pt", device="cpu") as saved,
    ):
        if not (saved.keys() == left.keys() == right.keys()):
            raise ValueError(f"{model}: テンソルのキーが一致しません")
        for key in saved.keys():
            a, b, c = (file.get_tensor(key) for file in (left, right, saved))
            if not (a.shape == b.shape == c.shape and a.dtype == b.dtype == c.dtype):
                raise ValueError(f"{model}/{key}: 形状またはdtypeが一致しません")
            counts[str(c.dtype)] += 1
            if not c.numel():
                continue
            indices = torch.linspace(0, c.numel() - 1, steps=min(16, c.numel()),
                                     dtype=torch.float64).long()
            start, end, value = (tensor.flatten()[indices] for tensor in (a, b, c))
            expected = start
            if a.is_floating_point():
                expected = torch.lerp(start.double(), end.double(), alpha).to(c.dtype)
            if not torch.equal(expected, value):
                raise ValueError(f"{model}/{key}: 保存値が補間値と一致しません")
            sampled_values += indices.numel()
    return {"tensors_by_dtype": dict(counts), "verified_values": sampled_values,
            "weight_bytes": (model / "model.safetensors").stat().st_size}


def verify_split(out: Path, baseline: Path, split: str, audit: dict) -> dict:
    """行別入力と用語一覧を親の評価と照合し、既存reportの指標を取り出す。"""
    run = f"{split}-segment-merge"
    name = f"{run}.jsonl"
    items, parents = [
        [json.loads(line) for line in path.read_text().splitlines()]
        for path in (out / "multiasr" / name, baseline / "multiasr" / name)
    ]
    keys = ("id", "input_text", "glossary", "prompt_token_count")
    for row, parent in zip(items, parents, strict=True):
        if any(row[k] != parent[k] for k in keys):
            raise ValueError(f"{out}/{split}/{row['id']}: 親の評価入力と一致しません")
    report = (out / "reports" / f"{split}.report.txt").read_text().split("```json\n")[1]
    result, = json.loads(report.partition("\n```")[0])["results"]
    summary = json.loads((out / "multiasr" / f"{run}.summary.json").read_text())
    if (audit["terms"], audit["correct"]) != (result["terms"]["total"], result["terms"]["correct"]):
        raise ValueError(f"{out}/{split}: 用語集計値が一致しません")
    if len(items) != audit["rows"] or len(items) != summary["n"]:
        raise ValueError(f"{out}/{split}: 行数が一致しません")
    return {"audit": audit, "cer": result["cer"], "evaluation": summary}


def verify() -> dict:
    """重み3条件の検証、評価、キューの最終記録をまとめる。"""
    home = Path.home()
    work = home / "voiceime-work-wops"
    fr3 = home / "voiceime-work-fr3"
    baseline = Path("/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123/D-0.8B-drop0")
    parents = [fr3 / "outputs" / f"formatter-sft3-d-0.8b-{drop}-restart1/final"
               for drop in ("drop0", "drop0075")]
    queue = home / "voiceime-queue"
    history = (queue / "history.log").read_text().splitlines()
    runs = {}
    for suffix, alpha in (("025", 0.25), ("050", 0.5), ("075", 0.75)):
        tag = f"soup-a{suffix}"
        job = f"70-wops-{tag}"
        model = work / "outputs" / tag
        out = work / "runs" / tag
        audit = json.loads((out / "audit.json").read_text())
        queue_util = dict(field.split("=") for field in
                          (queue / "done" / f"{job}.util").read_text().split())
        if queue_util["rc"] != "0":
            raise ValueError(f"{job}: キューが正常終了していません")
        runs[tag] = {
            "alpha": alpha,
            "weights": verify_weights(parents, model, alpha),
            "queue": queue_util,
            "queue_history": [line for line in history if job in line],
            "val": verify_split(out, baseline, "val", audit["val"]),
            "test-novel": verify_split(out, baseline, "test-novel", audit["test_novel"]),
        }
    return {"torch": torch.__version__, "transformers": transformers.__version__, "runs": runs}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
