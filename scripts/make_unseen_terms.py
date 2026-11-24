"""manifestの正解用語から、推論時の用語集から外す「見えない用語」の一覧を作る。

実行例（手元のMac、作業ツリーで）：
    uv run python scripts/make_unseen_terms.py \\
        --manifest /Users/marutyan/PrivateDev/voiceIME/data/dev-user/manifest.jsonl \\
        --prompt-kind scripted --out data/eval/unseen-terms-devuser.txt
    uv run python scripts/make_unseen_terms.py \\
        --manifest /Users/marutyan/PrivateDev/voiceIME/data/tts/val/manifest.jsonl \\
        --out data/eval/unseen-terms-val.txt
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Iterable, Sequence
from pathlib import Path

# 正解用語のうち、見えない用語として選ぶ既定の割合（30%）。
DEFAULT_RATIO = 0.3
# 再現性を保つため、`docs/PLAN.md`の既定と同じ乱数seedを使う。
DEFAULT_SEED = 0


def read_manifest(path: Path) -> list[dict]:
    """1行1件のmanifest JSONLを読み込む。"""
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: 各行はJSON objectが必要です")
            rows.append(row)
    return rows


def collect_terms(rows: Iterable[dict], prompt_kind: str | None = None) -> list[str]:
    """対象行の`terms`に現れる用語を重複なく集め、表記順で返す。"""
    unique_terms: set[str] = set()
    for row in rows:
        if prompt_kind is not None and row.get("prompt_kind") != prompt_kind:
            continue
        terms = row.get("terms", [])
        if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
            raise ValueError(f"{row.get('id', '<unknown>')}: termsは文字列の配列が必要です")
        for term in terms:
            stripped = term.strip()
            if stripped:
                unique_terms.add(stripped)
    return sorted(unique_terms)


def sample_unseen_terms(
    terms: Sequence[str], ratio: float = DEFAULT_RATIO, seed: int = DEFAULT_SEED
) -> list[str]:
    """重複を除いて並べた用語一覧から、指定seedと割合で見えない用語を選んで表記順で返す。"""
    if not 0.0 <= ratio <= 1.0:
        raise ValueError(f"ratioは0から1の範囲で指定する: {ratio}")
    ordered_terms = sorted(set(terms))
    count = round(len(ordered_terms) * ratio)
    rng = random.Random(seed)
    return sorted(rng.sample(ordered_terms, count))


def write_term_list(path: Path, terms: Sequence[str]) -> None:
    """1行1語のテキストファイルとして書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(f"{term}\n" for term in terms)
    path.write_text(content, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を読む。"""
    parser = argparse.ArgumentParser(
        description="manifestの正解termsから、用語集から除く「見えない用語」の一覧を作る"
    )
    parser.add_argument("--manifest", required=True, type=Path, help="対象のmanifest JSONL")
    parser.add_argument("--out", required=True, type=Path, help="1行1語で書き出すテキストファイル")
    parser.add_argument(
        "--ratio",
        type=float,
        default=DEFAULT_RATIO,
        help=f"見えない用語として選ぶ割合（0〜1、既定: {DEFAULT_RATIO}）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"抽出に使う乱数seed（既定: {DEFAULT_SEED}）",
    )
    parser.add_argument(
        "--prompt-kind",
        default=None,
        help="対象にするprompt_kind（例: scripted）。省略時は全行を対象にする",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """manifestから見えない用語を選び、1行1語のファイルへ書き出す。"""
    args = parse_args(argv)
    rows = read_manifest(args.manifest)
    target_rows = (
        [row for row in rows if row.get("prompt_kind") == args.prompt_kind]
        if args.prompt_kind is not None
        else rows
    )
    unique_terms = collect_terms(target_rows)
    selected = sample_unseen_terms(unique_terms, ratio=args.ratio, seed=args.seed)
    write_term_list(args.out, selected)
    print(
        f"{len(target_rows)}行のユニーク用語{len(unique_terms)}語から"
        f"{len(selected)}語を選び、{args.out}へ書き出しました（seed={args.seed}, ratio={args.ratio}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
