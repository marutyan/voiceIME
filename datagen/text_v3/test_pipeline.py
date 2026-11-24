"""小さな偽用語集と偽教師出力で、第3弾生成の境界を確かめる。"""

from __future__ import annotations

import json
from collections import Counter

from pipeline import (
    Glossary,
    _build_rows,
    _render_v3_item,
    load_confusables,
    make_training_specs,
    new_heldout_terms,
    validate_novel_rows,
    validate_training_rows,
)


def _fixture() -> tuple[list[dict], dict[str, dict], dict[str, list[dict]], list[dict]]:
    """train語、近音候補、新held-out語、v1語を含む最小の用語集を返す。"""
    rows = [
        {"surface": "AlphaNet", "readings": ["アルファネット"], "category": "programming", "split": "train", "style": "latin"},
        {"surface": "BetaNet", "readings": ["ベータネット"], "category": "programming", "split": "train", "style": "latin"},
        {"surface": "DecoyNet", "readings": ["デコイネット"], "category": "programming", "split": "train", "style": "latin"},
        {"surface": "GammaNet", "readings": ["ガンマネット"], "category": "programming", "split": "train", "style": "latin"},
        {"surface": "NovelModel", "readings": ["ノベルモデル"], "category": "ml-research", "split": "held-out", "style": "latin"},
        {"surface": "OldNovel", "readings": ["オールドノベル"], "category": "ml-research", "split": "held-out", "style": "latin"},
    ]
    by_surface = {row["surface"]: row for row in rows}
    confusables = {
        "AlphaNet": [by_surface["DecoyNet"]],
        "BetaNet": [by_surface["DecoyNet"]],
        "NovelModel": [by_surface["DecoyNet"]],
    }
    legacy_rows = [{"surface": "OldNovel"}]
    return rows, by_surface, confusables, legacy_rows


def _spec(spec_id: str, surface: str, reading: str, glossary: list[dict], *, omitted: bool = False, split: str = "train") -> dict:
    """固定条件で偽教師へ渡す仕様を作る。"""
    return {
        "spec_id": spec_id,
        "split": "test" if split == "test-novel" else split,
        "domain": "ml-research" if surface == "NovelModel" else "programming",
        "usecase": "chat",
        "filler_level": "none",
        "restatement": None,
        "numbers": False,
        "english_phrase": None,
        "instruction_like": False,
        "enumeration": False,
        "no_change": False,
        "terms": [{"surface": surface, "reading": reading, "category": "ml-research" if surface == "NovelModel" else "programming"}],
        "omitted_surfaces": [surface] if omitted else [],
        "planned_terms": [surface],
        "novel_terms": [surface] if split == "test-novel" else [],
        "glossary": glossary,
        "request_id": f"req-{spec_id}",
        "request_index": 1,
    }


def _teacher_output(spec: dict) -> dict:
    """出力検査を通る決め打ちのspoken/targetを偽教師として返す。"""
    term = spec["terms"][0]
    surface, reading = term["surface"], term["reading"]
    if surface in spec["omitted_surfaces"]:
        spoken = f"この実験では、{reading}を使って結果を定期的に確認します"
        target = f"この実験では、{reading}を使って結果を定期的に確認します。"
    else:
        spoken = f"この実験では、[[{surface}|{reading}]]を使って結果を定期的に確認します"
        target = f"この実験では、{surface}を使って結果を定期的に確認します。"
    return {"id": spec["request_id"], "text": json.dumps({"i": 1, "spoken": spoken, "target": target}, ensure_ascii=False)}


