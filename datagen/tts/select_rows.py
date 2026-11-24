"""文章データから読み上げる行を選び、選んだidの一覧と、生成に渡す入力JSONLを書く。

集合ごとに件数を指定する。既定はseed付き無作為選択で、`--prioritize-terms`を指定したsplitは用語網羅を優先する。
選んだidは集合ごとのテキストファイル（1行1id、元のファイルの順）に残し、後から同じ選択を確かめられるようにする。

使い方:
    python select_rows.py --text-dir data/text --out data/tts/work \
        --count test-synth=1000 --count val=1000 --count train=12000 \\
        --prioritize-terms train --seed 0
"""

import argparse
import heapq
import json
import random
from collections import Counter
from pathlib import Path


def select_ids(ids: list[str], count: int, seed: int) -> set[str]:
    """idの一覧から count 件を無作為に選ぶ。count が全件以上なら全件を返す。"""
    if count >= len(ids):
        return set(ids)
    return set(random.Random(seed).sample(ids, count))


def select_ids_by_term_coverage(rows: list[dict], count: int, seed: int) -> set[str]:
    """未選択の行が増やす用語数を優先し、残りをseed付きで補ってidを返す。"""
    if count < 0:
        raise ValueError("countは0以上が必要です")
    if count >= len(rows):
        return {row["id"] for row in rows}

    terms_by_index: dict[int, set[str]] = {}
    frequencies: Counter[str] = Counter()
    for index, row in enumerate(rows):
        terms = row.get("terms", [])
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            raise ValueError(f"{row.get('id')}: termsは文字列の配列である必要があります")
        unique_terms = set(terms)
        terms_by_index[index] = unique_terms
        frequencies.update(unique_terms)

    rng = random.Random(seed)
    tie_breakers = [rng.random() for _ in rows]
    candidates: list[tuple[int, float, float, int]] = []
    for index, terms in terms_by_index.items():
        rarity = sum(1 / frequencies[term] for term in sorted(terms))
        heapq.heappush(candidates, (-len(terms), -rarity, tie_breakers[index], index))
    selected: set[int] = set()
    covered: set[str] = set()
    target_count = min(count, len(rows))
    while len(selected) < target_count:
        if not candidates:
            break
        negative_count, negative_rarity, tie_breaker, index = heapq.heappop(candidates)
        new_terms = terms_by_index[index] - covered
        if not new_terms:
            continue
        rarity = sum(1 / frequencies[term] for term in sorted(new_terms))
        if len(new_terms) != -negative_count or rarity != -negative_rarity:
            heapq.heappush(candidates, (-len(new_terms), -rarity, tie_breaker, index))
            continue
        selected.add(index)
        covered.update(new_terms)

    if len(selected) < target_count:
        remaining = sorted(set(range(len(rows))) - selected)
        selected.update(rng.sample(remaining, target_count - len(selected)))
    return {rows[index]["id"] for index in selected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text-dir", type=Path, required=True, help="<split>.jsonl が置かれたディレクトリ")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", action="append", required=True, help="<split>=<件数>。複数指定できる")
    parser.add_argument(
        "--prioritize-terms",
        action="append",
        default=[],
        metavar="SPLIT",
        help="指定splitは未選択用語の網羅を優先して音声行を選ぶ（複数指定可）",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    selected_rows = []
    for spec in args.count:
        split, count = spec.split("=")
        lines = [line for line in (args.text_dir / f"{split}.jsonl").read_text().splitlines() if line.strip()]
        rows = [json.loads(line) for line in lines]
        ids = [row["id"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{split}: idが重複しています")
        requested_count = int(count)
        if split in args.prioritize_terms:
            chosen = select_ids_by_term_coverage(rows, requested_count, args.seed)
        else:
            chosen = select_ids(ids, requested_count, args.seed)
        picked = [r for r in rows if r["id"] in chosen]
        (args.out / f"selected_ids_{split}.txt").write_text("".join(r["id"] + "\n" for r in picked))
        selected_rows += picked
        coverage = ""
        if split in args.prioritize_terms:
            all_terms = {term for row in rows for term in row.get("terms", [])}
            selected_terms = {term for row in picked for term in row.get("terms", [])}
            coverage = f"、用語網羅 {len(selected_terms)}/{len(all_terms)}"
        print(f"{split}: {len(rows)}件から{len(picked)}件{coverage}")
    with (args.out / "input.jsonl").open("w") as f:
        for r in selected_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
