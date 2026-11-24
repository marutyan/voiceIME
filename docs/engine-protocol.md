# アプリと認識エンジンの通信形式

Swift製のアプリ（起動キー、録音、区切り、貼り付けを担う）と、Python製の認識エンジン（ASRと整形を担う）は、エンジンの標準入出力で1行1件のJSONをやり取りする。モデルを差し替えてもアプリを変えずに済むよう、この境界で分ける。

## 役割

| 担当 | 役割 |
| --- | --- |
| アプリ | 起動キーの監視、録音、無音での区切り、区間ごとのWAVの書き出し、宛先の照合、貼り付け、クリップボードの復元、状態の表示 |
| エンジン | モデルの読み込みとwarm-up、区間ごとの認識、用語集の適用、整形、出力の検査、履歴の記録 |

## 音声の受け渡し

- アプリは録音中、無音が600ms続いた時点、または区間が20秒に達した時点で区間を確定し、16kHz・モノラル・16bitのWAVを一時ディレクトリへ書き出して、そのパスを送る。
- 無音の判定に使う音量のしきい値は、録音開始直後の約300msから背景雑音を測って決める。
- 一時ファイルは、エンジンが結果を返した後にアプリが消す。

## アプリからエンジンへ

```json
{"type": "start", "session_id": "s-0001", "app": {"bundle_id": "com.apple.dt.Xcode", "name": "Xcode"}}
{"type": "segment", "session_id": "s-0001", "seq": 0, "wav_path": "/tmp/voiceime/s-0001-0.wav"}
{"type": "finish", "session_id": "s-0001", "mode": "formatted"}
{"type": "cancel", "session_id": "s-0001"}
{"type": "shutdown"}
```

- `start`：録音を始めた時点で送る。エンジンはこれを受けて、整形用LLMの準備（KVキャッシュの用意など）を始めてよい。任意の欄`screen_text`（文字列、最大4,000字）に、録音開始時に前面ウィンドウを文字認識した結果を入れる。エンジンはこれを用語のヒントに使う（用語集の`surface`が画面に現れた語を優先してASRへ渡し、整形LLMへの参考にも加える）。画面の文字は履歴に保存しない。
- `segment`：区間を確定するたびに送る。`seq`は0から連番。エンジンは受け取った区間から順に認識を進める。
- `finish`：キーを離した時点で、最後の区間を送った直後に送る。`mode`は`formatted`（整形する）か`raw`（整形せず認識結果だけ返す）。
- `cancel`：録音を取り消した場合。エンジンはその`session_id`の処理を捨て、結果を返さない。

## エンジンからアプリへ

```json
{"type": "ready", "asr": "haas-ja-v1.0-q8_0", "formatter": "qwen3.5-0.8b-ft-4bit"}
{"type": "partial", "session_id": "s-0001", "seq": 0, "text": "えーと パイトーチの"}
{"type": "result", "session_id": "s-0001", "raw_text": "えーと パイトーチのデータローダーで", "text": "PyTorchのDataLoaderで", "format_ok": true, "asr_latency_s": 0.12, "format_latency_s": 0.18, "total_latency_s": 0.31}
{"type": "error", "session_id": "s-0001", "message": "..."}
```

- `ready`：モデルの読み込みとwarm-upを終えた時点で一度だけ送る。アプリはこれを受けるまで録音を受け付けない。
- `partial`：区間ごとの認識結果（表示用、任意）。
- `result`：`finish`の後に一度だけ送る。`text`は貼り付ける文。整形に失敗した場合や出力の検査に落ちた場合は、`format_ok`を`false`にし、`text`には`raw_text`を入れる。
- `total_latency_s`：`finish`を受けてから`result`を送るまでの時間。
- `error`：処理を続けられない場合。アプリは`raw_text`があればそれを、無ければ何も貼らずに通知する。

## 設定と保存先

- 置き場所：`~/Library/Application Support/voiceIME/`
- 本人用の用語集：この置き場所か、リポジトリの`data/user/`に`glossary.jsonl`を置く。書き方は[記入例](../data/user/glossary.example.jsonl)を参照。
- 履歴：`history.jsonl`（整形前の文、整形後の文、遅延、宛先のアプリ名）。ファイルの権限は本人だけが読み書きできる`0600`とする。
- エンジンの起動：アプリが`uv run --project <リポジトリ> python -m voiceime.engine`を子プロセスとして起動する。

本人用の用語集は1行に1語を書く。`surface`に出したい表記、`readings`に追加したい読みを書く。同じ`surface`が学習用の用語集にあれば、既存の読みとまとめて使う。変更はエンジンの再起動時に読み込む。

実際の認識文に出る誤表記は、任意の`aliases`に文字列の配列で登録する。完全一致した箇所を整形の前に`surface`へ直す。ひらがなは助詞が続いても一致し、カタカナや英数字の語中では一致しない。同じ別名が複数の表記に登録されている場合は置換を見送る。
