"""動作確認用の小さなデータ`dev-say`を、macOSの`say`で読み上げて作る。

日英混在の技術的な発話40文（フィラー、言い直し、カタカナ読みの用語、短文と長文を含む）を
日本語の声で読み上げ、16kHzモノラル16bitのWAVと`docs/PLAN.md`の形式のmanifestを出力する。
このデータは配管の確認用で、結論には使わない。

実行（手元のMac、作業ツリーで）：
    uv run python scripts/make_dev_say.py --out /Users/marutyan/PrivateDev/voiceIME/data/dev-say
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

# 読み上げに使う日本語の声。`say -v '?'`で確認した名前で、同名の他言語の声と区別するため地域名まで書く。
VOICES = [
    "Kyoko",
    "Eddy (Japanese (Japan))",
    "Flo (Japanese (Japan))",
    "Reed (Japanese (Japan))",
    "Sandy (Japanese (Japan))",
    "Shelley (Japanese (Japan))",
]

# 各発話の定義：(読み上げる文, 整形後に期待する文, [(用語の表記, 読み)], フィラーの数)。
# 読み上げる文の用語は、カタカナで書いたもの（`say`がカタカナ読みする）と英字のままのものを混ぜる。
# 言い直し（「いや」「じゃなくて」）は正解文から訂正前の内容を除く。フィラーの数に言い直しの語は含めない。
UTTERANCES: list[tuple[str, str, list[tuple[str, str]], int]] = [
    # 短文
    ("ギットハブにプッシュしました。", "GitHubにプッシュしました。", [("GitHub", "ギットハブ")], 0),
    ("えーと、ドッカーを再起動します。", "Dockerを再起動します。", [("Docker", "ドッカー")], 1),
    ("PyTorchのバージョンを上げます。", "PyTorchのバージョンを上げます。", [("PyTorch", "パイトーチ")], 0),
    ("あの、ジェイソンで返してください。", "JSONで返してください。", [("JSON", "ジェイソン")], 1),
    ("クーダが見つからないです。", "CUDAが見つからないです。", [("CUDA", "クーダ")], 0),
    ("Slackに貼っておきます。", "Slackに貼っておきます。", [("Slack", "スラック")], 0),
    ("まあ、エムエルエックスで十分速いです。", "MLXで十分速いです。", [("MLX", "エムエルエックス")], 1),
    (
        "ラグの、いや、エンベディングの精度が低いです。",
        "Embeddingの精度が低いです。",
        [("Embedding", "エンベディング")],
        0,
    ),
    ("ウブントゥでビルドが落ちます。", "Ubuntuでビルドが落ちます。", [("Ubuntu", "ウブントゥ")], 0),
    ("えー、Colabのセッションを止めました。", "Colabのセッションを止めました。", [("Colab", "コラボ")], 1),
    ("ローラで微調整します。", "LoRAで微調整します。", [("LoRA", "ローラ")], 0),
    ("なんか、ブイエスコードが重いです。", "VS Codeが重いです。", [("VS Code", "ブイエスコード")], 1),
    ("ウィスパーの小さいモデルを試します。", "Whisperの小さいモデルを試します。", [("Whisper", "ウィスパー")], 0),
    # 中くらいの文（10秒前後）
    (
        "えーと、トランスフォーマーのアテンションの部分を、もう少し軽くしたいんですけど、何かいい方法ありますか。",
        "TransformerのAttentionの部分をもう少し軽くしたいんですけど、何かいい方法ありますか。",
        [("Transformer", "トランスフォーマー"), ("Attention", "アテンション")],
        1,
    ),
    (
        "ハギングフェイスからモデルをダウンロードして、エムエルエックスの形式に変換してから、手元のマックで動かします。",
        "Hugging FaceからモデルをダウンロードしてMLXの形式に変換してから、手元のMacで動かします。",
        [("Hugging Face", "ハギングフェイス"), ("MLX", "エムエルエックス"), ("Mac", "マック")],
        0,
    ),
    (
        "あの、バッチサイズを三十二に、いや、十六に下げたら、ブイラムに収まりました。",
        "バッチサイズを16に下げたら、VRAMに収まりました。",
        [("VRAM", "ブイラム")],
        1,
    ),
    (
        "GitHub Actionsのワークフローで、pytestが失敗しているので、ログを確認してもらえますか。",
        "GitHub Actionsのワークフローでpytestが失敗しているので、ログを確認してもらえますか。",
        [("GitHub Actions", "ギットハブアクションズ"), ("pytest", "パイテスト")],
        0,
    ),
    (
        "まあ、とりあえずパンダスでシーエスブイを読み込んで、欠損値を確認してみましょう。",
        "とりあえずpandasでCSVを読み込んで、欠損値を確認してみましょう。",
        [("pandas", "パンダス"), ("CSV", "シーエスブイ")],
        1,
    ),
    (
        "えー、リアクトのコンポーネントが二回レンダリングされる問題は、ストリクトモードのせいだと思います。",
        "Reactのコンポーネントが2回レンダリングされる問題は、Strict Modeのせいだと思います。",
        [("React", "リアクト"), ("Strict Mode", "ストリクトモード")],
        1,
    ),
    (
        "ポスグレのインデックスを張ったら、クエリが十倍くらい速くなりました。",
        "PostgreSQLのインデックスを張ったら、クエリが10倍くらい速くなりました。",
        [("PostgreSQL", "ポスグレ")],
        0,
    ),
    (
        "うーん、その、ラーニングレートが高すぎて、ロスが発散しているかもしれないです。",
        "learning rateが高すぎて、lossが発散しているかもしれないです。",
        [("learning rate", "ラーニングレート"), ("loss", "ロス")],
        2,
    ),
    (
        "クバネティスのポッドが、えーと、メモリ不足で落ちているみたいです。",
        "KubernetesのPodがメモリ不足で落ちているみたいです。",
        [("Kubernetes", "クバネティス"), ("Pod", "ポッド")],
        1,
    ),
    (
        "OpenAIのAPIキーを環境変数に入れて、FastAPIのサーバーから呼び出します。",
        "OpenAIのAPIキーを環境変数に入れて、FastAPIのサーバーから呼び出します。",
        [("OpenAI", "オープンエーアイ"), ("API", "エーピーアイ"), ("FastAPI", "ファストエーピーアイ")],
        0,
    ),
    (
        "あの、タイプスクリプトの型エラーが、えー、三十件くらい出ています。",
        "TypeScriptの型エラーが30件くらい出ています。",
        [("TypeScript", "タイプスクリプト")],
        2,
    ),
    (
        "ダブリューアンドビーで学習曲線を見ると、エポック五あたりから過学習しています。",
        "W&Bで学習曲線を見ると、epoch 5あたりから過学習しています。",
        [("W&B", "ダブリューアンドビー"), ("epoch", "エポック")],
        0,
    ),
    (
        "ドッカーファイルの、いや、ドッカーコンポーズの設定を見直してください。",
        "Docker Composeの設定を見直してください。",
        [("Docker Compose", "ドッカーコンポーズ")],
        0,
    ),
    (
        "えっと、ヨロで物体検出をしてから、セグメントエニシングでマスクを作ります。",
        "YOLOで物体検出をしてから、Segment Anythingでマスクを作ります。",
        [("YOLO", "ヨロ"), ("Segment Anything", "セグメントエニシング")],
        1,
    ),
    (
        "Xcodeでビルドすると、SwiftUIのプレビューが、なんか固まるんですよね。",
        "Xcodeでビルドすると、SwiftUIのプレビューが固まるんですよね。",
        [("Xcode", "エックスコード"), ("SwiftUI", "スウィフトユーアイ")],
        1,
    ),
    # 長文
    (
        "えーと、今日のミーティングでは、まず、ラグのパイプラインの評価結果を共有して、そのあと、エンベディングモデルを、"
        "あの、オープンエーアイのものから、オープンソースのものに切り替えるかどうかを決めたいと思います。",
        "今日のミーティングでは、まずRAGのパイプラインの評価結果を共有して、そのあとEmbeddingモデルを"
        "OpenAIのものからオープンソースのものに切り替えるかどうかを決めたいと思います。",
        [("RAG", "ラグ"), ("Embedding", "エンベディング"), ("OpenAI", "オープンエーアイ")],
        2,
    ),
    (
        "学習はコラボのエーワンハンドレッドで回して、チェックポイントはグーグルドライブに保存して、"
        "推論だけ手元のエムスリープロで動かす予定です。",
        "学習はColabのA100で回して、checkpointはGoogle Driveに保存して、推論だけ手元のM3 Proで動かす予定です。",
        [
            ("Colab", "コラボ"),
            ("A100", "エーワンハンドレッド"),
            ("checkpoint", "チェックポイント"),
            ("Google Drive", "グーグルドライブ"),
            ("M3 Pro", "エムスリープロ"),
        ],
        0,
    ),
    (
        "あの、さっきのプルリクなんですけど、リベースしたらコンフリクトが出たので、えー、マージは明日に、いや、今日の夕方にやります。",
        "さっきのPRなんですけど、rebaseしたらconflictが出たので、mergeは今日の夕方にやります。",
        [("PR", "プルリク"), ("rebase", "リベース"), ("conflict", "コンフリクト"), ("merge", "マージ")],
        2,
    ),
    (
        "えっと、ラマの八ビーを四ビットに量子化して、エムエルエックスエルエムで動かしてみたら、一秒あたり四十トークンくらい出ました。",
        "Llamaの8Bを4bitに量子化して、MLX-LMで動かしてみたら、1秒あたり40トークンくらい出ました。",
        [("Llama", "ラマ"), ("MLX-LM", "エムエルエックスエルエム")],
        1,
    ),
    (
        "パイソンの仮想環境はユーブイで管理して、依存関係はパイプロジェクトトムルに書いておけば、ほかの人も同じ環境を再現できます。",
        "Pythonの仮想環境はuvで管理して、依存関係はpyproject.tomlに書いておけば、ほかの人も同じ環境を再現できます。",
        [("Python", "パイソン"), ("uv", "ユーブイ"), ("pyproject.toml", "パイプロジェクトトムル")],
        0,
    ),
    (
        "なんか、ネクストジェイエスのアップデートのあとから、ビルドがすごく遅くなっていて、えー、ターボパックを無効にすると、まあ、元に戻るみたいです。",
        "Next.jsのアップデートのあとから、ビルドがすごく遅くなっていて、Turbopackを無効にすると元に戻るみたいです。",
        [("Next.js", "ネクストジェイエス"), ("Turbopack", "ターボパック")],
        3,
    ),
    (
        "評価にはシーイーアールと、用語の正答率を使って、ベースラインのウィスパーラージブイスリーと比べて、差が一ポイント以内なら合格とします。",
        "評価にはCERと用語の正答率を使って、ベースラインのWhisper large-v3と比べて、差が1ポイント以内なら合格とします。",
        [("CER", "シーイーアール"), ("Whisper large-v3", "ウィスパーラージブイスリー")],
        0,
    ),
    (
        "あの、オースのトークンの有効期限が切れていて、えー、リフレッシュトークンで再取得する処理が、その、うまく動いていないようです。",
        "OAuthのトークンの有効期限が切れていて、refresh tokenで再取得する処理がうまく動いていないようです。",
        [("OAuth", "オース"), ("refresh token", "リフレッシュトークン")],
        3,
    ),
    (
        "AWSのLambdaからS3にファイルを書き込むときに、IAMのロールの権限が足りなくて、AccessDeniedのエラーが出ています。",
        "AWSのLambdaからS3にファイルを書き込むときに、IAMのロールの権限が足りなくて、AccessDeniedのエラーが出ています。",
        [
            ("AWS", "エーダブリューエス"),
            ("Lambda", "ラムダ"),
            ("S3", "エススリー"),
            ("IAM", "アイアム"),
            ("AccessDenied", "アクセスデナイド"),
        ],
        0,
    ),
    (
        "えーと、ビジョントランスフォーマーとレズネットを、同じデータ拡張と同じエポック数で比べて、そのあと、アブレーションをやります。",
        "Vision TransformerとResNetを、同じデータ拡張と同じepoch数で比べて、そのあとablationをやります。",
        [
            ("Vision Transformer", "ビジョントランスフォーマー"),
            ("ResNet", "レズネット"),
            ("epoch", "エポック"),
            ("ablation", "アブレーション"),
        ],
        1,
    ),
    (
        "Core MLに変換したモデルを、ニューラルエンジンで動かすと、GPUより消費電力が少なくて、まあ、バッテリーの持ちがかなり良くなります。",
        "Core MLに変換したモデルをNeural Engineで動かすと、GPUより消費電力が少なくて、バッテリーの持ちがかなり良くなります。",
        [("Core ML", "コアエムエル"), ("Neural Engine", "ニューラルエンジン"), ("GPU", "ジーピーユー")],
        1,
    ),
    (
        "うーん、テラフォームで作ったリソースと、手で作ったリソースが混ざっていて、えーと、ステートファイルが、あの、"
        "実際の状態とずれているので、インポートし直します。",
        "Terraformで作ったリソースと手で作ったリソースが混ざっていて、stateファイルが実際の状態とずれているので、importし直します。",
        [("Terraform", "テラフォーム"), ("state", "ステート"), ("import", "インポート")],
        3,
    ),
]


def synthesize_wav(text: str, voice: str, wav_path: Path) -> None:
    """`say`でAIFFへ読み上げ、ffmpegで16kHzモノラル16bitのWAVへ変換する（副作用：ファイル出力）。"""
    with tempfile.TemporaryDirectory() as tmp:
        aiff_path = Path(tmp) / "say.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(aiff_path), text], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff_path),
             "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(wav_path)],
            check=True,
        )


def build_record(index: int, voice: str) -> dict:
    """`UTTERANCES[index]`から`docs/PLAN.md`の形式のmanifestの1行を作る。"""
    spoken, target, terms, fillers = UTTERANCES[index]
    utt_id = f"dev-say-{index + 1:04d}"
    return {
        "id": utt_id,
        "split": "dev",
        "audio_path": f"audio/{utt_id}.wav",
        "spoken_text": spoken,
        "target_text": target,
        "terms": [surface for surface, _ in terms],
        "glossary": [{"surface": surface, "readings": [reading]} for surface, reading in terms],
        "speaker": f"say-{voice.split(' ')[0].lower()}",
        "source": "macos-say",
        "domain": "tech-mixed",
        "fillers": fillers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="出力先（manifest.jsonlとaudio/を置く）")
    args = parser.parse_args()

    audio_dir = args.out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, (spoken, _, _, _) in enumerate(UTTERANCES):
        # 声は順番に割り当て、各声に短文と長文が混ざるようにする。
        voice = VOICES[index % len(VOICES)]
        record = build_record(index, voice)
        synthesize_wav(spoken, voice, args.out / record["audio_path"])
        records.append(record)
    with open(args.out / "manifest.jsonl", "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{len(records)}件を{args.out}へ書き出した")


if __name__ == "__main__":
    main()
