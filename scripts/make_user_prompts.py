"""本人の録音（dev-user）で読む台本を作る。

valの文から読み上げ用の50件を発話の種類と長さで層別に選び、台本なしで話す自由発話の題を50件加える。
自由発話の正解文は録音後に最良の系で下書きを作り、本人が直す。
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAL_PATH = ROOT / "data/text/val.jsonl"
OUT_PATH = ROOT / "data/user-prompts/dev-user.jsonl"

# 読み上げにかかる秒数の範囲。短すぎる文と、一息で読めない長い文を避ける。
MIN_SECONDS, MAX_SECONDS = 4.0, 20.0
SCRIPTED_COUNT = 50
SEED = 0

# 自由発話の題。日常の使い方（チャット、研究メモ、AIへの指示）に近く、技術用語が自然に出るものにする。
FREE_TOPICS = [
    "今取り組んでいる研究の進捗を、使っているモデルやライブラリの名前を交えて話してください。",
    "最近読んだ論文の手法を、同僚に説明するつもりで話してください。",
    "今日やった作業を、日報としてチャットに書く内容で話してください。",
    "AIのコーディング支援に、直してほしいバグの内容を指示してください。",
    "AIのコーディング支援に、新しく作りたい機能を説明してください。",
    "共同研究者に、実験の設定を変えたいと相談するメッセージを話してください。",
    "学習が失敗した原因について、考えられることを順に話してください。",
    "使っている開発環境（エディタ、ターミナル、ツール）を紹介してください。",
    "GPUサーバーの使い方のルールを、後輩に説明してください。",
    "データセットの前処理の手順を説明してください。",
    "評価指標の選び方について、意見を話してください。",
    "最近気になっている技術ニュースについて話してください。",
    "コードレビューのコメントとして、気になった点を指摘してください。",
    "プルリクエストの説明文を口頭で話してください。",
    "来週の作業予定を箇条書きにするつもりで話してください。",
    "発表のスライドの構成を考えながら話してください。",
    "メールで先生に進捗を報告する文を話してください。",
    "環境構築でつまずいたことと、その解決方法を話してください。",
    "好きなプログラミング言語とその理由を話してください。",
    "画像認識のモデルの比較結果を説明してください。",
    "ハイパーパラメータの探索をどう進めたかを話してください。",
    "途中で言い直しをしながら、明日の予定を話してください。",
    "えーと、などを気にせず、思いつくままに今日の昼食の話をしてください。",
    "AIに、文章を要約してほしいと依頼してください。",
    "AIに、エラーメッセージの意味を教えてほしいと依頼してください。",
]


def load_jsonl(path: Path) -> list[dict]:
    """JSONLを読み込んで辞書のリストを返す。"""
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pick_scripted(rows: list[dict], rng: random.Random) -> list[dict]:
    """発話の種類（先頭のtag、無ければ`none`）ごとに均等になるよう読み上げ用の文を選ぶ。"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if MIN_SECONDS <= row.get("est_seconds", 0) <= MAX_SECONDS:
            buckets[(row.get("tags") or ["none"])[0]].append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    picked: list[dict] = []
    while len(picked) < SCRIPTED_COUNT and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(picked) < SCRIPTED_COUNT:
                picked.append(buckets[key].pop())
    return picked


def main() -> None:
    """台本を書き出す。読み上げ用は英字の用語を英字のまま見せ、本人が普段どおりに発音できるようにする。"""
    rng = random.Random(SEED)
    scripted = pick_scripted(load_jsonl(VAL_PATH), rng)
    out: list[dict] = []
    for i, row in enumerate(scripted):
        prompt = dict(row)
        prompt["source_id"] = row["id"]
        prompt["id"] = f"dev-user-s{i:03d}"
        prompt["spoken_text"] = row["spoken_text_mixed"]
        prompt["prompt_kind"] = "scripted"
        out.append(prompt)
    for i, topic in enumerate(FREE_TOPICS * 2):
        out.append({
            "id": f"dev-user-f{i:03d}",
            "spoken_text": f"【自由発話】{topic}（10〜30秒）",
            "target_text": "",
            "terms": [],
            "glossary": [],
            "tags": [],
            "fillers": None,
            "prompt_kind": "free",
        })
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(out)}件を書き出しました: {OUT_PATH}")


if __name__ == "__main__":
    main()
