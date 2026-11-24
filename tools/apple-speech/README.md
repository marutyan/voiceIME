# apple-speech

macOS標準の音声認識（Speech frameworkの `SpeechAnalyzer` と `DictationTranscriber` / `SpeechTranscriber`）を使って音声ファイルを文字起こしするコマンドと、評価用の本人音声を録音するコマンドをまとめた Swift Package です。外部の Swift パッケージは使わず、macOS 標準フレームワークのみで構成しています。

## 動作要件

- macOS 26 以降（開発・確認環境：macOS 27.3 / Apple M3 Pro / Swift 6.4.2 / SDK 27.2）
- Xcode Command Line Tools または Xcode

## ビルド方法

```bash
cd tools/apple-speech
swift build -c release
```

ビルドが通ると、次の場所に実行ファイルが生成されます（環境によっては `swift build -c release --show-bin-path` で正確なパスを確認できます）。

- `.build/release/apple-transcribe`
- `.build/release/record-prompts`

単体テスト（引数解析、JSONL読み書き、WAV生成、音声ローダ）を実行する場合：

```bash
cd tools/apple-speech
swift test
```

---

## 1. `apple-transcribe`（音声ファイルの文字起こし）

manifest JSONL に記載された音声ファイルを順に認識し、結果を1行ずつの JSONL として出力します。

### オプション

| オプション | 必須 | 既定値 | 説明 |
| --- | --- | --- | --- |
| `--manifest <path>` | 必須 | — | 入力 manifest JSONL のパス（各行に `id`、`audio_path`、任意で `glossary` を含む） |
| `--out <path>` | 必須 | — | 出力 JSONL のパス（親ディレクトリが無ければ自動作成） |
| `--transcriber <dictation\|speech>` | 任意 | `dictation` | 使用するモジュール（`DictationTranscriber` または `SpeechTranscriber`） |
| `--locale <id>` | 任意 | `ja-JP` | 認識ロケール |
| `--use-glossary` | 任意 | 無効 | 各行の `glossary` の `surface` を `AnalysisContext.contextualStrings[.general]` へ渡す |
| `-h`, `--help` | 任意 | — | ヘルプを表示して終了 |

### 実行例

```bash
# DictationTranscriber（用語集なし）
tools/apple-speech/.build/release/apple-transcribe \
  --manifest data/test-synth/manifest.jsonl \
  --out runs/exp01/apple-dictation.jsonl \
  --transcriber dictation \
  --locale ja-JP

# DictationTranscriber（用語集あり）
tools/apple-speech/.build/release/apple-transcribe \
  --manifest data/test-synth/manifest.jsonl \
  --out runs/exp01/apple-dictation-glossary.jsonl \
  --transcriber dictation \
  --locale ja-JP \
  --use-glossary

# SpeechTranscriber
tools/apple-speech/.build/release/apple-transcribe \
  --manifest data/test-synth/manifest.jsonl \
  --out runs/exp01/apple-speech.jsonl \
  --transcriber speech \
  --locale ja-JP
```

### 出力形式と挙動

- 各発話ごとに次のJSONを1行ずつ追記・同期します。
  ```json
  {"id":"synth-000001","system":"apple-dictation","stage":"asr","hyp":"...","latency_s":0.284}
  ```
- `system` は `--transcriber` と `--use-glossary` の組み合わせで次の値になります。
  - `apple-dictation` / `apple-dictation-glossary`
  - `apple-speech` / `apple-speech-glossary`
- `audio_path` が相対パスの場合は、まず入力 manifest の親ディレクトリ基準で解決します。
- `latency_s` は、音声ファイルの読み込みと解析用フォーマットへの変換を終えた時点から、最終結果が確定するまでの経過時間（秒）です。`AssetInventory` による言語資産の準備と、先頭1発話を用いた初回実行（ウォームアップ）は最初に1回だけ行い、計測から除外します。
- 言語資産が未導入の場合は `AssetInventory` で自動的にダウンロード・インストールし、状態と進捗を標準エラー出力へ表示します。
- `DictationTranscriber`（`.shortDictation`）の結果は確定後も `isFinal` が false のまま届きます（`resultsFinalizationTime` が0のため）。そのため dictation では `isFinal` で絞らず、届いた結果を区間の開始時刻ごとに後着のもので置き換えて連結します。認識器が結果を1件も返さなかった発話は `hyp` が空文字になります。
- `--use-glossary` は `DictationTranscriber` でのみ有効とされているため、`--transcriber speech` と併用した場合は標準エラー出力へ警告を出します。

### 合成音声を使った動作確認の例

