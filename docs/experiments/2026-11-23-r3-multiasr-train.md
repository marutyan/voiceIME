# 第3弾学習用音声のQwen認識とHaas two-pass

## 結果

facultyで利用できた第3弾train音声12,000件とval音声1,000件について、Qwen3-ASR 0.6Bの初回認識、Haasの合併ヒントによる2回目認識、`segment-merge`、整形LLM用語一覧を作成した。train/valともmanifest順の全件がそろい、IDの重複と欠落はなかった。

整形用語一覧に含まれた正解語は、trainが13,247/19,220（68.9%）、valが1,310/1,427（91.8%）だった。大文字小文字を無視した照合でも同じ件数だった。

ただし、第3弾train文56,971件のうちfacultyに音声があったのは12,000件だった。残り44,971件分の結果は含まれないため、この成果物は部分集合である。

## 対象範囲

`docs/STATUS.md`には、第3弾のtrain文が56,971件と記録されている。facultyで確認できた`r3-train-20261122`の音声manifestは12,000件で、全件の音声ファイルが存在した。56,971件に対して音声が確認できない44,971件は推論対象に含めず、結果を全train分とは扱わない。

val音声は1,000件を使用した。第3弾train音声12,000件とval音声1,000件の計13,000件を、音声長の降順に並べて3 shardへround-robin分割した。各shardは4,334、4,333、4,333件で、各shard内は音声長の降順である。既存のHaas初回仮説はmanifestと件数、ID、順序が一致することを確認した。

| 入力 | 件数 | SHA-256 | faculty上の場所 |
| --- | ---: | --- | --- |
| 第3弾train音声manifest | 12,000 | `6ce5ea823cb70ca26cbf692c42815bb64ceedd4c979c9af6aa8eec6e4cf8c96e` | `~/voiceime-work-tts/outputs/r3-train-20261122/manifest.jsonl` |
| val音声manifest | 1,000 | `89d96b02e9fa064b9b93f8c6ea21cea87fb19acc7b04aa2696561f7cb0424b6` | `~/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/data/tts/val/manifest.jsonl` |

旧train音声9,990件は`synth-train-*`の別ID体系のため、第3弾trainには混ぜなかった。

## 条件

- Qwen3-ASR 0.6B、revision `5eb144179a02acc5e5ba31e748d22b0cf3e303b0`。qwen-asr 0.0.6、PyTorch 2.11.0+cu128、Transformers 4.57.6、bfloat16、greedy（`do_sample=false`, `num_beams=1`）、日本語指定、contextは空。
- Qwenのbatchは32件とし、音声長順でpaddingを減らした。3 shardをGPUキューに登録し、キューから割り当てられたGPU1〜3だけを使った。
- Haasは既存のQ8_0 GGUFを使い、speech.cpp CUDA encoderとCPU decodeで再認識した。speech.cpp commit `8d18924cd238b87c0297df112f7ff40783a6414f`、ggml commit `79b50d239d0b88852814c873db0d85d43ed66d9b`。
- HaasとQwenの初回仮説を改行で連結し、mainの`select_glossary()`で候補を選んだ。speech.cppのヒントはengineの上限16語・240文字、整形LLMの用語一覧は最大20語とした。2回目の仮説は`segment-merge`、読み類似度閾値0.80で区間ごとに採否した。
- train/valの用語集はv1とv2を優先順で結合し、v2 held-out語と既存除外語を除いた。前回の条件ファイル`exclude-v2-plus-heldout.txt`（6,437表記、SHA-256 `a9d1cc6d40475a2adb984cc28ad4a82fe6f8c7c9b46207ada61e2959c145da6f`）を使った。
- 選択用コードはmain commit `cab8b886084c42935227c904027dd790d0df17af`の`src/voiceime/`をfacultyへコピーした。`formatter/glossary.py`のfaculty上SHA-256は`e9db1b5d7ba52703300b4cb29099f2cb8da791361f6f895e931eac5f75eeedfa`。

## 実行

優先度25で最初の3 shardを投入したが、`exec -a`で起動したPythonが仮想環境のsite-packagesを見失い、`soundfile`のimportで終了した。各ジョブは1秒以内、GPU使用率0%で、推論は始まっていない。これを受けてQwenの仮想環境内に`voiceime-r3multi-train-pipeline`というPython別名を作り、修正ジョブを優先度35で再投入した。Formatter評価の優先度30のジョブを先にキューへ通した。

初期の一度だけの使用状況確認では、GPU1〜3でQwenの推論が進み、GPU2はSM 5〜70%、GPU3はSM 0〜56%の範囲を観測した。CPU負荷も処理中で、入力待ちやCPU参照実装への切替は見られなかったため、batchや分割は変更しなかった。キュー上のPython親プロセスは`voiceime-r3multi-train-pipeline`、speech.cpp workerは`voiceime-r3multi-haas-twopass-worker`に統一した。

