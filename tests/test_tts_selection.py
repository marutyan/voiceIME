"""音声生成へ回す文章行の用語網羅選択を確認する。"""

import importlib.util
import json
import sys
from pathlib import Path

SELECTOR_PATH = Path(__file__).parents[1] / "datagen/tts/select_rows.py"
selector_spec = importlib.util.spec_from_file_location("tts_select_rows_for_test", SELECTOR_PATH)
assert selector_spec is not None and selector_spec.loader is not None
selector_module = importlib.util.module_from_spec(selector_spec)
sys.modules[selector_spec.name] = selector_module
selector_spec.loader.exec_module(selector_module)


def test_term_coverage_selection_picks_new_terms_before_repeats():
    """選択枠が2件なら、3語を含む行と、残る新語を持つ行を選ぶ。"""
    rows = [
        {"id": "multi", "terms": ["A", "B", "C"]},
        {"id": "repeat", "terms": ["A"]},
        {"id": "new", "terms": ["D"]},
        {"id": "empty", "terms": []},
    ]

    selected = selector_module.select_ids_by_term_coverage(rows, count=2, seed=0)

    assert selected == {"multi", "new"}
    assert selector_module.select_ids_by_term_coverage(rows, count=2, seed=0) == selected


def test_cli_writes_the_requested_term_coverage_subset(tmp_path, monkeypatch, capsys):
    """CLIの件数引数を守り、選んだ行とid一覧を出力する。"""
    text_dir = tmp_path / "text"
    out_dir = tmp_path / "selected"
    text_dir.mkdir()
    rows = [
        {"id": "multi", "terms": ["A", "B", "C"]},
        {"id": "repeat", "terms": ["A"]},
        {"id": "new", "terms": ["D"]},
        {"id": "empty", "terms": []},
    ]
    (text_dir / "train.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_rows.py",
            "--text-dir",
            str(text_dir),
            "--out",
            str(out_dir),
            "--count",
            "train=2",
            "--prioritize-terms",
            "train",
            "--seed",
            "0",
        ],
    )

    selector_module.main()

    selected_rows = [json.loads(line) for line in (out_dir / "input.jsonl").read_text().splitlines()]
    assert [row["id"] for row in selected_rows] == ["multi", "new"]
    assert (out_dir / "selected_ids_train.txt").read_text().splitlines() == ["multi", "new"]
    assert "用語網羅 4/4" in capsys.readouterr().out
