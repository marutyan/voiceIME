"""`scripts/make_unseen_terms.py`と生成済み一覧ファイルの確認。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "make_unseen_terms", _ROOT / "scripts" / "make_unseen_terms.py"
)
assert _SPEC is not None and _SPEC.loader is not None
make_unseen_terms = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(make_unseen_terms)


def test_make_unseen_terms_filters_prompt_kind_and_samples_deterministically(tmp_path) -> None:
    """10語のユニーク用語からseed 0・30%で3語を選び、free行や重複を混ぜない。"""
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        {"id": "s1", "prompt_kind": "scripted", "terms": ["C#", "Docker", "PyTorch"]},
        {"id": "s2", "prompt_kind": "scripted", "terms": ["PyTorch", "FastAPI", "GitHub"]},
        {"id": "s3", "prompt_kind": "scripted", "terms": ["Kubernetes", "MLX", "ONNX", "Redis", "uv"]},
        {"id": "f1", "prompt_kind": "free", "terms": ["FreeOnlyTerm"]},
    ]
    manifest.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    out1 = tmp_path / "out1.txt"
    out2 = tmp_path / "out2.txt"
    assert (
        make_unseen_terms.main(
            ["--manifest", str(manifest), "--prompt-kind", "scripted", "--out", str(out1)]
        )
        == 0
    )
    assert (
        make_unseen_terms.main(
            ["--manifest", str(manifest), "--prompt-kind", "scripted", "--out", str(out2)]
        )
        == 0
    )

    lines = out1.read_text(encoding="utf-8").splitlines()
    assert lines == out2.read_text(encoding="utf-8").splitlines()
    # 10語を昇順に並べた一覧からseed=0・30%（round(10*0.3)=3語）で確定する3語。
    assert lines == ["C#", "ONNX", "uv"]
    assert "FreeOnlyTerm" not in lines


def test_sample_unseen_terms_rejects_out_of_range_ratio() -> None:
    """割合が0〜1の範囲外ならエラーにする。"""
    with pytest.raises(ValueError, match="ratio"):
        make_unseen_terms.sample_unseen_terms(["PyTorch"], ratio=1.5, seed=0)


def test_generated_unseen_term_files_have_expected_counts_and_format() -> None:
    """dev-user読み上げ50件（67語の30%=20語）とval（861語の30%=258語）の一覧が正しく存在する。"""
    devuser_lines = (_ROOT / "data" / "eval" / "unseen-terms-devuser.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    val_lines = (_ROOT / "data" / "eval" / "unseen-terms-val.txt").read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(devuser_lines) == 20
    assert len(set(devuser_lines)) == 20
    assert devuser_lines == sorted(devuser_lines)
    assert all(line and line == line.strip() for line in devuser_lines)

    assert len(val_lines) == 258
    assert len(set(val_lines)) == 258
    assert val_lines == sorted(val_lines)
    assert all(line and line == line.strip() for line in val_lines)
