"""本人が直した`data/dev-user/review.md`を、`data/dev-user/manifest.jsonl`と本人用の用語集へ戻す。

review.mdは次の2つの部分からなる。
- `## 追加する用語`：本人が使いたい表記の語を、```text```の中に1行1語の`表記 = 読み1, 読み2`で書く。
  `#`で始まる行は無視する。これらは本人用の用語集（`data/user/glossary.jsonl`、`split: "user"`）へ追記する。
- `## <id>`の各件：`spoken_text:`と`target_text:`の直後の```text```の中身と、`- terms:`、`- fillers:`、`- tags:`の行。
  manifestの同じidの行を書き換える。

`terms`は、学習用の用語集（`data/text/glossary.jsonl`）と本人用の用語集を合わせた中の語で、`target_text`に表記通り
現れることを確かめる。`glossary`は`terms`の語を合わせた用語集の表記と読みで作り直す。ただし読み上げの行は、
台本の用語集（文に出ない語を混ぜたもの）を残し、足りない語だけを加える。
読み上げの行の`spoken_text`を変えた場合は、元の台本を`script_spoken_text`に残す。
書き換える前に、元のmanifestと本人用の用語集を`*.before-review-<日時>.jsonl`として保存する。

実行（手元のMac、作業ツリーで）：
    uv run python scripts/apply_dev_user_review.py
    uv run python scripts/apply_dev_user_review.py --dry-run   # 書き換えずに変更点だけ表示する
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/Users/marutyan/PrivateDev/voiceIME/data")
REVIEW_PATH = DATA_DIR / "dev-user" / "review.md"
MANIFEST_PATH = DATA_DIR / "dev-user" / "manifest.jsonl"
TRAIN_GLOSSARY_PATH = DATA_DIR / "text" / "glossary.jsonl"
USER_GLOSSARY_PATH = DATA_DIR / "user" / "glossary.jsonl"
# `docs/PLAN.md`で定めた発話の種類。これ以外のtagは打ち間違いとして止める。
ALLOWED_TAGS = {"self_correction", "no_change", "instruction_like", "list", "english_phrase"}
# 「追加する用語」の見出し。各件の見出し（`## <id>`）と区別する。
ADDITIONS_HEADING = "追加する用語"

SECTION = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
TEXT_BLOCK = re.compile(r"^(spoken_text|target_text):\s*\n```text\n(.*?)\n```", re.MULTILINE | re.DOTALL)
ANY_TEXT_BLOCK = re.compile(r"^```text\n(.*?)\n```", re.MULTILINE | re.DOTALL)
FIELD_LINE = re.compile(r"^- (terms|fillers|tags):[ \t]*(.*)$", re.MULTILINE)
# 表記や読みに含まれると、用語集やASRのヒント（`表記=読み`の行）の書式を壊す文字。
FORBIDDEN_CHARS = ("=", ",", "、", "\t")


def split_sections(text: str) -> dict[str, str]:
    """review.mdを見出し（`## ...`）ごとの本文に分ける。同じ見出しが2つあれば誤りとして止める。"""
    matches = list(SECTION.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1)
        if title in sections:
            raise ValueError(f"見出し「{title}」が2つある")
        sections[title] = text[match.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
    return sections


def parse_additions(body: str) -> list[dict]:
    """「追加する用語」の欄から`{"surface", "readings"}`の一覧を作る。読みの無い行や書式の崩れた行は誤りとして止める。"""
    block = ANY_TEXT_BLOCK.search(body)
    if block is None:
        return []
    additions = []
    for line in block.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("=") != 1:
            raise ValueError(f"追加する用語は`表記 = 読み1, 読み2`の形で書く：{line!r}")
        surface, readings_text = (part.strip() for part in line.split("="))
        readings = [r.strip() for r in re.split(r"[,、]", readings_text) if r.strip()]
        if not surface or not readings:
            raise ValueError(f"追加する用語に表記と読みの両方が要る：{line!r}")
        if any(char in item for item in [surface, *readings] for char in FORBIDDEN_CHARS):
            raise ValueError(f"追加する用語の表記と読みに{FORBIDDEN_CHARS}は使えない：{line!r}")
        additions.append({"surface": surface, "readings": readings})
    return additions


def parse_entry(item_id: str, body: str) -> dict:
    """1件分の本文から{spoken_text, target_text, terms, fillers, tags}を作る。欠けている項目は誤りとして止める。"""
    blocks = {name: value for name, value in TEXT_BLOCK.findall(body)}
    fields = {name: value.strip() for name, value in FIELD_LINE.findall(body)}
    missing = [k for k in ("spoken_text", "target_text") if k not in blocks]
    missing += [k for k in ("terms", "fillers", "tags") if k not in fields]
    if missing:
        raise ValueError(f"{item_id}: {', '.join(missing)}が読めない")
    if not fields["fillers"].isdigit():
        raise ValueError(f"{item_id}: fillersは0以上の整数で書く（{fields['fillers']!r}）")
    tags = [t.strip() for t in fields["tags"].split(",") if t.strip()]
    if unknown := sorted(set(tags) - ALLOWED_TAGS):
        raise ValueError(f"{item_id}: 未知のtag {unknown}")
    return {
        "spoken_text": blocks["spoken_text"].strip(),
        "target_text": blocks["target_text"].strip(),
        "terms": [t.strip() for t in fields["terms"].split(",") if t.strip()],
        "fillers": int(fields["fillers"]),
        "tags": tags,
    }


def parse_review(text: str) -> tuple[list[dict], dict[str, dict]]:
    """review.mdを（追加する用語, 件ごとの内容）に分ける。"""
    additions: list[dict] = []
    entries = {}
    for title, body in split_sections(text).items():
        if title == ADDITIONS_HEADING:
            additions = parse_additions(body)
        else:
            entries[title] = parse_entry(title, body)
    return additions, entries


def merge_user_glossary(current: list[dict], additions: list[dict]) -> list[dict]:
    """本人用の用語集へ追加する用語を足す。同じ表記の語は読みをまとめ、元の順を保つ。"""
    merged = {record["surface"]: dict(record, readings=list(record["readings"])) for record in current}
    for addition in additions:
        record = merged.setdefault(addition["surface"], {"surface": addition["surface"], "readings": [], "split": "user"})
        record["readings"].extend(r for r in addition["readings"] if r not in record["readings"])
    return list(merged.values())


def combined_glossary(train: list[dict], user: list[dict]) -> dict[str, list[str]]:
    """学習用と本人用の用語集を合わせ、表記から読みの一覧を引ける形にする。同じ表記は学習用の読みを先に並べる。"""
    readings: dict[str, list[str]] = {}
    for record in [*train, *user]:
        merged = readings.setdefault(record["surface"], [])
        merged.extend(r for r in record["readings"] if r not in merged)
    return readings


def rebuild_glossary(row: dict, terms: list[str], glossary: dict[str, list[str]]) -> list[dict]:
    """行の`glossary`を`terms`に合わせる。読み上げの行は台本の語を残し、自由発話の行は`terms`の語だけにする。"""
    kept = row.get("glossary", []) if row.get("prompt_kind") == "scripted" else []
    present = {entry["surface"] for entry in kept}
    return kept + [{"surface": term, "readings": glossary[term]} for term in terms if term not in present]


def apply(entries: dict[str, dict], rows: list[dict], glossary: dict[str, list[str]]) -> list[str]:
    """manifestの行を書き換え、変更点の説明を返す。用語集に無い語、target_textに無い語は誤りとして止める。"""
    by_id = {row["id"]: row for row in rows}
    changes = []
    for item_id, entry in entries.items():
        if item_id not in by_id:
            raise ValueError(f"{item_id}: manifestに無いid")
        row = by_id[item_id]
        for term in entry["terms"]:
            if term not in glossary:
                raise ValueError(f"{item_id}: 用語集に無い語 {term!r}（「追加する用語」に足す）")
            if term not in entry["target_text"]:
                raise ValueError(f"{item_id}: target_textに無い語 {term!r}")
        if row.get("prompt_kind") == "scripted" and entry["spoken_text"] != row["spoken_text"]:
            row.setdefault("script_spoken_text", row["spoken_text"])
        changed = [key for key in ("spoken_text", "target_text", "terms", "fillers", "tags") if row.get(key) != entry[key]]
        row.update(entry)
        row["glossary"] = rebuild_glossary(row, entry["terms"], glossary)
        row["review_status"] = "reviewed"
        changes.append(f"{item_id}: {', '.join(changed) if changed else '変更なし'}")
    return changes


def read_jsonl(path: Path) -> list[dict]:
    """JSONLを読む。ファイルが無ければ空の一覧を返す（本人用の用語集は最初は無い）。"""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict], timestamp: str) -> None:
    """元のファイルがあれば`*.before-review-<日時>.jsonl`として残してから書き換える。"""
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.stem}.before-review-{timestamp}.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="review.mdの正解文と追加する用語を、dev-userのmanifestと本人用の用語集へ戻す")
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--train-glossary", type=Path, default=TRAIN_GLOSSARY_PATH)
    parser.add_argument("--user-glossary", type=Path, default=USER_GLOSSARY_PATH)
    parser.add_argument("--dry-run", action="store_true", help="書き換えずに変更点だけ表示する")
    args = parser.parse_args()

    additions, entries = parse_review(args.review.read_text(encoding="utf-8"))
    user_glossary = merge_user_glossary(read_jsonl(args.user_glossary), additions)
    glossary = combined_glossary(read_jsonl(args.train_glossary), user_glossary)
    rows = read_jsonl(args.manifest)
    changes = apply(entries, rows, glossary)
    print(f"追加する用語：{len(additions)}語（本人用の用語集は計{len(user_glossary)}語）")
    print("\n".join(changes))
    if args.dry_run:
        return
    timestamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    write_jsonl(args.user_glossary, user_glossary, timestamp)
    write_jsonl(args.manifest, rows, timestamp)
    print(f"{len(entries)}件をmanifestへ、{len(additions)}語を{args.user_glossary}へ戻した（元のファイルは*.before-review-{timestamp}.jsonl）")


if __name__ == "__main__":
    main()
