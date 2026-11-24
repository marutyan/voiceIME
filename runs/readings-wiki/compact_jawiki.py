"""転送量を抑えるため、英字表記の照合に関係する転送とカテゴリだけを残す。"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from extract_jawiki import latin_form, title_form, write_record


def compact(source: Path, destination: Path) -> None:
    """英字転送を最終記事へ結び直し、記事の直上2階層に必要なカテゴリを残す。"""
    parents = {}
    categories = set()
    redirects = {}
    counts = None
    with (
        gzip.open(source, "rt", encoding="utf-8") as stream,
        gzip.open(destination, "wb", compresslevel=6) as output,
    ):
        for line in stream:
            row = json.loads(line)
            if "c" in row:
                parents[row["c"]] = row["p"]
            elif "r" in row:
                redirects[row["r"]] = row["t"]
            elif "stats" in row:
                counts = row
            else:
                categories.update(row["p"])
                output.write(line.encode())
        if counts is None:
            raise ValueError("全件走査の終了レコードがありません")

        parents_to_keep = categories | {
            parent for category in categories for parent in parents.get(category, [])
        }
        for category in sorted(parents_to_keep & parents.keys()):
            write_record(output, {"c": category, "p": parents[category]})
        for title, target in redirects.items():
            if not latin_form(title_form(title)):
                continue
            seen = {title}
            while target in redirects and target not in seen:
                seen.add(target)
                target = redirects[target]
            if target not in seen:
                write_record(output, {"r": title, "t": target})
        write_record(output, counts)


def main() -> None:
    """生の中間結果を、手元で照合する転送用ファイルに変換する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compact(args.input, args.output)


if __name__ == "__main__":
    main()
