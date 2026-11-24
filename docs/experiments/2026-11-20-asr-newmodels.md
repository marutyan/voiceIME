# 新しいASR候補の比較（Qwen3-ASR、Granite Speech、Haas-ja、Nemotron、Voxtral）

## 仮説

- 入力の長さに比例して計算するencoderと、短いdecoderを持つ方式なら、10秒の発話でASR単体0.4秒に収まる。
- 用語集を入れられる方式（Qwen3-ASRのsystem message、Granite Speechの`Keywords:`、Haasの`keywords`）は、Whisper turbo＋用語集と同じかそれ以上に、英語の用語を英字で書ける。

## 条件

- データ：`data/dev-say`（40発話）と、`data/pilot-tts`のtrainとvalの18発話（test-synthの2発話は除いた）。どちらも配管の確認用で、結論には使わない。
- 実行：`uv run python -m voiceime.asr.run`（commit e0765af）。warm-up 1回の後、1発話ずつ順に処理した。計測中、手元で他の担当の重い処理は動いていなかった（PMの連絡と、各`.meta.json`の上位プロセスの記録による）。
- 比較の基準として、Whisper large-v3-turbo（greedy＋用語集）とParakeetを同じ時間帯に測り直した。
- デコードは、どの方式も温度0のgreedyとした。
- 用語集の渡し方：
  - Qwen3-ASR：表記をカンマでつなぎ、system messageへ入れる。
  - Granite Speech：指示文の末尾に`Keywords: 表記, ...`を付ける。
  - Haas（speech.cpp）：`keywords`に1行1語の`表記=最初の読み`を渡す。`keywords_guard`は既定（有効）のまま。
  - どれも発話に出る語だけを渡したので、正解を含む楽観的な条件である。
- Granite Speechは、句読点と大文字小文字を付ける指示（`punctuate`）を使った。使わないと英字がすべて小文字になる。
- Haas-ja-v1.0は2つの実装で測った。
  - speech.cpp（commit 8d18924、0.11.0）をローカルでビルドし、GGUF版（F16、Q8_0、Q4_K）を`speech worker`で動かした。
  - 公式の`.nemo`をMLXへ移植した版。予測ネットワーク（KDA）をMLXで書き、前処理をNeMoと同じ計算にした。
- 結果：`runs/asr-newmodels-dev-say/`、`runs/asr-newmodels-pilot-tts/`。図は`runs/asr-newmodels-dev-say/figures/latency_vs_duration.png`。

## Haasの実装が公式と一致するかの確認

ColabのT4で、公式のHaas-ASR（commit acc614f）に14発話（dev-say 10、pilot 4）を認識させ、手元の出力と文字列で比べた。結果は`runs/asr-newmodels-dev-say/haas-official-check/`に置いた。

| 手元の実装 | 公式fp32と一致 | 公式bf16と一致 |
| --- | --- | --- |
| speech.cpp F16 | 14/14 | 13/14 |
| speech.cpp Q8_0 | 13/14 | 12/14 |
| speech.cpp Q4_K | 7/14 | 6/14 |
| MLXへの移植 fp32 | 10/14 | 未比較 |
| MLXへの移植 bf16 | 未比較 | 9/14 |

- 公式のbf16とfp32の出力も、1発話で互いに異なった（「メモリ」と「目盛り」）。
- MLXへの移植は、最初はparakeet-mlxの前処理をそのまま使い、公式との一致は10発話中3発話だった。前処理をNeMoと同じ計算に直すと、14発話中10発話まで一致した。
- 残る違いは、句読点1つや1語の違いである。
- そのため、比較の表のHaasには、公式と一致したspeech.cppの値を使う。MLXへの移植は、encoderと復号の時間の内訳を見るためにだけ使う。

## 結果（暫定の指標）

- CERは、評価の担当の正規化（`voiceime.eval.metrics.normalize_for_cer`）を使って計算した。
- 「読み揃え」は`docs/PLAN.md`の読み揃えCERで、評価の担当の実装ができるまでの暫定の計算である。
- 遅延は10秒前後（8〜12.5秒の15発話）の中央値である。
- pilotの発話は4〜7秒なので、全発話の中央値を載せた。

