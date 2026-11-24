# 整形用LLMの蒸留 第2弾：Gemma 4 E2B-it LoRA（2026-11-21）

## 目的

第2弾Qwen3.5-0.8Bと同じ入力条件でGemma 4 E2B-itを学習し、本人の読み上げ50件とval 1,000件で比較する。学習の選択指標には、dev-userと同じ文30件を除いたval 970件の損失を使う。

## 学習条件

| 項目 | 条件 |
| --- | --- |
| ベースモデル | google/gemma-4-E2B-it。第1弾と同じモデル名 |
| 学習データ | data/text/train.jsonl、40,000件 |
| 音声ありの入力 | 9,990件はHaas two-passの実出力 runs/asr-tts/haas2p-train.jsonl。確率0.2でヒント無しの runs/asr-tts/haas-train.jsonl に置換 |
| 音声なしの入力 | 30,010件は第2弾と同じASR癖の加工。句読点は確率0.5で本人の読み上げの分布へ寄せる |
| checkpoint選択 | runs/formatter-sft2/val-select.jsonl の970件の損失。評価val 1,000件のうちdev-userと同じ文30件を選択から除外 |
| 学習方式 | LoRA、r=16、α=32、dropout=0.05。文章部分のattentionとFFN線形層（q/k/v/o/gate/up/down） |
| 最適化 | 学習率2e-4、1 epoch、seed 0、batch 4×gradient accumulation 8、最大1,024 token、250 stepごとに評価 |
| 入力拡張 | ヒント無し確率0.2、用語集最大20語、正解用語dropout 0.15、無関係語最大8語、gradient checkpointing |
| 実行 | facultyのH100、train/formatter/train.pyを直接実行。Colabは不使用 |

学習に使ったデータと加工の詳細は、2026-11-21-formatter-sft2.mdの条件に合わせた。用語集の入力は学習データ各行の用語を使った。

| step | 250 | 500 | 750 | 1,000 | 1,250 |
| --- | ---: | ---: | ---: | ---: | ---: |
| val loss | 0.20060 | 0.17358 | 0.15489 | 0.14778 | **0.14716** |

最良はcheckpoint-1250で、eval lossは0.1471618265。Trainerのtrain_runtimeは4,288.15秒（71分28秒）。学習は2026-11-21 17:10ごろから18:22ごろまでGPU3で実行した。初回のGPU1実行は約6分・step 9で停止し、最終checkpointには使っていない。

## LoRA統合

train/formatter/merge_lora.pyをfaculty上でCPU実行し、checkpoint-1250を元のBF16重みに統合した。

- faculty上の統合済み重み：/home/maru/voiceime-work-gemma2/repo/models/formatter/sft2-gemma-4-e2b-lora/merged-bf16/
- model.safetensors：10,208,852,910 bytes
- 本人の決定に従い、重みは手元へ転送していない。MLX変換も行っていない。

## 評価条件

- GemmaはfacultyのTransformers 5.23.0、PyTorch 2.11.0+cu128、BF16で推論した。batch sizeは64、greedy decoding。
- promptはsrc/voiceime/formatter/prompt.py、用語選択はformatter/glossary.pyを使い、用語集は最大20語、最低score 75とした。除外条件では指定ファイルとsurfaceが完全一致する語をprompt用語集からも除いた。
- 出力上限はmax(64, floor(入力テキストtoken数×1.5))。batch推論ではMLXの反復出力による途中停止は適用していない。valは各条件1件がtoken上限に達した。
- 本人の読み上げは50件。manifestは /private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-scripted.jsonl、ASR入力はHaas two-passの出力をIDで結合した。音声pathは除き、音声は読み込んでいない。
- valはdata/tts/val/manifest.jsonlとruns/asr-tts/haas2p-val.jsonlをIDで結合した1,000件。
- 見えない用語条件では、Haasの除外あり出力 runs/base-compare/devuser-haas2p-excl.jsonl、runs/base-compare/val-haas2p-excl.jsonl と data/eval/unseen-terms-devuser.txt、unseen-terms-val.txtを使い、同じsurfaceの用語を生成用語集からも除いた。dev-userは20語、valは258語を候補から除外した。
- Qwen第2弾の相手は、既存の手元MLX 4bit出力を使った。元のQwen重みはfacultyに無く、転送しない方針のため、faculty上でのBF16再評価は省略した。
- 集計はvoiceime.eval.reportの--unseen-termsで行った。結果はruns/formatter-sft2-gemma/devuser-report.mdとval-report.mdに保存した。

