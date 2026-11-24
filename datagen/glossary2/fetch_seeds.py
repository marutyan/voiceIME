"""用語集v2の種にする公開の一覧をダウンロードする。

実行場所：手元（Mac）。標準ライブラリだけで動く。
使い方：python datagen/glossary2/fetch_seeds.py <保存先ディレクトリ>
取得した日付は保存先の fetched_at.txt に書く（data/text/README.mdに転記する）。
ダウンロードしたファイルは信頼しないデータとして扱い、seeds.py で文字列として読むだけにする。
"""

from __future__ import annotations

import datetime
import sys
import time
import urllib.request
from pathlib import Path

# 取得する一覧（保存名 → URL）。各一覧の意味と選んだ理由は data/text/README.md に書く。
SOURCES: dict[str, str] = {
    # Papers with Codeの手法とデータセットの一覧（2025年の閉鎖時の保存版、CC BY-SA 4.0）
    "pwc_methods.parquet": "https://huggingface.co/api/datasets/pwc-archive/methods/parquet/default/train/0.parquet",
    "pwc_datasets.parquet": "https://huggingface.co/api/datasets/pwc-archive/datasets/parquet/default/train/0.parquet",
    # PyPIの直近30日のダウンロード数の上位（hugovk/top-pypi-packages）
    "pypi_top.json": "https://hugovk." + "github.io/top-pypi-packages/top-pypi-packages.min.json",
    # npmの依存数・ダウンロード数の上位（wooorm/npm-high-impact）
    "npm_top.js": "https://unpkg.com/npm-high-impact/lib/top.js",
    # Homebrewの直近365日のインストール数（コマンドとデスクトップアプリ）
    "brew_formula_365d.json": "https://formulae.brew.sh/api/analytics/install-on-request/365d.json",
    "brew_cask_365d.json": "https://formulae.brew.sh/api/analytics/cask-install/365d.json",
    "brew_cask.json": "https://formulae.brew.sh/api/cask.json",
    # Hugging Faceのダウンロード数といいね数の上位のモデルとデータセット
    "hf_models_downloads.json": "https://huggingface.co/api/models?sort=downloads&direction=-1&limit=1000",
    "hf_models_likes.json": "https://huggingface.co/api/models?sort=likes&direction=-1&limit=1000",
    "hf_datasets_downloads.json": "https://huggingface.co/api/datasets?sort=downloads&direction=-1&limit=1000",
    "hf_datasets_likes.json": "https://huggingface.co/api/datasets?sort=likes&direction=-1&limit=1000",
    # arXivの分類の一覧
    "arxiv_taxonomy.html": "https://arxiv.org/category_taxonomy",
    # Go、Rust、Swift、Pythonの定番ライブラリの一覧（awesomeリスト）
    "awesome_go.md": "https://raw.githubusercontent.com/avelino/awesome-go/main/README.md",
    "awesome_rust.md": "https://raw.githubusercontent.com/rust-unofficial/awesome-rust/main/README.md",
    "awesome_swift.md": "https://raw.githubusercontent.com/matteocrippa/awesome-swift/master/README.md",
    "awesome_python.md": "https://raw.githubusercontent.com/vinta/awesome-python/master/README.md",
    "awesome_ml.md": "https://raw.githubusercontent.com/josephmisiti/awesome-machine-learning/master/README.md",
}
# crates.ioのダウンロード数の上位（100件ずつのページ数）
CRATES_PAGES = 15
USER_AGENT = "glossary-seed-fetch/0.1"


def fetch(url: str, path: Path) -> None:
    """URLの中身をファイルへ保存する。失敗したら例外を投げて止める。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        path.write_bytes(resp.read())
    print(f"{path.name}: {path.stat().st_size} bytes")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        fetch(url, out / name)
    for page in range(1, CRATES_PAGES + 1):
        fetch(f"https://crates.io/api/v1/crates?sort=downloads&per_page=100&page={page}", out / f"crates_{page:02d}.json")
        time.sleep(1)  # crates.ioの利用規約（1秒に1件まで）に合わせる
    (out / "fetched_at.txt").write_text(datetime.datetime.now().astimezone().isoformat() + "\n")


if __name__ == "__main__":
    main()
