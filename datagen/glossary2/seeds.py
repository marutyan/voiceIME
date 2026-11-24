"""fetch_seeds.py で取った公開の一覧から、用語集v2の種（見直しにかける候補）を取り出す。

実行場所：手元（Mac）。Papers with Codeの一覧がparquetのため pyarrow を一時的に使う。
使い方：uv run --with pyarrow python datagen/glossary2/seeds.py <fetch_seedsの保存先> <出力のseeds.jsonl>
出力の各行：{"term": 種の文字列, "hint": 出どころの説明, "source": 一覧の名前}
各一覧から取る件数は、上位の知られた語に絞りつつ合計で約3万になるように決めた（SOURCE_LIMITS）。
"""

from __future__ import annotations

import ast
import html
import json
import re
import sys
from pathlib import Path

# 一覧ごとに取る上位の件数。下位ほど話題にならない名前が増えるため、上位に絞る。
# 最初は合計約3万（PyPI 5,000、npm 4,000、Homebrew 3,000と2,000、論文数の下限は手法2・データセット5）で見直したが、
# 見直しで残る割合が約3割で目標の語数に届かなかったため、2回目の見直しの前に広げた。
SOURCE_LIMITS = {
    "pypi": 15000,
    "npm": 10000,
    "crates": 1500,
    "brew-formula": 6000,
    "brew-cask": 4000,
}
# Papers with Codeの一覧で残す最小の論文数。論文数の少ない項目には宣伝の書き込みが混ざるため、is_clean で文の形のものを除く。
PWC_METHOD_MIN_PAPERS = 1
PWC_DATASET_MIN_PAPERS = 2
# awesomeリストの項目名として認める最大の長さ（長い文は名前ではない）。
MAX_TERM_LEN = 60
# awesomeリストの「- [名前](URL)」の行。
AWESOME_RE = re.compile(r"^\s*[-*] \[([^\]]+)\]\(")

# ユーザーの分野で必ず入れる語（課題の指定）。見直しの判定に関わらず残す。
MUST_INCLUDE = (
    "Hungarian Matching",
    "auxiliary loss",
    "RT-DETR",
    "Shadow DETR",
    "Deformable DETR",
    "Query Selection",
    "Detection Transformer",
    "Average Precision",
    "Miss Rate",
    "CrowdHuman",
    "Optuna",
)


def is_clean(term: str) -> bool:
    """名前として使える文字列か（空でない、長すぎない、英字を含む、宣伝や文でない）を返す。"""
    if not term or len(term) > MAX_TERM_LEN or not re.search(r"[A-Za-z]", term):
        return False
    if re.search(r"[?？!！@【】{}|~®™]|https?:", term):
        return False
    return len(term.split()) <= 6


def pwc_seeds(raw: Path) -> list[dict]:
    """Papers with Codeの手法とデータセットから、論文数の多い順に種を取る。"""
    import pyarrow.parquet as pq

    def n_papers(r: dict) -> int:
        try:
            return int(r["num_papers"])
        except (TypeError, ValueError):
            return 0

    out = []
    methods = sorted(pq.read_table(raw / "pwc_methods.parquet").to_pylist(), key=n_papers, reverse=True)
    for r in methods:
        if n_papers(r) < PWC_METHOD_MIN_PAPERS or not is_clean(r["name"]):
            continue
        full = r.get("full_name") or ""
        coll = ""
        try:
            colls = ast.literal_eval(r.get("collections") or "[]")
            coll = colls[0]["collection"] if colls else ""
        except (ValueError, SyntaxError, KeyError, IndexError, TypeError):
            pass
        hint = "Papers with Codeの手法名"
        if full and full != r["name"] and is_clean(full):
            hint += f"（正式名：{full}）"
        if coll:
            hint += f"、分類：{coll}"
        out.append({"term": r["name"], "hint": hint, "source": "pwc-methods"})
    datasets = sorted(pq.read_table(raw / "pwc_datasets.parquet").to_pylist(), key=n_papers, reverse=True)
    for r in datasets:
        if n_papers(r) < PWC_DATASET_MIN_PAPERS or not is_clean(r["name"]):
            continue
        out.append({"term": r["name"], "hint": "Papers with Codeのデータセット名", "source": "pwc-datasets"})
    return out


