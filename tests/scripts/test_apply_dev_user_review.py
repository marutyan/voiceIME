"""`scripts/apply_dev_user_review.py`（確認用ファイルをmanifestと本人用の用語集へ戻す）の確認。"""

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "apply_dev_user_review", Path(__file__).resolve().parents[2] / "scripts" / "apply_dev_user_review.py"
)
review = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(review)

REVIEW_TEXT = """# dev-userの正解文の確認

説明の文。

## 追加する用語

```text
# RT-DETR = アールティーディーター
Hungarian Matching = ハンガリアンマッチング, ハンガリアン
```

## dev-user-f000

- 種類：自由発話

spoken_text:
```text
えーと、ハンガリアンマッチングは重い。
```

target_text:
```text
Hungarian Matchingは重い。
```

- terms: Hungarian Matching
- fillers: 1
- tags:

## dev-user-s001

spoken_text:
```text
DETRを読んだ、あ、違う、読む。
```

target_text:
```text
DETRを読む。
```

- terms: DETR
- fillers: 0
- tags: self_correction
"""

TRAIN_GLOSSARY = [{"surface": "DETR", "readings": ["ディーイーティーアール"], "split": "train"}]


def _rows():
    return [
        {"id": "dev-user-f000", "prompt_kind": "free", "spoken_text": "【自由発話】題", "target_text": "", "glossary": []},
        {
            "id": "dev-user-s001",
            "prompt_kind": "scripted",
            "spoken_text": "DETRを読んだ。",
            "target_text": "DETRを読んだ。",
            "glossary": [{"surface": "BERT", "readings": ["バート"]}],
        },
    ]


def test_parse_review_reads_additions_and_entries():
    additions, entries = review.parse_review(REVIEW_TEXT)
    # `#`の行は候補なので読まない。読みは「,」で区切る。
    assert additions == [{"surface": "Hungarian Matching", "readings": ["ハンガリアンマッチング", "ハンガリアン"]}]
    assert entries["dev-user-f000"] == {
        "spoken_text": "えーと、ハンガリアンマッチングは重い。",
        "target_text": "Hungarian Matchingは重い。",
        "terms": ["Hungarian Matching"],
        "fillers": 1,
        "tags": [],
    }
    assert entries["dev-user-s001"]["tags"] == ["self_correction"]


def test_apply_accepts_user_terms_and_keeps_script():
    additions, entries = review.parse_review(REVIEW_TEXT)
    user = review.merge_user_glossary([], additions)
    assert user == [{"surface": "Hungarian Matching", "readings": ["ハンガリアンマッチング", "ハンガリアン"], "split": "user"}]
    rows = _rows()
    review.apply(entries, rows, review.combined_glossary(TRAIN_GLOSSARY, user))
    free, scripted = rows
    assert free["glossary"] == [{"surface": "Hungarian Matching", "readings": ["ハンガリアンマッチング", "ハンガリアン"]}]
    assert free["review_status"] == "reviewed"
    # 読み上げの行は台本の用語集（混ぜた語）を残して足りない語を足し、元の台本を残す。
    assert scripted["glossary"] == [
        {"surface": "BERT", "readings": ["バート"]},
        {"surface": "DETR", "readings": ["ディーイーティーアール"]},
    ]
    assert scripted["script_spoken_text"] == "DETRを読んだ。"
    assert scripted["spoken_text"] == "DETRを読んだ、あ、違う、読む。"


def test_apply_rejects_term_missing_from_both_glossaries():
    _, entries = review.parse_review(REVIEW_TEXT)
    with pytest.raises(ValueError, match="追加する用語"):
        review.apply(entries, _rows(), review.combined_glossary(TRAIN_GLOSSARY, []))


def test_merge_user_glossary_adds_readings_to_existing_surface():
    current = [{"surface": "RT-DETR", "readings": ["アールティーデター"], "split": "user"}]
    merged = review.merge_user_glossary(current, [{"surface": "RT-DETR", "readings": ["アールティーディーター"]}])
    assert merged == [{"surface": "RT-DETR", "readings": ["アールティーデター", "アールティーディーター"], "split": "user"}]


@pytest.mark.parametrize("line", ["RT-DETR", "RT-DETR = ", "A = B = C", "A,B = エービー"])
def test_parse_additions_rejects_broken_lines(line):
    with pytest.raises(ValueError):
        review.parse_additions(f"```text\n{line}\n```")


def test_main_writes_user_glossary_and_manifest(tmp_path, monkeypatch):
    review_path = tmp_path / "review.md"
    review_path.write_text(REVIEW_TEXT, encoding="utf-8")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in _rows()), encoding="utf-8")
    train = tmp_path / "train.jsonl"
    train.write_text(json.dumps(TRAIN_GLOSSARY[0], ensure_ascii=False) + "\n", encoding="utf-8")
    user = tmp_path / "user" / "glossary.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        ["apply", "--review", str(review_path), "--manifest", str(manifest), "--train-glossary", str(train),
         "--user-glossary", str(user)],
    )
    review.main()
    assert [json.loads(line)["surface"] for line in user.read_text(encoding="utf-8").splitlines()] == ["Hungarian Matching"]
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["target_text"] == "Hungarian Matchingは重い。"
    # 元のmanifestを別名で残す（本人用の用語集は最初は無いので残すものが無い）。
    assert len(list(tmp_path.glob("manifest.before-review-*.jsonl"))) == 1
