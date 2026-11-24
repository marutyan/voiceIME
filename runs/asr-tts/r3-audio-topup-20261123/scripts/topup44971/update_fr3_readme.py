#!/usr/bin/env python3
"""検証済みのASR出力とomitted_termsの集計を整形担当のREADMEに追記する。"""

from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path


OUTPUTS = Path.home() / "voiceime-work-asr/r3-multiasr-train-20261123/outputs"
README = Path.home() / "voiceime-work-fr3/repo/README.md"


def omitted_row(label: str, data: dict[str, int]) -> str:
    """表へ載せる件数を、同じ分母と区分の順序で並べる。"""
    keys = ("rows_with_omitted_terms", "rows_with_any_hit", "rows_with_all_hits", "rows_with_no_hit")
    return "| " + " | ".join([label, *(f"{data[key]:,}" for key in keys)]) + " |"


def main() -> None:
    """出力の検証が成功した段階ごとに、README末尾へ1回だけ追記する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("preview", "final"))
    parser.add_argument("--metadata", type=Path, help="最終出力を検証した集計JSON")
    args = parser.parse_args()
    if args.stage == "preview":
        title = "## 第3弾の追加学習音声 ASR先行分（22,000件）"
        data = json.loads((OUTPUTS / "preview-topup44971-summary.json").read_text())
        if data["rows"] != 22_000 or not Path(data["path"]).is_file():
            raise ValueError("先行22,000件の完成品がない")
        body = f"""合成済みの音声から先行した22,000件は、facultyの
`~/voiceime-work-asr/r3-multiasr-train-20261123/outputs/train-topup44971-preview22000.jsonl`
にある。各行の形式は`train-available-12000.jsonl`と同じで、IDが重ならない。
既存12,000件と連結して34,000件として使える。最終の追加ファイルにはこの先行分も含まれる。

先行分のうち、`omitted_terms`がある行は{data["omitted_terms"]["rows_with_omitted_terms"]:,}件あり、
そのうち少なくとも1語の表記が`formatter_glossary`に入ったのは{data["omitted_terms"]["rows_with_any_hit"]:,}件。
照合は同じ行の`surface`の完全一致で行った。用語一覧と教師文は生成時の内容を保存した。
"""
    else:
        if args.metadata is None:
            parser.error("finalでは--metadataが必要")
        data = json.loads(args.metadata.read_text())
        counts = data["row_counts"]
        topup = counts["topup"]
        full = counts["full_train"]
        missing = data["results"]["missing_ids"]
        if (
            topup + len(missing) != 44_971
            or full != topup + 12_000
            or counts["topup_unique"] != topup
            or counts["topup_missing"] != len(missing)
            or counts["overlap"] != 0
        ):
            raise ValueError("追加分の件数・重複・欠落の照合が済んでいない")
        title = f"## 第3弾の追加学習音声 ASR最終結果（{topup:,}件）"
        omitted = data["results"]["omitted_terms"]
        table = "\n".join(omitted_row(label, omitted[key]) for label, key in (
            (f"追加{topup:,}件", "topup"), ("既存12,000件", "previous"), (f"結合後{full:,}件", "full_train"),
        ))
        paths = {key: Path(item["path"]).name for key, item in data["results"]["outputs"].items()}
        missing_note = "元のtrainからの欠落は0件。"
        if missing:
            descriptions = "、".join(
                f"`{record_id}`（{data['confirmed_tts_failures'][record_id]['reason']}）" for record_id in missing
            )
            missing_note = f"元のtrainからの欠落は{len(missing)}件。音声長の条件を満たさなかった{descriptions}が欠けている。"
        body = f"""保存先はfacultyの`~/voiceime-work-asr/r3-multiasr-train-20261123/outputs/`。
`train-available-12000.jsonl`と`{paths["combined"]}`を連結すると、利用できるtrainは{full:,}件になる。
IDの重複は0件。{missing_note}
先行22,000件のJSONLは追加{topup:,}件に含まれる。
valは既存の`val-1000.jsonl`を使う。

| ファイル | 件数 | 内容 |
| --- | ---: | --- |
| `{paths["combined"]}` | {topup:,} | 既存trainと同じ形式。Haas初回・2回目・segment-merge、Qwen3-ASR 0.6B初回、用語一覧（最大20語） |
| `{paths["haas"]}` | {topup:,} | ヒントなしのHaas初回認識 |
| `{paths["qwen"]}` | {topup:,} | Qwen3-ASR 0.6B初回認識 |
| `{paths["omitted_term_matches"]}` | {omitted["full_train"]["rows_with_omitted_terms"]:,} | `omitted_terms`がある行の照合結果 |
| `{args.metadata.name}` | — | 条件、IDのSHA-256、件数、実行時間、GPU使用率 |

音声manifestは`~/voiceime-work-tts/outputs/r3-audio-topup-20261123/manifest.jsonl`。
各行の`audio_path`はmanifestのディレクトリからの相対パス。

`omitted_terms`の`surface`を同じ行の`formatter_glossary`と完全一致で照合した。
集計は行単位で、複数語を持つ行のために「1語以上」と「全語」を併記する。

| 対象 | omitted語のある行 | 1語以上一致 | 全語一致 | 一致なし |
| --- | ---: | ---: | ---: | ---: |
{table}

`{paths["omitted_term_matches"]}`は、`id`、`omitted_terms`（表記の配列）、
`omitted_terms_in_formatter_glossary`（一致した表記の配列）、`omitted_term_count`、`omitted_term_hit_count`を持つ。
元の教師文は該当語をカタカナで表記している。照合後も教師文と用語一覧は保持しているため、教師文の調整はこの照合結果をIDで結合して行える。
"""
    if not README.is_file():
        raise FileNotFoundError(README)
    with README.open("a+", encoding="utf-8") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.seek(0)
        if title not in output.read().splitlines():
            output.write(f"\n{title}\n\n{body}")
    print(f"{README}: {title.removeprefix('## ')}")


if __name__ == "__main__":
    main()