def list_seeds(raw: Path) -> list[dict]:
    """パッケージの人気一覧（PyPI、npm、crates.io、Homebrew）から上位の種を取る。"""
    out = []
    pypi = json.loads((raw / "pypi_top.json").read_text())["rows"]
    for r in pypi[: SOURCE_LIMITS["pypi"]]:
        out.append({"term": r["project"], "hint": "PyPIのパッケージ名", "source": "pypi"})
    npm = re.findall(r"^\s*'([^']+)',?$", (raw / "npm_top.js").read_text(), flags=re.M)
    for name in npm[: SOURCE_LIMITS["npm"]]:
        out.append({"term": name, "hint": "npmのパッケージ名", "source": "npm"})
    crates = []
    for p in sorted(raw.glob("crates_*.json")):
        crates += json.loads(p.read_text())["crates"]
    for c in crates[: SOURCE_LIMITS["crates"]]:
        desc = (c.get("description") or "").strip().replace("\n", " ")[:80]
        out.append({"term": c["name"], "hint": f"Rustのクレート名（{desc}）", "source": "crates"})
    formulas = json.loads((raw / "brew_formula_365d.json").read_text())["items"]
    for it in formulas[: SOURCE_LIMITS["brew-formula"]]:
        out.append({"term": it["formula"], "hint": "Homebrewのパッケージ名（コマンドやライブラリ）", "source": "brew-formula"})
    names = {c["token"]: c for c in json.loads((raw / "brew_cask.json").read_text())}
    casks = json.loads((raw / "brew_cask_365d.json").read_text())["items"]
    for it in casks[: SOURCE_LIMITS["brew-cask"]]:
        c = names.get(it["cask"])
        if c is None or not c.get("name"):
            continue
        desc = (c.get("desc") or "")[:60]
        hint = f"macOSのアプリ名（{desc}）" if desc else "macOSのアプリ名"
        out.append({"term": c["name"][0], "hint": hint, "source": "brew-cask"})
    return out


def hf_seeds(raw: Path) -> list[dict]:
    """Hugging Faceのダウンロード数・いいね数の上位のモデルとデータセットのIDを種にする。"""
    out = []
    for kind, label in (("models", "モデル"), ("datasets", "データセット")):
        seen = set()
        for sort in ("downloads", "likes"):
            for r in json.loads((raw / f"hf_{kind}_{sort}.json").read_text()):
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                out.append({"term": r["id"], "hint": f"Hugging Faceの{label}のID", "source": f"hf-{kind}"})
    return out


def arxiv_seeds(raw: Path) -> list[dict]:
    """arXivの分類の記号（例：cs.CV）を種にする。"""
    text = (raw / "arxiv_taxonomy.html").read_text()
    out = []
    for code, name in re.findall(r"<h4>([a-z\-]+(?:\.[A-Za-z\-]+)?) <span>\(([^)]*)\)", text):
        out.append({"term": code, "hint": f"arXivの分類（{html.unescape(name)}）", "source": "arxiv"})
    return out


def awesome_seeds(raw: Path) -> list[dict]:
    """Go、Rust、Swift、Python、機械学習のawesomeリストの項目名を種にする。"""
    labels = {
        "go": "Goのライブラリやツール",
        "rust": "Rustのライブラリやツール",
        "swift": "Swiftのライブラリやツール",
        "python": "Pythonのライブラリやツール",
        "ml": "機械学習のライブラリやツール",
    }
    out = []
    for key, label in labels.items():
        for line in (raw / f"awesome_{key}.md").read_text().splitlines():
            m = AWESOME_RE.match(line)
            if m and is_clean(m.group(1).strip()):
                out.append({"term": m.group(1).strip(), "hint": f"awesome-{key}に載っている{label}", "source": f"awesome-{key}"})
    return out


def main() -> None:
    raw, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    seeds = [{"term": t, "hint": "ユーザーの研究分野で必要な用語", "source": "must"} for t in MUST_INCLUDE]
    seeds += pwc_seeds(raw) + list_seeds(raw) + hf_seeds(raw) + arxiv_seeds(raw) + awesome_seeds(raw)
    # 同じ文字列の種は最初の出どころだけを残す（mustを優先し、以下は並べた順）
    uniq: dict[str, dict] = {}
    for s in seeds:
        uniq.setdefault(s["term"].strip().lower(), s)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for s in uniq.values():
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for s in uniq.values():
        counts[s["source"]] = counts.get(s["source"], 0) + 1
    print(f"seeds={len(uniq)}", counts)


if __name__ == "__main__":
    main()