入力manifestは音声pathを外したため、音声長別の遅延集計はできない。以下の遅延は全件の中央値/p90で、Gemmaはbatch全体の生成時間を件数で割った値を含む。QwenのMLX 4bit実測遅延とは実行環境・計測方法が異なり、直接比較できない。

## 結果：本人の読み上げ50件

| 入力とモデル | CER | 用語正答率 | 見えない用語 | それ以外 | 未発話用語挿入 | フィラー残存 | 遅延 中央値/p90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Haas two-pass・Qwen第2弾 MLX 4bit | 7.34% (171/2,331) | 83.58% (56/67) | 90.00% (18/20) | 80.85% (38/47) | 1 | 0.00% | 0.435/0.626秒 |
| Haas two-pass・Gemma BF16 | 9.01% (210/2,331) | 80.60% (54/67) | 80.00% (16/20) | 80.85% (38/47) | 1 | 0.00% | 0.591/0.693秒 |
| 用語除外・Qwen第2弾 MLX 4bit | 7.72% (180/2,331) | 77.61% (52/67) | 70.00% (14/20) | 80.85% (38/47) | 1 | 0.00% | 0.434/0.606秒 |
| 用語除外・Gemma BF16 | 8.28% (193/2,331) | 74.63% (50/67) | 60.00% (12/20) | 80.85% (38/47) | 1 | 0.00% | 0.410/0.512秒 |

## 結果：val 1,000件

| 入力とモデル | CER | 用語正答率 | 見えない用語 | それ以外 | 未発話用語挿入 | フィラー残存 | 遅延 中央値/p90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Haas two-pass・Qwen第2弾 MLX 4bit | 5.37% (2,551/47,482) | 90.12% (1,286/1,427) | 86.61% (375/433) | 91.65% (911/994) | 42 | 0.31% | 0.559/0.882秒 |
| Haas two-pass・Gemma BF16 | 5.20% (2,468/47,482) | 89.35% (1,275/1,427) | 85.45% (370/433) | 91.05% (905/994) | 38 | 0.31% | 0.648/1.037秒 |
| 用語除外・Qwen第2弾 MLX 4bit | 6.09% (2,890/47,482) | 84.93% (1,212/1,427) | 69.28% (300/433) | 91.75% (912/994) | 44 | 0.31% | 0.550/0.890秒 |
| 用語除外・Gemma BF16 | 6.13% (2,909/47,482) | 83.39% (1,190/1,427) | 66.97% (290/433) | 90.54% (900/994) | 38 | 0.31% | 0.404/0.637秒 |

すべての条件でmanifestと予測が50/50件または1,000/1,000件一致し、重複ID・欠損予測はなかった。音声pathを外したため、音声長別の遅延集計対象からはdev-user 50件、val 1,000件を除外した。

## 実行時間とGPU使用

| 実行 | GPU | 時間 | 結果 |
| --- | --- | ---: | --- |
| 最終学習 | H100 GPU3 | 4,288秒（71分28秒） | 1,250 step、best loss 0.14716 |
| 最終評価 batch64 | H100 GPU3 | 全体446秒（7分26秒）、生成407秒 | 2,100件、PyTorchの最大GPU割当量13.72GB |
| batch32比較 | H100 GPU3 | 生成515秒 | 2,100件、最大GPU割当量12.07GB |
| batch128試行 | H100 GPU3 | 約3分で停止 | val最初の128件に83.15秒。dmonは0〜19%で、最終結果には不使用 |

batch64はbatch32よりgeneration時間が約21%短かったため採用した。batch32の推論中に記録したdmonはGPU3で最大63%、batch128では最大19%だった。batch64のgeneration中はdmonを採取できず、GPU使用率が継続して100%に達したことは確認できていない。初回の学習停止分を含め、GPU割当時間は学習の約77分、評価試行の約20分。

## 分かったことと限界

- dev-user 50件ではQwen第2弾がCER・用語正答率・見えない用語正答率でGemmaを上回った。
- val 1,000件の通常条件ではGemmaのCERがQwenより0.17ポイント低かった一方、用語正答率は0.77ポイント、見えない用語正答率は1.16ポイント低かった。用語除外条件ではQwenがCER・用語・見えない用語でわずかに上回った。
- QwenはMLX 4bit、GemmaはTransformers BF16であり、生成ランタイムと停止処理が異なる。Gemma評価は反復による途中停止を使わず、batch時間からの換算遅延を出したため、速度の優劣は判断できない。
- 学習はseed 0の1回だけ。dev-userは50件、見えない用語は20件であり、差が小さい指標の一般化は判断できない。
- 重みはfacultyの統合済みBF16パスに保管した。手元への転送とMLX変換は実施していない。