| 系 | dev-say CER（読み揃え） | pilot CER（読み揃え） | 用語の英字表記一致（dev-say） | フィラー残存（dev-say） | 遅延の中央値（10秒前後） | 内訳（10秒前後の中央値） | メモリ最大 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Whisper large-v3-turbo greedy＋用語集 | 10.6 | 9.3 | 65% | 74% | 0.79秒 | encoder 0.61、decoder 0.17 | 2.5GB |
| Parakeet TDT-CTC 0.6B ja | 20.9 | 17.4 | 1% | 41% | 0.17秒 | encoder 0.10、decoder 0.07 | 2.2GB |
| Haas-ja Q8_0（speech.cpp） | 17.7 | 11.5 | 1% | 38% | 0.10秒 | 内訳は取れない（MLX版はencoder 0.06、復号 0.07） | 0.78GB |
| Haas-ja Q8_0＋用語集（speech.cpp） | 14.0 | 9.3 | 84% | 38% | 0.11秒 | 同上 | 0.78GB |
| Haas-ja Q4_K＋用語集（speech.cpp） | 16.0 | 9.1 | 78% | 41% | 0.11秒 | 同上 | 0.48GB |
| Qwen3-ASR 0.6B 8bit | 21.4 | 12.7 | 18% | 53% | 0.36秒 | encoder 0.05、prefill 0.06、生成 0.25 | 2.0GB |
| Qwen3-ASR 0.6B 8bit＋用語集 | 15.1 | 19.8 | 65% | 56% | 0.36秒 | 同上 | 2.0GB |
| Qwen3-ASR 0.6B bf16 | 22.4 | 12.2 | 15% | 53% | 0.53秒 | encoder 0.06、prefill 0.07、生成 0.40 | 2.6GB |
| Qwen3-ASR 0.6B 4bit（参考） | 26.5 | 19.3 | 11% | 59% | 0.26秒 | — | 1.7GB |
| Qwen3-ASR 1.7B 8bit | 16.2 | 8.6 | 25% | 59% | 0.78秒 | encoder 0.07、prefill 0.15、生成 0.55 | 3.7GB |
| Qwen3-ASR 1.7B 8bit＋用語集 | 9.8 | 8.3 | 65% | 62% | 0.81秒 | 同上 | 3.7GB |
| Qwen3-ASR 1.7B bf16＋用語集 | 10.1 | 9.3 | 65% | 62% | 1.26秒 | encoder 0.08、prefill 0.18、生成 1.00 | 5.3GB |
| Qwen3-ASR 1.7B 4bit（参考） | 18.9 | 12.2 | 20% | 62% | 0.54秒 | — | 2.8GB |
| Granite Speech 5.0 2B＋用語集 | 14.6 | 13.2 | 22% | 50% | 1.96秒 | encoder 0.41、prefill 0.18、生成 1.36 | 8.2GB |
| Nemotron 3.5 ASR streaming 0.6B（参考） | 47.6 | 14.0 | 1% | 26% | 0.88秒 | 内訳は取れない | 2.2GB |
| Voxtral Mini 4B Realtime 4bit（参考） | 25.3 | 9.7 | 11% | 62% | 8.40秒 | 内訳は取れない | 5.6GB |

- メモリは、MLXの方式ではMLXが確保した量の最大値、speech.cppではworkerプロセスの最大の常駐メモリである。
- 全系の表は各directoryの`summary-tmp-cer.md`にある。

## 分析

- 10秒の発話でASR単体0.4秒に収まったのは、Haas-ja（speech.cpp 0.10〜0.11秒、MLX移植 0.14秒）、Parakeet（0.17秒）、Qwen3-ASR 0.6Bの8bit（0.36秒、p90は0.39〜0.40秒）と4bit（0.26秒）である。
- Qwen3-ASR、Granite Speech、Voxtralでは、LLMのtoken生成が時間の大半を占める。10秒の発話の出力は30〜50 tokenで、0.6B 8bitで約0.25秒、1.7B 8bitで約0.55秒、Granite 2Bで約1.4秒かかる。encoderは入力長に比例し、0.1秒以下である。
- Whisperは、encoderが30秒の窓のため0.61秒で一定である（前回の確認と同じ）。
- Voxtral Realtimeは、音声のフレームごとに1 tokenを進める設計のため、録音後に一括で処理すると発話の長さに比例して遅くなる（10秒で8秒）。録音中に処理を進める使い方でなければ候補にならない。
- 用語集の効果：
  - Haasの`keywords`は、用語の英字表記一致を1%から84%へ上げ、読み揃えCERも3.7ポイント下げた。遅延はほぼ増えなかった（＋0.01秒）。
  - Qwen3-ASRでもdev-sayでは18%→65%と大きく効いた。ただし0.6Bは、pilotで読み揃えCERが12.7→19.8と悪化した。
  - Granite Speechは1%→22%にとどまった。
- 用語集による誤挿入：Haas＋用語集で、話していない場所に用語が入った例が1件あった。dev-say-0021で、文頭の「うーん」が「loss、」になった。`keywords_guard`は有効のままである。発話に出る語だけを渡す今回の条件では、話していない用語の挿入は測れていない。

## 分かったこと

- 速度と精度の兼ね合いでは、Haas-ja＋用語集（speech.cpp、Q8_0）が最も良い。
  - Parakeetより速く（0.11秒）、読み揃えCERはWhisper turbo＋用語集に近い（dev-say 14.0対10.6、pilot 9.3対9.3）。
  - 用語の英字表記一致は84%で、他の候補より高い。
  - メモリは0.8GB、Q4_Kなら0.5GBで済む。
- Haas-jaの癖：
  - フィラーを落とすことが多い（残存38%）。
  - 文頭の短い語を落とす、または取り違えることがある（「えーと、ドッカー」→「ロッカー」、「あの、オース」→「ボス」）。
  - 英字の用語は、用語集が無いと小文字の英字になる（「vram」「openai」）。
- 精度を最優先するなら、Qwen3-ASR 1.7B 8bit＋用語集が最も低いCERである（dev-say 9.8、pilot 8.3）。ただし0.8秒かかり、0.4秒には収まらない。
- parakeet-mlxの前処理はNeMoと異なる（窓の置き方、端の埋め方、振幅の計算、対数の下限、正規化）。前回測ったParakeetの値も、NeMoの公式実装より悪く出ている可能性がある。

## 次の仮説

- Haas-jaに500語の用語集を渡し、話していない用語の挿入がどれだけ増えるかを測る。`keywords_guard`と`keywords_alpha`も変えて測る。speech.cppとOpenHinoVoiceは、1回に渡す語を16語・240字までにしている。
- 追加学習の土台をHaas-jaにする場合、学習にはNeMoと公式のHaas-ASR（CUDA）を使い、推論はspeech.cppのGGUFへ変換して動かす流れを確かめる。
- ParakeetをNeMoと同じ前処理で測り直す。