## 成果物と検証

出力はすべてfaculty上の`~/voiceime-work-asr/r3-multiasr-train-20261123/outputs/`に置き、行単位のJSONLは手元へ転送しない。整形LLM担当の`~/voiceime-work-fr3/repo/README.md`にファイル名、schema、各フィールド、対象範囲を追記した。

| 出力 | 件数 | bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `train-available-12000.jsonl` | 12,000 | 49,204,812 | `c4c6052d5a324d54a18d0e96f7d22c6bb41d7c5408f50ecbc3f2fe59d0b3087b` |
| `val-1000.jsonl` | 1,000 | 3,805,532 | `79810cff789919c4dffb9e0858c896143273ed85d80ead6e4ed2f5ccab0f59b7` |
| `metadata.json`（faculty） | — | 10,333 | `383590be20be3f59f7d6e5184268130bfb9290c6b04fa89a2b828f5af0c92003` |

train JSONLの正解語は19,220語中13,247語が一覧に含まれた（68.9%）。12,000行中10,207行に正解語があり、そのうち8,721行（72.7%）は1語以上を一覧に含んだ。valでは1,427語中1,310語が一覧に含まれた（91.8%）。1,000行中850行に正解語があり、そのうち813行（81.3%）は1語以上を一覧に含んだ。計数対象は各manifestの`terms`で、用語一覧の`surface`と完全一致で照合した。casefold照合も同数だった。

CPUで行った統合検査では、train 12,000/12,000行、val 1,000/1,000行がそれぞれ入力manifest順に並び、ID重複0、欠落0だった。全行で必須文字列・遅延フィールドの型、整形用語20語以下、Haas用語16語以下も確認した。確認スクリプトは`runs/asr-tts/r3-multiasr-train-20261123/scripts/train_pipeline.py`にある。

JSONL2本の合計は53,010,344 bytesだが、facultyの出力ディレクトリに残し、手元へ転送していない。手元へ持ち帰ったのは集計だけの10,333-byte `metadata.json`である。同metadataのローカルSHA-256は`383590be20be3f59f7d6e5184268130bfb9290c6b04fa89a2b828f5af0c92003`。

整形LLM担当の`~/voiceime-work-fr3/repo/README.md`に、出力パス、2つのJSONL名、各フィールドの意味、trainの対象範囲を追記した。

## 処理時間とGPU

キュー優先度35で3ジョブを実行した。Qwenの処理はモデル読み込み後に計測し、Haasの処理はworker起動を含む。各キュー`.util`の秒数、平均使用率、サンプル数は次のとおり。

| shard | GPU | 行数 | Qwen | Haas two-pass | ジョブ全体 | 平均GPU使用率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 00 | 2 | 4,334 | 809.2秒 | 896.1秒 | 1,720.8秒 | 7.9%（58 samples） |
| 01 | 3 | 4,333 | 807.3秒 | 896.2秒 | 1,713.8秒 | 10.0%（57 samples） |
| 02 | 1 | 4,333 | 898.4秒 | 907.0秒 | 1,815.8秒 | 9.1%（61 samples） |

`.util`の秒数の合計は5,260秒（約1.46 GPU-hour）。サンプル数で加重した平均GPU使用率は約9.0%だった。Qwenの1行あたり`latency_s`はbatch内の推論壁時間をbatch件数で割り、音声読み込み時間を含めない。

最初の数分に行った一度の使用状況確認では、GPU2はSM 5〜70%、GPU3は0〜56%、GPU1は0〜55%だった。CPUでも処理が進み、batch待ちやCPU参照実装への切替は見られなかったため、batchや分割は変更しなかった。Qwenログに`temperature`が無効または無視される警告と`pad_token_id`の通知があったが、`do_sample=false`と`num_beams=1`は明示している。

最初の優先度25の起動は`exec -a`がPythonの仮想環境を解決できず、`soundfile`のimportで3ジョブとも終了した。各ジョブの`.util`は0%・0〜1秒で、推論は始まっていない。仮想環境内に役割名のPython symlinkを置き、優先度30のFormatter評価ジョブを先に通した後、優先度35で再実行した。

全ジョブの完了後、キューの`pending/`と`running/`に自分のジョブはなく、`voiceime-ps.sh`に`voiceime-r3multi`プロセスは表示されなかった。`nvidia-smi --id=1,2,3`でもGPU1〜3はすべて0 MiB、0%だった。GPU0は他者の利用分があり、触れていない。