```bash
TMPDIR_DEMO=$(mktemp -d)
mkdir -p "$TMPDIR_DEMO/audio"

say -v Kyoko -o "$TMPDIR_DEMO/audio/s1.aiff" "パイトーチのデータローダーで読み込みます"
say -v Kyoko -o "$TMPDIR_DEMO/audio/s2.aiff" "えーと、トランスフォーマーのアテンション層を確認します"
say -v Kyoko -o "$TMPDIR_DEMO/audio/s3.aiff" "ギットハブのプルリクエストをマージしてください"

for id in s1 s2 s3; do
  afconvert -f WAVE -d LEI16@16000 -c 1 "$TMPDIR_DEMO/audio/$id.aiff" "$TMPDIR_DEMO/audio/$id.wav"
  rm "$TMPDIR_DEMO/audio/$id.aiff"
done

cat > "$TMPDIR_DEMO/manifest.jsonl" <<'EOF'
{"id":"s1","audio_path":"audio/s1.wav","glossary":[{"surface":"PyTorch","reading":"パイトーチ"},{"surface":"DataLoader","reading":"データローダー"}]}
{"id":"s2","audio_path":"audio/s2.wav","glossary":[{"surface":"Transformer","reading":"トランスフォーマー"},{"surface":"Attention","reading":"アテンション"}]}
{"id":"s3","audio_path":"audio/s3.wav","glossary":[{"surface":"GitHub","reading":"ギットハブ"}]}
EOF

tools/apple-speech/.build/release/apple-transcribe \
  --manifest "$TMPDIR_DEMO/manifest.jsonl" \
  --out "$TMPDIR_DEMO/dictation.jsonl" \
  --transcriber dictation \
  --locale ja-JP

tools/apple-speech/.build/release/apple-transcribe \
  --manifest "$TMPDIR_DEMO/manifest.jsonl" \
  --out "$TMPDIR_DEMO/speech.jsonl" \
  --transcriber speech \
  --locale ja-JP

cat "$TMPDIR_DEMO/dictation.jsonl"
cat "$TMPDIR_DEMO/speech.jsonl"
rm -rf "$TMPDIR_DEMO"
```

---

## 2. `record-prompts`（評価用音声の録音）

プロンプト JSONL（各行に `id` と `spoken_text`）を端末へ1件ずつ表示し、マイクから 16kHz モノラル 16bit WAV を録音します。

### オプション

| オプション | 必須 | 説明 |
| --- | --- | --- |
| `--manifest <prompts.jsonl>` | 必須 | 入力プロンプト JSONL のパス（各行に `id` と `spoken_text` を含む） |
| `--out-dir <dir>` | 必須 | 出力先ディレクトリ（`<dir>/audio/<id>.wav` と `<dir>/manifest.jsonl` を保存） |
| `-h`, `--help` | 任意 | ヘルプを表示して終了 |

### 実行例

```bash
tools/apple-speech/.build/release/record-prompts \
  --manifest data/test-user/prompts.jsonl \
  --out-dir data/test-user
```

### 対話操作

1件ずつ `id` と `spoken_text` が表示されます。

- `Enter`：録音開始 → もう一度 `Enter` で録音停止（長さと最大音量を表示）→ さらに `Enter` で保存して次へ
- `r` + `Enter`：取り直し（録音中・録音停止後のどちらでも可）
- `s` + `Enter`：この発話を飛ばす
- `q` + `Enter`（または `Ctrl-D`）：途中終了

### 出力と再開

- 録音音声は 16kHz・モノラル・16bit PCM の WAV 形式で `<out-dir>/audio/<id>.wav` に原子的に保存します。
- 保存のたびに、`<out-dir>/manifest.jsonl` へ元の行の全フィールドを引き継ぎ、`audio_path`（`"audio/<id>.wav"`）、`speaker: "user"`、`source: "user"`、`split: "test-user"` を加えて追記・同期します。
- 途中で終了しても保存済みの分は残ります。同じ `--out-dir` で再実行すると、`<out-dir>/manifest.jsonl` に記録済みの `id` を自動的に飛ばして未録音分から再開します。

---

## 必要な権限と実行環境

### マイク権限（`record-prompts`）

- 初回実行時にマイクアクセス許可ダイアログが表示されます。
- 権限はコマンドを実行しているターミナルアプリ（Terminal、iTerm2 等）に対して付与されます。
- 拒否された場合は、macOS の「システム設定 > プライバシーとセキュリティ > マイク」で使用中のターミナルアプリをオンにしてから再実行してください。

### 音声認識と言語資産（`apple-transcribe`）

- `SpeechAnalyzer`（`DictationTranscriber` / `SpeechTranscriber`）はオンデバイスで動作し、音声ファイルからの認識ではマイク権限は不要です。
- ただし、初回に日本語などの言語資産が未導入の場合は `AssetInventory` がモデルをダウンロードするため、インターネット接続が必要です。
- 厳格なサンドボックス配下ではシステム音声認識サービス（XPC / `AssetInventory`）への接続が拒否され、対応ロケールが空になったり利用不可エラーになる場合があります。通常のターミナル環境から実行してください。