def test_planner_assigns_every_train_term_and_hides_omitted_surface() -> None:
    """各train語の割当回数と、辞書抜け語のプロンプト制約を確かめる。"""
    rows, by_surface, confusables, _ = _fixture()
    specs = make_training_specs(
        [by_surface["AlphaNet"], by_surface["BetaNet"], by_surface["GammaNet"]],
        by_surface,
        confusables,
        minimum_repeats=3,
        overgeneration=1,
        seed=12,
        id_prefix="small",
    )
    counts = Counter(surface for spec in specs for surface in spec["planned_terms"])
    assert counts == {"AlphaNet": 3, "BetaNet": 3, "GammaNet": 3}
    assert abs(sum(bool(spec["omitted_surfaces"]) for spec in specs) / len(specs) - 0.15) <= 0.1
    assert any("DecoyNet" in {entry["surface"] for entry in spec["glossary"]} for spec in specs)
    omitted = next(spec for spec in specs if spec["omitted_surfaces"])
    rendered = _render_v3_item(1, omitted)
    omitted_surface = omitted["omitted_surfaces"][0]
    omitted_reading = next(term["reading"] for term in omitted["terms"] if term["surface"] == omitted_surface)
    assert omitted_surface not in rendered
    assert omitted_reading in rendered
    assert all(entry["split"] == "train" for entry in rows if entry["surface"] in {g["surface"] for spec in specs for g in spec["glossary"]})


def test_missing_confusable_references_are_counted_and_skipped(tmp_path) -> None:
    """用語集v2に残っていない近音候補を無視し、除外件数を返す。"""
    rows, by_surface, _, _ = _fixture()
    path = tmp_path / "confusables.jsonl"
    path.write_text(
        json.dumps({"surface": "AlphaNet", "confusables": [{"surface": "DecoyNet"}, {"surface": "RemovedTerm"}]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    candidates, stale = load_confusables(path, by_surface)
    assert [row["surface"] for row in candidates["AlphaNet"]] == ["DecoyNet"]
    assert stale == 1


def test_fake_teacher_build_keeps_unlisted_term_kana_and_filters_decoy() -> None:
    """偽教師出力の検査後、辞書抜け語をかなで保ち、近音語を正解へ入れない。"""
    rows, by_surface, _, legacy = _fixture()
    train_specs = [
        _spec("train-alpha", "AlphaNet", "アルファネット", [{"surface": "DecoyNet", "readings": ["デコイネット"]}], omitted=True),
        _spec("train-beta", "BetaNet", "ベータネット", [{"surface": "BetaNet", "readings": ["ベータネット"]}, {"surface": "DecoyNet", "readings": ["デコイネット"]}]),
        _spec("train-decoy", "DecoyNet", "デコイネット", [{"surface": "DecoyNet", "readings": ["デコイネット"]}]),
        _spec("train-gamma", "GammaNet", "ガンマネット", [{"surface": "GammaNet", "readings": ["ガンマネット"]}]),
    ]
    train_outputs = {spec["request_id"]: _teacher_output(spec) for spec in train_specs}
    built_train, train_rejects = _build_rows(train_specs, train_outputs, Glossary.from_rows(rows), "train")
    missing, errors = validate_training_rows(built_train, rows, 0, Glossary.from_rows(rows))
    assert not train_rejects
    assert not missing
    assert not errors
    omitted = next(row for row in built_train if row["omitted_terms"])
    assert all(row["glossary_fixed"] is True for row in built_train)
    assert omitted["terms"] == []
    assert "AlphaNet" not in omitted["target_text"]
    assert "アルファネット" in omitted["target_text"]
    assert "DecoyNet" in {entry["surface"] for entry in omitted["glossary"]}
    assert "DecoyNet" not in omitted["target_text"]
    assert all(entry["surface"] not in {"NovelModel", "OldNovel"} for row in built_train for entry in row["glossary"])

    novel_terms = new_heldout_terms(rows, legacy)
    assert [row["surface"] for row in novel_terms] == ["NovelModel"]
    novel_spec = _spec("novel-new", "NovelModel", "ノベルモデル", [{"surface": "NovelModel", "readings": ["ノベルモデル"]}, {"surface": "DecoyNet", "readings": ["デコイネット"]}], split="test-novel")
    novel_output = _teacher_output(novel_spec)
    built_novel, novel_rejects = _build_rows([novel_spec], {novel_spec["request_id"]: novel_output}, Glossary.from_rows(rows), "novel")
    novel_errors = validate_novel_rows(built_novel, {"NovelModel"}, by_surface)
    assert not novel_rejects
    assert not novel_errors
    assert built_novel[0]["terms"] == ["NovelModel"]
    assert built_novel[0]["novel_terms"] == ["NovelModel"]
    assert "NovelModel" not in {entry["surface"] for entry in built_train[0]["glossary"]}
