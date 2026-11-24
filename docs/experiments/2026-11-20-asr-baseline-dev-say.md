# ASR候補の比較（dev-sayとpilot-ttsでの動作確認）

## 仮説

- 日英混在の発話では、Whisper large-v3系に用語集を`initial_prompt`で渡すと、英語の用語を英字で書く割合が上がる。
- ASR単体の遅延の目安0.4秒（10秒の発話）は、Whisper large系のencoderが入力を30秒へ埋めるため満たせない。入力長に比例するtransducer系なら満たせる。

## 条件

- データ：`data/dev-say`（`say`の日本語6声で読み上げた40文、2.1〜16.1秒、`scripts/make_dev_say.py`）と、`data/pilot-tts`のtrainとvalの18発話（4.2〜7.2秒、test-synthの2発話は除いた）。どちらも配管の確認用で、結論には使わない。
- 実行：`uv run python -m voiceime.asr.run`（commit 9f562c4、f54481b）。warm-up 1回の後、1発話ずつ順に処理した。
- デコード：Whisper系は`transcribe`（mlx-whisperの既定。タイムスタンプと温度を上げたやり直しあり）と`greedy`（30秒の窓1つ、タイムスタンプなし、温度0、やり直しなし）。言語は`ja`。
- 用語集：各発話の`glossary`の表記を「、」でつないで`initial_prompt`へ渡した。発話に出る語だけを渡すので、正解を含む楽観的な条件である。
- 量子化：mlx-communityのfp16か、`voiceime.asr.convert`で変換したfp16を、`nn.quantize`（group size 64）で8bitと4bitにした。
- 結果：`runs/asr-baseline-dev-say/`、`runs/asr-latency-recheck-dev-say/`（遅延の2回目）、`runs/asr-baseline-pilot-tts/`。各系の`.meta.json`に重みの取得元、負荷、メモリを残した。
- 計測環境：他の担当がLLMとASRを同時に動かしていた。1回目のwhisper-large-v3の4系はswapが約6.5GBに達して遅延が1発話30〜200秒に崩れたため、測り直した値で置き換えた。

## 結果（暫定の指標）

CERと用語の一致は、評価の担当の実装ができるまでの暫定の計算である（NFKC、英字の小文字化、句読点と空白の除去。正解は`spoken_text`）。「読み揃え」は、用語集の表記を読みに置き換えてから比べたCERで、カタカナで書いたか英字で書いたかの差を除く。遅延は10秒前後（8〜12.5秒の15発話）の中央値で、2回目の計測の値を優先した。

| 系（dev-say） | CER | CER（読み揃え） | 用語の英字表記一致 | フィラー残存 | 遅延の中央値（10秒前後） | encoder | MLXのメモリ最大 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| whisper-large-v3.greedy | 17.1 | 12.2 | 22% | 82% | 1.78〜1.88秒 | 0.62秒 | 3.9GB |
| whisper-large-v3.greedy+glossary | 27.8 | 8.4 | 59% | 79% | 1.69秒 | 0.62秒 | 3.9GB |
| whisper-large-v3-turbo.greedy | 18.2 | 12.6 | 23% | 88% | 0.81秒 | 0.61秒 | 2.5GB |
| whisper-large-v3-turbo.greedy+glossary | 31.4 | 10.6 | 65% | 74% | 0.81秒 | 0.62秒 | 2.5GB |
| whisper-large-v3-turbo-q4.greedy | 18.7 | 12.9 | 23% | 85% | 0.74秒 | 0.65秒 | 1.3GB |
| kotoba-whisper-bilingual-v1.0.greedy | 15.0 | 14.0 | 10% | 56% | 0.75秒 | 0.61秒 | 2.4GB |
| kotoba-whisper-bilingual-v1.0-q4.greedy | 16.1 | 16.1 | 8% | 59% | 0.71秒 | 0.65秒 | 1.3GB |
| kotoba-whisper-v2.2.greedy | 16.2 | 15.9 | 10% | 53% | 0.75〜0.95秒 | 0.62秒 | 2.4GB |
| whisperkit-large-v3-v20240930_626MB.greedy | 18.7 | 13.1 | 23% | 88% | 1.24秒 | 0.61秒 | 0.2GB＋ANE |
| parakeet-tdt_ctc-0.6b-ja | 21.8 | 20.9 | 1% | 41% | 0.17秒 | 0.10秒 | 2.2GB |
| reazonspeech-k2-v2 | 32.7 | 33.3 | 8% | 18% | 0.22秒 | － | CPU、RSS 1.0GB |

pilot-tts（18発話）でのCER（読み揃え）は、whisperkit 626MB 8.8、large-v3 9.3、turbo 10.0、turbo＋用語集 9.3、kotoba-v2.2 12.4、kotoba-bilingual 14.0、Parakeet 17.4、ReazonSpeech 21.5だった。遅延の中央値（4〜7秒の発話）は、turbo 0.73秒、kotoba 0.68秒、large-v3 1.24秒、Parakeet 0.12秒、ReazonSpeech 0.11秒。

発話の長さと時間の関係は`runs/asr-latency-recheck-dev-say/figures/latency_vs_duration.png`に描いた。

## 分析

- Whisper large系のencoderは、発話が2秒でも16秒でも約0.61秒で一定だった。turboと量子化はdecoderだけを速くし、encoderは変わらない（4bitでも0.65秒）。GPUが空いている状態でencoderだけを10回測っても中央値0.62秒だった。そのため、Whisper large系でASR単体0.4秒は満たせない。
- 0.4秒に収まったのは、Parakeet（0.17秒）とReazonSpeech k2（0.22秒）だけである。ただしCER（読み揃え）はWhisper系より6〜20ポイント悪く、英語の用語はほとんど英字にならない。
- 用語集のプロンプトは、Whisperの英字表記の一致を22〜23%から59〜65%へ上げ、読み揃えのCERも2ポイント下げた。kotoba-whisperではほぼ効かなかった（10%前後のまま）。
- 存在しない文の生成（幻覚）は、全系で見つからなかった（出力が正解より大幅に長い、または同じ文字列の3回以上の繰り返しで検出）。

## 分かったこと

- 英語の用語：Whisper large系は「Docker」「GitHub」「GPU」など一般的な語を英字で書き、「パイトーチ」を「TYTorch」と書くような英字の誤りも出る。kotoba-whisperはほぼカタカナで書く。Parakeetは英字を小文字で書く（「gpu」「openai」）。
- フィラー：Whisper large系は「えーと」「あの」をほぼ残す（74〜88%）。kotoba-whisperは「えー」を「A」と書くことがある。ReazonSpeechは大半を落とすが、内容の語も落とす。用語集のプロンプトを渡すと、Whisperが文頭のフィラーを落とすことがある（「えーと、今日の」→「今日の」）。
- 言い直し（「いや」）は、ほぼすべての系で訂正前の語も含めてそのまま書き起こされた。ASRの段階では消えないので、整形で処理する必要がある。
- WhisperKitの`_turbo`版は、encoderが1.1〜1.5秒で、`_626MB`版（0.61秒）より遅かった。

## 次の仮説

- Whisper系を使う場合、encoderを30秒へ埋めずに発話の長さだけで動かす方法（音声の長さに合わせたencoder、または録音中に先にencoderを回す方式）で、ASRを0.4秒に近づけられるかを確かめる。
- Parakeetの日本語版に、用語集による偏り付け（parakeet-mlxの`boost`）を使い、英字の用語を出せるかを確かめる。
- 用語集を500語に増やすと、Whisperのプロンプトは223 tokenまでしか入らないため、渡し方（発話に関係する語の選び方）を決める必要がある。
