#!/usr/bin/env bash
# 作業ディレクトリに取得したダンプを展開し、記事本文を保存せずに読みを抽出する。
set -euo pipefail

dump=jawiki-20261101-pages-articles.xml.bz2
decoder=(bzip2 -dc)
if command -v lbzip2 >/dev/null; then
    # 共有サーバーでは並列展開のスレッド数を固定する。
    decoder=(lbzip2 -n 4 -dc)
fi
if [[ $# -eq 1 ]]; then
    # 取得中は同じファイルを先頭から追い、取得プロセスの終了で入力を閉じる。
    tail -c +1 --follow=descriptor --sleep-interval=0.2 --pid="$1" "$dump"
else
    cat "$dump"
fi | nice -n 15 "${decoder[@]}" | nice -n 15 python3 extract_jawiki.py - facts.jsonl.gz

printf '%s  %s\n' e1a1173c8ae5a844ab5fe89ff457f9c7b178b68d "$dump" | nice -n 15 sha1sum -c -
touch extract.ok
