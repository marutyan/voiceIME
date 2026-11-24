# 整形用LLMの蒸留 第3弾：Qwen3.5-0.8B、音声なし（2026-11-22）

## 仮説

第2弾の学習入力40,000件へ、用語集v2のtrain語を使った文章を加えると、本人の読み上げで用語の正答率が上がり、CERが下がる。第2版のheld-out語とtest-novel語を学習に入れずに評価する。

## 学習条件

| 項目 | 条件 |
| --- | --- |
| ベースモデル | `Qwen/Qwen3.5-0.8B`。faculty取得revision `2fc06364715b967f1860aea9cf38778875588b17` |
| 学習データ | 第1版の40,000件と、用語集v2の完成済みtrain文（約67,000件、受領後に件数を記録） |
| 旧データのASR入力 | `haas2p-train.jsonl`。ASRなしの例は`asr_noise.py`で加工する（`--allow-partial-asr --asr-noise-prob 1.0`）。no-hint確率0.2、本人の句読点への寄せ確率0.5 |
| 新データのASR入力 | 同じ`asr_noise.py`加工を適用し、辞書抜け行の行単位用語集を保持する |
| 用語集 | 用語集v2のtrain語のみ。held-out語、test-novel語、および`glossary-v2-excluded.txt`の語を用語として使わない |
| 学習方式 | 全パラメータ、2 epoch、学習率`2e-5`、seed 0、最大1,024 token |
| 実効batch | 32件。初期候補はmicrobatch 16、累積2、DataLoader worker 8、gradient checkpointingなし。pilotでGPU使用率とVRAMを確認してから確定 |
| checkpoint選択 | `val-select.jsonl` 970件の損失。250 stepごとに評価・保存 |

## 比較と評価

- **A**は従来どおり2回目を主入力にし、no-hintの1回目を確率0.2で使う。**B**は1回目と2回目を常に両方渡し、他の学習条件はAと揃える。
- **C**は別担当が作成する区間単位の結合文と1回目を渡す。結合文が届いてから追加し、A/Bの学習を待たせない。
- 基準は第2弾のQwen3.5-0.8B、MLX 4bitの既存結果。第2弾の重みはfaculty上の確認先になく、実行ランタイムの差を記録する。
- facultyで`eval_transformers.py`を使い、Transformers BF16で評価する。
- 本人の読み上げ50件は、`unseen-terms-devuser.txt`を用語集から除いた条件と、除かない条件を評価する。valは1,000件を評価する。
- test-novelは、対応するHaas書き起こしが`runs/asr-tts/`にある場合に評価し、novel語を用語集から除く。
- 既存の評価manifestは音声pathを含まない。音声長別の遅延は算出できない。

## 準備済みの入力と環境

- facultyの作業場所：`~/voiceime-work-fr3/`。コードはcommit `3d0583954525a57c274986e34cfea034eb0a0349`から配置した。
- 第1版の学習JSONLはfacultyの`~/voiceime-work-gemma2/repo/data/text/train.jsonl`から複製し、40,000行、SHA-256 `2525447b5d249b8aeec361bfb25a0678d363e205e574bf4d6dcee312ac4371c4`を確認した。
- `haas2p-train.jsonl`と`haas-train.jsonl`は各9,990行。val選択用JSONLは970行、Haas two-pass val入力は1,000行。
- 本人用manifestは50行で、既存Qwen第2弾出力の`input_text`とIDが一致することを確認した。faculty評価用ASR入力はこの`input_text`から作った。
- ID確認では、旧train 40,000件にtwo-pass／no-hintが同じ9,990 IDで対応し、970件の選択用val IDが1,000件のHaas valに含まれることを確認した。
- faculty環境はPyTorch 2.11.0+cu128、Transformers 5.23.0、Accelerate 1.16.0。`soundfile` 0.14.0は新しい作業場所の`python-deps/`にだけ追加した。
- モデルsnapshotは`~/voiceime-work-fr3/hf-cache/`に取得済み（約1.7GB）。

## 実行状況

**本番学習は未開始。** 用語集v2は本体リポジトリの`/Users/marutyan/PrivateDev/voiceIME/data/text/glossary-v2.jsonl`にあり、31,415語（train 25,050、held-out 6,365）を確認した。`glossary-v2-excluded.txt`は83語。第3弾の`data/text/v3/train.jsonl`と`test-novel.jsonl`は、2026-11-22 04:06 JST時点でまだ本体リポジトリに現れていない。facultyの生成clientログには成功終了（final 7,659要求、top-up 1,800要求）とあるが、元ディレクトリの出力は変更していない。

GPU設定を決めるため、第1版40,000件だけで試運転した。microbatch 32はstep 1でOOM、microbatch 16・累積2・worker 8はstep 17でOOM。`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`を加えた同じ設定では38 stepを完走し、学習時間225.6秒、最良val損失0.37421、最大VRAM 92,657 MiBだった。2秒間隔の計測では学習中GPU使用率の概算平均は27.4%で、目標の約90%には届かなかった。出力は`~/voiceime-work-fr3/outputs/pilot-40k-mb16-ga2-w8-expandable/`。

試運転終了後、Transformers 5.23.0のTrainerがbest checkpointを直接`load_state_dict`し、Qwen3.5の重みkey 320個を読み込めていない警告を確認した。checkpointを標準の`AutoModelForCausalLM.from_pretrained`でCPU読込したところ、missing／unexpected／mismatched keyはいずれも0で、共有embedding／lm_headも結合されていた。`train/formatter/train.py`は自動読込を無効にし、この標準読込を経由してbest checkpointを厳密に反映するよう修正した。

worker 16の試運転は当初、`exec -a`でPythonのargv[0]を変えたため標準ライブラリを見つけられず、GPUを使う前に終了した。Pythonの基準パスとvenvのsite-packagesを明示したlauncherに直し、2026-11-22 04:05 JSTにキューからGPU1で再実行した。38 step中17 stepでOOMし、94秒で終了。キューのGPU使用率平均は25.0%、失敗時は9.64 GiBの割当要求に対して空きが9.58 GiBだった。別名は`voiceime-formatter-r3-pilot`としてGPU一覧に表示された。完了後にGPU1〜3のVRAM使用が0 MiBで、残存プロセスも無いことを確認した。Transformersは`causal_conv1d`と`flash-linear-attention`の参照実装へfallbackすると警告している。使用率目標にもメモリにも余裕がなく、この設定では本番へ進めない。

| 結果 | 値 | 出典 |
| --- | --- | --- |
| 試運転・最良checkpoint | val損失0.37421、38 step | pilotの`train_summary.json` |
| GPU・使用率・学習時間 | H100、学習中平均27.4%、225.6秒、最大92,657 MiB | pilotの2秒間隔監視と`train_summary.json` |
| worker 16試運転 | step 17/38でOOM、94秒、平均使用率25.0%、割当要求9.64 GiB・空き9.58 GiB | `~/voiceime-queue/failed/11-formatter-r3-pilot-w16-retry.log`、`.util` |
| 本番学習・評価 | 未実施 | v3の完成データ待ち、使用率目標も未達 |
| dev-user 50件 | 未測定 | 評価未実施 |
| val 1,000件 | 未測定 | 評価未実施 |
| test-novel | 未測定 | 書き起こし作業の完了と出力配置を未確認 |

## 学習開始前に確認すること

1. 本体リポジトリにv3データが現れたら受け取り、件数、重複ID、`glossary_fixed`、辞書抜け行を確認する。
2. v2 held-out語とtest-novel語が旧・新の学習文、用語集、ASR入力に現れないことを監査する。除外83語は文中の文字列から削除せず、用語・辞書項目として扱わない。
3. 第1版40,000件とv3行を統合した入力を作り、元データの行数、seed、加工条件を記録する。
4. すべてのGPU処理は`~/voiceime-queue/pending/`へ実行可能なlauncherを入れる。GPU選択と`CUDA_VISIBLE_DEVICES`は常駐キューに任せ、workerを増やした数十stepの試運転で平均使用率約90%を確認する。
5. 使用率を上げられたmicrobatch、累積、worker数で2 epochを学習し、val-select損失最小checkpointを評価する。

## 結果・分析

本番学習と評価は未実施。workerを8から16へ増やしても使用率は25.0%で、step 17でOOMした。最適化kernelの新規導入、学習コードを変えてlogitsのメモリ使用を減らす方法、または使用率90%未達のまま本番へ進む方法のどれを採るかはPM判断が必要。新しい依存の導入や学習条件の変更は承認されていない。

## PM追加指示の追記（2026-11-22 04:06 JST）

`FormatterInput`を学習、Transformers評価、MLX推論で共有し、従来の文字列入力、1回目＋2回目、1回目＋結合文を切替可能にした。結合文の生成方法はまだ届いていないため、条件Cの学習・評価は未実施。prompt helperのCPU smoke checkはPASS。ローカルでの同checkは`rapidfuzz`が無いため実行できず、faculty側の既存venvで確認した。

第1版の実ASR 9,990件に対する暫定監査では、(a) 行の用語集にある正解外の表記が2回目に出た行は604件、そのうち10文字以上の表記が出て1回目に正解語の読みがある行は60件、(b) 正解表記の直後にカタカナが続く候補は607件、(c) 繰り返し発話で2回目に表記が1回だけ出て1回目に読みが2回ある行は6件だった。(a)と(b)は指定例そのものの完全一致ではなく、行の辞書と文字列からの候補数。

第1版の正解文には「やっぱり」656件、「最後に」111件、「主に」5件がある。音声のない例では現行`asr_noise.py`の一度の固定seed試算で、それぞれ487/487、91/91、4/4件の入力に句が残った。実ASRの2回目では、それぞれ167/656、20/111、1/5件に残った。これは前処理済みの全学習例を数えたものではなく、旧40,000件だけの監査である。v3到着後に同じ集計を再実行する。

同じく旧40,000件のASR runとmanifestを見た暫定値であり、v3の受領後にpattern監査とheld-out/test-novel/除外語の漏れ監査を完了する。合成例を追加・反復する場合の頻度を実測から決められないときは、研究条件を推測せずPMへ戻す。

## 本番開始前の訂正と監査（2026-11-22）

### 比較条件

PMの最新指示に合わせ、条件Aは2回目だけを入力し、`--nohint-prob 0`にする。条件Bは1回目と2回目を両方入力する。A/Bは同じ学習データ、用語集、seed、学習率、batch、worker数、gradient checkpointing、句読点加工を使う。条件Cは入力形式の切替を用意済みで、結合文データが届いた後に別途実施する。

### held-outとtest-novelの漏れ監査

用語表記の英数字境界と読みのカタカナ境界は、`datagen/text_v3/pipeline.py`の検査と同じ条件で照合した。第1版40,000行のうち1,041行にv2 held-out語の読みがあり、そのうち1行は表記も一致したため、A/B共通の入力から除外した。test-novel語の表記・読みは第1版で一致0行だった。残った第1版は38,959行。

実ASRの第1回目・第2回目も同じ語彙条件で点検し、どちらか一方にheld-out/test-novel語の表記またはheld-out語の読みがあるIDは、A/B両方のASR入力から除外した。第1回目の該当は31行、第2回目は183行。両方が一致する9,522 IDだけ実ASRを使い、他の学習行は`asr_noise.py`で音声なし入力を作る。

`glossary-v2-excluded.txt`は83語と説明コメント1行から成る。用語集v2のtrain 25,050語から該当する72語を外し、24,978語を明示的な学習用辞書にした。v3は56,971行とtest-novel 500行の完成済みデータを使う。結合前データのSHA-256は、v1 `2525447b5d249b8aeec361bfb25a0678d363e205e574bf4d6dcee312ac4371c4`、v3 train `252cfaf5a3bc0023158d1d009c03fa47668261ec74fd392c45ebce0fffdcc6ab`、test-novel `9fb8c7ef83fde5d845a87164871635a97285f62892b2c45b1348fe11202753ac`。

### 入力誤りと過剰な削除

本人の実ASRで検出した率を、v3で各型を合成できる行の割合に合わせて`asr_noise.py`へ設定した。該当行の目安は、長い誤置換19,394行、英字表記後の読み残り44,764行、繰り返し語の片方置換1,679行。A/Bとも同じデータ加工コードを使う。`やっぱり`は第1版656行・v3 1,612行、`最後に`は111行・505行で、例数を増やす必要はない。非削除例の`主に`は監査後6行だったため、同じ6文から4件をseed 0で再掲して10件にした。A/B共通の学習データは95,934行、ID重複は0。

### 高速kernelの準備

formatter-r3専用venvに`flash-linear-attention==0.6.0`と`fla-core==0.6.0`があり、A/Bはこれを使う。`causal-conv1d==1.7.0`のwheelはPython 3.12.0／PyTorch 2.13.0+cu129／CUDA runtime 12.9／nvcc 12.8／`TORCH_CUDA_ARCH_LIST=9.0`／`MAX_JOBS=4`でCPUのみから一度作ろうとしたが、`exec -a`による子プロセス起動で`PermissionError: [Errno 13] ... executable ''`となり、CUDAコンパイル前に失敗した。PMの指示どおり再試行せず、FLAのみで本番を開始する。結果と条件はfacultyの`~/voiceime-wheels/README.txt`に記録した。

本番設定はmicrobatch 32、gradient accumulation 1（実効batch 32）、DataLoader worker 16、gradient checkpointingあり、全パラメータ、2 epoch、learning rate `2e-5`、seed 0、最大1,024 token。A/Bはfacultyのジョブキューへ別々に登録し、空いたGPUをキューに割り当ててもらう。GPUの空き待ち中は直接確保しない。

## 本番学習と評価の確定結果（2026-11-22）

この節は、上記の「未開始」「判断待ち」などの記述を、その後のPM指示に沿って実行した最終状態へ更新する追記である。過去の試運転記録は履歴として残す。

### 条件と学習結果

共通学習データは95,934件、2 epochで各5,996 step。A/Bで変えた学習要因は入力形式だけで、Aは2回目のみ（`input_passes=single`、no-hint確率0）、Bは1回目と2回目（`input_passes=both`）。実効batch 32、全パラメータ、学習率`2e-5`、seed 0、最大1,024 token、worker 16、gradient checkpointing有効、句読点加工確率0.5、用語集drop確率0.15は共通である。

| 条件 | GPU | 最良checkpoint | 選択val損失 | Trainer学習時間 | キュー記録の平均GPU使用率 |
| --- | --- | --- | ---: | ---: | ---: |
| A: 2回目のみ | H100 / 1 | `checkpoint-5500` | 0.16918 | 6,703.8秒 | 89.4%（224 sample） |
| B: 1回目＋2回目 | H100 / 2 | `checkpoint-5500` | 0.12809 | 7,581.0秒 | 87.7%（253 sample） |

キュー全体の所要時間はAが6,746秒、Bが7,636秒で、両方とも終了コード0。GPU使用率は90%目標に近いがBは届かなかった。Bの学習時間はAより約13%長く、平均入力token数はdev-userで約2.06倍だった。A/Bの引数はfaculty各出力先の`train_summary.json`に記録した。

faculty専用環境はPyTorch `2.13.0+cu129`、Transformers `5.23.0`、`flash-linear-attention==0.6.0`、`fla-core==0.6.0`。`causal-conv1d==1.7.0`はnvcc 12.8を指定したCPUビルドを一度試みたが、Python子プロセス起動で失敗したため導入していない。A/Bとも同じFLA環境で実行し、causal convolutionは参照実装へfallbackした。

### EOS停止条件の訂正

最初のA評価では全50件とval全1,000件の生成が出力上限に達し、出力末尾に会話区切り語が残った。`src/voiceime/formatter/prompt.py`は学習ラベルにtokenizer EOSを付ける一方、評価コードはgeneration config EOSだけを使っていた。facultyのtokenizer EOSは`<|im_end|>`（ID 248046）、generation config EOSは`<|endoftext|>`（ID 248044）で一致していなかった。

`train/formatter/eval_transformers.py`を両EOSで停止し、長さ上限時はtokenizer EOSを出すよう修正した。最初の評価出力は採用せず、新しい出力先でA/B双方を再実行した。修正版で上限に達したのはAのvalが1,000件中1件だけで、dev-userとBの評価では0件だった。B評価の初回launcherはvalの1回目ASRファイルのパス誤りで失敗したが、正しい`inputs/sft3-20261122/haas-val.jsonl`を指定した再実行は終了コード0で完了した。

学習の正解文と評価の出力には`src/voiceime/formatter/style.py`の`apply_output_style`を適用し、数値の後の「パーセント」を`%`へ揃えた。評価はTransformers BF16、greedy、batch 32で実施し、CERは更新後の`src/voiceime/eval/`定義（`CER_EQUIVALENT_FORMS`を含む）で集計した。SFT2基準はMLX 4bitの再評価値であり、A/BのTransformers BF16とは実行runtimeが異なる。

### 評価結果

| 評価 | SFT2 MLX 4bit | A: 2回目のみ | B: 1回目＋2回目 |
| --- | --- | --- | --- |
| dev-user、用語集全件：CER / 用語正答率 / 初見20語 | 7.05% / 56/67 (83.58%) / 18/20 (90%) | 7.05% / 53/67 (79.10%) / 16/20 (80%) | 6.02% / 56/67 (83.58%) / 17/20 (85%) |
| dev-user、初見語を用語集から除外：CER / 用語正答率 / 初見20語 | 7.44% / 52/67 (77.61%) / 14/20 (70%) | 7.18% / 51/67 (76.12%) / 14/20 (70%) | 5.63% / 57/67 (85.07%) / 18/20 (90%) |
| val 1,000件：CER / 用語正答率 | 5.25% / 1286/1427 (90.12%) | 4.52% / 1304/1427 (91.38%) | 3.51% / 1300/1427 (91.10%) |

BはAよりdev-userのCERが全用語条件で1.03ポイント、初見語除外条件で1.55ポイント低く、val CERも1.01ポイント低かった。全用語条件の用語正答率はAより4.48ポイント上がったが、SFT2の83.58%と同じで、目標95%には届かない。Bの初見語正答率は全用語条件で85%、初見語除外条件で90%となり、目標80%を上回った。seed 0の単一runであり、seed間のばらつきは未測定。

### 入力長と整形時間

整形時間は評価batchの生成wall timeを件数で割ったthroughput換算平均で、単発遅延ではない。dev-user manifestには音声長がなく、音声長別の評価遅延は未測定。

| 評価 | 平均入力token A → B | 平均prompt token A → B | 整形時間平均 A → B |
| --- | ---: | ---: | ---: |
| dev-user、用語集全件、50件 | 29.06 → 59.98 | 480.26 → 529.60 | 0.142 → 0.140秒/件 |
| dev-user、初見語除外、50件 | 29.06 → 59.98 | 480.60 → 530.30 | 0.049 → 0.051秒/件 |
| val、1,000件 | 31.40 → 64.84 | 498.82 → 553.45 | 0.0476 → 0.0469秒/件 |

BではASR入力長がほぼ2倍、promptは約10–11%長くなったが、batch換算の整形時間に増加は観測されなかった。これは単発遅延の比較ではなく、GPU、batch、greedy生成による計測値である。main評価report上のASR込み中央値/p90は、全用語dev-userでA `0.372/0.474`秒、B `0.370/0.480`秒、初見語除外でA `0.277/0.378`秒、B `0.279/0.384`秒、valでA `0.403/0.634`秒、B `0.400/0.641`秒だった。

### 解釈と次の作業

- AはSFT2と比べて初見語除外条件のCER・用語正答率がほぼ改善しなかった。BはAよりCERを下げ、特に初見語を用語集から除いた場合の用語正答率を高めた。
- Bでもdev-user全用語の正答率83.58%とCER6.02%は、目標95%・5%に届いていない。val CERは目標内だが、本人の読み上げ50件の達成を代替しない。
- test-novelの文章500件は入力に存在するが、facultyの`runs/asr-tts/`に対応するASR書き起こしを確認できなかったため未評価。
- 条件Cは区間結合文が未着のため未実施。結合文＋1回目の入力を切り替えられる状態までコードを準備済みであり、結合文が届いた後にA/Bと同じ設定で比較する。

評価結果と生成時間の出典はfacultyの`runs/formatter-sft3-eosfix-a-20261122/`および`runs/formatter-sft3-eosfix-b-retry1-20261122/`。学習ログとGPU平均使用率は`~/voiceime-queue/done/20-formatter-r3-{a,b}-sft3.{log,util}`。

## 現行ASR選択での再評価とB-2B（2026-11-22）

### 条件

最新のASR入力選択と区間ごとの採否後の2回目を使い、学習済みA/Bを追加学習なしで評価した。Aは2回目だけ、Bは1回目と採否後の2回目を入力した。valは1,000件、本人の読み上げは既存baselineと同じ`dev-user-s` 50件を使った。用語集はv1（1,458語）、評価は`src/voiceime/eval/`のCER定義と`apply_output_style`を適用したTransformers BF16 greedy推論である。本人の録音から作った入力と推論出力はfaculty内に置いている。

baselineは同じ入力に対する保存済みMLX出力を、現在の評価集計器で再集計した。valは依頼値のCER 3.72%、用語1,301/1,427（91.17%）と一致した。本人50件は用語60/67（89.55%）は一致したが、CERは4.39%となり、依頼値3.82%と異なる。baseline出力には`dev-user-f`も含まれており、今回の比較ではmanifestと一致する50件だけを集計した（未知ID 50件は除外）。この差の原因は未特定であり、同一manifest・同一集計器での比較には下記4.39%を使う。

### 現行入力の評価結果

| 評価 | SFT2 baseline（MLX） | A: 2回目 | B: 1回目＋採否後2回目 |
| --- | --- | --- | --- |
| 本人50件、用語集全件：CER / 用語 | 4.39% / 60/67 (89.55%) | 5.55% / 57/67 (85.07%) | 6.11% / 58/67 (86.57%) |
| 本人50件、見えない用語を用語集から除外：CER / 用語 | 比較出力なし | 6.71% / 54/67 (80.60%; unseen 14/20) | 6.19% / 58/67 (86.57%; unseen 16/20) |
| val 1,000件：CER / 用語 | 3.72% / 1301/1427 (91.17%) | 3.66% / 1300/1427 (91.10%) | 3.47% / 1305/1427 (91.45%) |
| test-novel 500件、v1+v2用語集から除外83語：CER / 用語 | 比較出力なし | 11.26% / 168/500 (33.60%) | 9.46% / 186/500 (37.20%) |

valではBがAよりCERを0.19ポイント下げた。本人50件ではA/Bとも再集計baselineを上回れず、BのCERはAより0.56ポイント高かった。単一seedの結果で、seed間のばらつきは未測定である。全用語条件のA/B出力と集計はfacultyの`runs/formatter-sft3/term-select-{a,b}-20261122/`および`runs/formatter-sft3/current-{devuser-s50,val}.report.txt`。

test-novelではnovel語を含む1回目と区間結合後の文を使った。入力用語集はv1とv2を統合し、`glossary-v2-excluded.txt`の83語を除いた31,332語である。BはAよりCERが1.80ポイント低く、用語正答率は3.60ポイント高かった。Bの生成は500件中1件が長さ上限に達した。比較対象のSFT2出力は無い。

### 入力長と整形時間

以下の整形時間はbatch生成時間を件数で割ったthroughput換算値で、単発遅延ではない。Bでは入力token数が約2.05倍、prompt token数が約1.11倍になった。整形時間は本人50件で0.1498秒から0.1535秒、valで0.0501秒から0.0526秒へ増加した。

| 評価 | 平均入力token A → B | 平均prompt token A → B | 平均整形時間 A → B |
| --- | ---: | ---: | ---: |
| 本人50件 | 29.46 → 60.38 | 428.24 → 478.94 | 0.1498 → 0.1535秒/件 |
| val 1,000件 | 31.76 → 65.20 | 444.99 → 500.10 | 0.0501 → 0.0526秒/件 |
| test-novel 500件 | 34.78 → 71.33 | 513.52 → 568.38 | 0.0712 → 0.0662秒/件 |

test-novelの生成時間もbatch throughput換算値であり、単発遅延ではない。推論出力と集計はfacultyの`runs/formatter-sft3/test-novel-{a,b}-20261122/`と`runs/formatter-sft3/current-test-novel.report.txt`。

### 継続中の条件

B-2BはBと同じ95,934件の学習データ、2 epoch、seed 0、学習率`2e-5`、実効batch 32、gradient checkpointing、Transformers BF16でfacultyのジョブキューから学習中である。2Bはmicrobatch 4・累積8、0.8BのBはmicrobatch 32・累積1とし、実効batchを揃えた。学習と評価の終了後に同じ現行入力で比較を追記する。

見えない用語を除外した本人50件では、Aはそれ以外40/47 (85.11%)、Bは42/47 (89.36%)だった。出力と集計はfacultyの`runs/formatter-sft3/term-select-{a,b}-no-unseen-20261122/`と`runs/formatter-sft3/current-devuser-s50-no-unseen.report.txt`。

CのASRペアは旧学習文9,990件、v3文12,000件、val1,000件。学習manifestに一致した21,720件を調べ、held-out表記68件、held-out読み153件、test-novel読み4件（理由は重複あり）のいずれかが1回目または採否後文に現れた223件を除いた。Cの実ASR入力は21,497件、音声なし加工は74,437件。checkpoint選択に使う`val-select.jsonl`は970件で、1,000件の新val ASR runからこの970 IDに一致するものを抽出した。監査の件数・SHA-256・生成コードはfacultyの`runs/formatter-sft3/c-input-audit.json`と`runs/formatter-sft3/prepare-c-inputs.py`、学習入力は`inputs/c-asr-20261122/`。Cは同じ2 epoch・seed 0・`2e-5`・実効batch32でfacultyキューに登録済み。B-2BとCの学習・評価の終了後、faculty内の本人録音由来入力と推論出力を削除する。

## 条件Cの学習と評価（2026-11-22）

CはQwen3.5-0.8Bを全パラメータ学習し、入力を1回目＋区間ごとの採否後の2回目にした。学習文95,934件、2 epoch、5,996 step、学習率`2e-5`、seed 0、batch32・累積1、gradient checkpointing有効、worker16、最大長1,024、句読点加工確率0.5、用語集drop確率0.15である。実ASR入力21,497組以外の74,437件は`asr_noise.py`で加工した。選択valは漏れ監査済みの970件を使った。

学習は終了コード0。Trainerの学習時間は7,671.8秒、キュー全体は7,727秒、平均GPU使用率86.6%（256 sample）だった。選択checkpointは`checkpoint-5500`、val lossは0.117835。最終重みは`outputs/formatter-sft3-c-accepted-20261122/final/`にある。評価も両ジョブが終了コード0で、current-ASRの平均GPU使用率は21.8%、test-novelは3.6%だった。C評価はTransformers BF16 greedyで、`apply_output_style`とmainの`voiceime.eval.report`を使った。`causal-conv1d`は未導入のため参照実装へfallbackした。

### 現行ASR入力での比較

下表はmainのCER定義で再集計した値である。本人50件とvalはA/B/Cで同一manifestを使い、本人の用語集はv1、test-novelではv1+v2から除外83語を引いた31,332語を使った。本人録音由来のASR入力と推論出力はfacultyの作業場所にのみ保存している。

| 評価 | SFT2 baseline（MLX） | A: 2回目 | B: 1回目＋採否後2回目 | C: 1回目＋採否後2回目で学習 |
| --- | --- | --- | --- | --- |
| 本人50件、用語集全件：CER / 用語 | 4.39% / 60/67 | 5.55% / 57/67 | 6.11% / 58/67 | 4.56% / 61/67 |
| 本人50件、見えない用語を除外：CER / 用語 | 比較出力なし | 6.71% / 54/67 | 6.19% / 58/67 | 5.76% / 57/67 |
| val 1,000件：CER / 用語 | 3.72% / 1301/1427 | 3.66% / 1300/1427 | 3.47% / 1305/1427 | 3.88% / 1305/1427 |
| test-novel 500件：CER / 用語 | 比較出力なし | 11.26% / 168/500 | 9.46% / 186/500 | 9.41% / 186/500 |

本人の全用語条件ではCがAより0.99ポイント、Bより1.55ポイントCERを下げ、用語は61/67（91.04%）となった。baselineのCER 4.39%はCより0.17ポイント低い一方、用語正答はCの方が1語多い。見えない用語を除く条件ではCのCERがA/Bより低かったが、用語はBの58/67に対しCは57/67だった。valではCのCER 3.88%がBより0.41ポイント高く、baselineより0.16ポイント高かった。test-novelではCとBの用語正答数が同じで、CのCERが0.05ポイント低かった。単一seedの結果であり、seed間のばらつきは未測定。

全用語条件でCは見えない20語中18語、それ以外47語中43語に正解した。見えない用語をプロンプトから除いた場合は、見えない語14/20、それ以外43/47だった。test-novelは初見語を含む用語集で評価し、500語中186語に正解した。SFT2のtest-novel出力は無い。

### 入力長と遅延

`format_latency_mean_s_amortized`はbatch生成wall timeを件数で割ったthroughput換算値で、単発遅延ではない。mainの集計器が出す中央値/p90は、各runのASR遅延と整形遅延を合わせた値である。

| 評価 | 条件 | 平均入力token | 平均prompt token | 整形時間（秒/件） | ASR込み中央値 / p90（秒） |
| --- | --- | ---: | ---: | ---: | ---: |
| 本人50件、全用語 | A | 29.46 | 428.24 | 0.1498 | 0.532 / 0.690 |
|  | B | 60.38 | 478.94 | 0.1535 | 0.533 / 0.704 |
|  | C | 60.38 | 485.94 | 0.1479 | 0.533 / 0.706 |
| val 1,000件 | A | 31.76 | 444.99 | 0.0501 | 0.394 / 0.620 |
|  | B | 65.20 | 500.10 | 0.0526 | 0.392 / 0.623 |
|  | C | 65.20 | 507.10 | 0.0516 | 0.392 / 0.624 |
| test-novel 500件 | A | 34.78 | 513.52 | 0.0712 | 0.533 / 0.813 |
|  | B | 71.33 | 568.38 | 0.0662 | 0.524 / 0.815 |
|  | C | 71.33 | 575.38 | 0.0637 | 0.522 / 0.800 |

B/Cは1回目を追加するため、平均入力tokenはAの約2.05倍、prompt tokenはAより約11%長い。CはBよりprompt tokenが約7多い一方、throughput換算の整形時間は本人50件・val・test-novelでBより短かった。音声長はmanifestに無く、音声長別の遅延は未評価である。

生成JSONLはfacultyの`runs/formatter-sft3/c-current-20261122/`と`runs/formatter-sft3/test-novel-c-20261122/`にある。A/B/Cの集計は`current-devuser-s50-a-b-c.report.txt`、`current-devuser-s50-no-unseen-a-b-c.report.txt`、`current-val-a-b-c.report.txt`、`current-test-novel-a-b-c.report.txt`に保存した。

## 条件B-2Bの学習と評価（2026-11-22）

Bと同じ95,934件のデータ、1回目＋採否後の2回目、2 epoch、seed 0、学習率`2e-5`、実効batch 32、最大長1,024、gradient checkpointing有効で、モデルを`Qwen/Qwen3.5-2B`へ替えて学習した。mainの`train/formatter/model_loader.py`を使い、全パラメータをTransformers BF16で更新した。GPUメモリに合わせ、Bのmicrobatch 32・累積1に対してB-2Bはmicrobatch 4・累積8とし、実効batchは揃えた。DataLoader workerはBの16に対してB-2Bでは4だった。

学習は5,996 stepで終了し、終了コード0。最良checkpointは`checkpoint-5996`、選択val lossは0.125154。Trainer学習時間は18,379秒（5時間6分19秒）、キュー全体は18,527秒（5時間8分47秒）。キューが記録した平均GPU使用率は52.2%（614 sample）だった。faculty環境はPyTorch `2.13.0+cu129`、Transformers `5.23.0`、H100。重みは`outputs/formatter-sft3-b-2b-20261122/final/`に保存した。

### 現行ASR入力の評価

B-2BもA/B/Cと同じ現行ASR入力で評価し、Transformers BF16 greedy、mainの`CER_EQUIVALENT_FORMS`を含む評価定義と`apply_output_style`を使った。本人の読み上げは同じ50件のmanifestを使い、用語集はv1。valは1,000件。test-novelはv1+v2から除外83語を引いた31,332語の用語集を使った。B-2Bの現行ASR評価はキュー終了コード0・平均GPU使用率30.5%、test-novel評価は終了コード0・平均4.2%だった。test-novelの500件中1件は生成長上限に達した。

| 評価 | SFT2 baseline（MLX） | A: 2回目 | B: 1回目＋採否後2回目 | C: 1回目＋採否後2回目で学習 | B-2B: Bと同じ入力で2B学習 |
| --- | --- | --- | --- | --- | --- |
| 本人50件、用語集全件：CER / 用語 | 4.39% / 60/67 | 5.55% / 57/67 | 6.11% / 58/67 | 4.56% / 61/67 | 4.95% / 61/67 |
| 本人50件、見えない用語を除外：CER / 用語 | 比較出力なし | 6.71% / 54/67 | 6.19% / 58/67 | 5.76% / 57/67 | 5.29% / 59/67 |
| val 1,000件：CER / 用語 | 3.72% / 1301/1427 | 3.66% / 1300/1427 | 3.47% / 1305/1427 | 3.88% / 1305/1427 | 3.28% / 1329/1427 |
| test-novel 500件：CER / 用語 | 比較出力なし | 11.26% / 168/500 | 9.46% / 186/500 | 9.41% / 186/500 | 10.47% / 174/500 |

見えない用語を用語集から除いたB-2Bは、見えない用語17/20（85.00%）、それ以外42/47（89.36%）だった。全用語の本人50件ではB-2Bは61/67でCと並んだが、CERは4.95%で再集計SFT2 baselineの4.39%より0.56ポイント高い。見えない用語除外のCERは5.29%で、A/B/Cより低かった。valはB-2Bが今回の比較で最良（3.28%、1329/1427）で、BよりCERを0.19ポイント下げた。test-novelはB/CよりCERが約1ポイント高く、用語正答数も12語少なかった。SFT2 baselineとの直接比較は、MLXとTransformers BF16のruntime差を含む。すべて単一seedであり、seed間のばらつきは未測定。

### 入力長と整形時間

整形時間はbatch生成wall timeを件数で割ったthroughput換算値で、単発遅延ではない。音声長はmanifestに無く、音声長別の遅延は評価できていない。

| 評価 | 条件 | 平均入力token | 平均prompt token | 整形時間（秒/件） | ASR込み中央値 / p90（秒） |
| --- | --- | ---: | ---: | ---: | ---: |
| 本人50件、全用語 | B | 60.38 | 478.94 | 0.1535 | 0.533 / 0.704 |
|  | B-2B | 60.38 | 478.94 | 0.1440 | 0.528 / 0.702 |
| 本人50件、見えない用語除外 | B | 60.38 | 530.30 | 0.1503 | 0.530 / 0.701 |
|  | B-2B | 60.38 | 477.32 | 0.0543 | 0.434 / 0.603 |
| val 1,000件 | B | 65.20 | 500.10 | 0.0526 | 0.392 / 0.623 |
|  | B-2B | 65.20 | 500.10 | 0.0530 | 0.394 / 0.628 |
| test-novel 500件 | B | 71.33 | 568.38 | 0.0662 | 0.524 / 0.815 |
|  | B-2B | 71.33 | 568.38 | 0.0701 | 0.525 / 0.819 |

評価出力はfacultyの`runs/formatter-sft3/b-2b-current-20261122/`と`runs/formatter-sft3/test-novel-b-2b-20261122/`に保存した。mainの評価集計表は`current-devuser-s50-a-b-c-b2b.report.txt`、`current-devuser-s50-no-unseen-a-b-c-b2b.report.txt`、`current-val-a-b-c-b2b.report.txt`、`current-test-novel-a-b-c-b2b.report.txt`にある。学習ログと使用率は`~/voiceime-queue/done/10-formatter-r3-b2b-sft3.{log,util}`、評価ジョブの記録は`~/voiceime-queue/done/30-formatter-r3-b2b-{current-eval,testnovel-eval}.{log,util}`。

## main用語選択での再評価（2026-11-22）

mainの`glossary.py`と選択呼び出しでA/B/C/B-2Bを再評価した。評価はmainの`voiceime.eval.report`、Transformers BF16では`apply_output_style`を使った。SFT2は既存MLX 4bit出力を同じ集計器で再集計した。test-novelの候補用語集31,332語で、正解語が一覧に入った件数は343/500となり、旧選択による133/500を訂正した。

初回は各formatter入力から動的に用語を選んだ。AとSFT2の入力文・一覧は本人50件、val1,000件、test-novel500件ですべて一致した。B/C/B-2Bは1回目の文も選択に使うため、SFT2と完全に同じ一覧だったのはtest-novelの218/500件である。初回の表と、用語一覧の一致件数、整形時間、本人CERの照合は`runs/formatter-sft3/main-glossary-dynamic-reeval-20261122.md`に記録した。test-novelの初回結果はSFT2 225/500、A 197/500、B 243/500、C 234/500、B-2B 232/500。

本人50件のSFT2 baselineは同じ50 ID、同じ入力文、同じ用語一覧でAと50/50一致し、main評価器で102/2,325文字、CER4.39%となった。PM手元の3.82%との差は一覧では説明できない。比較元manifestまたは集計処理が不明なため、原因は未特定。

SFT2の保存済み用語一覧をIDごとに固定する再評価を優先度05のfaculty jobへ登録した。本人50件とvalでは保存済みSFT2出力の配列、test-novelではSFT2 baseline配列を使う。見えない用語を除く本人評価では、その除外一覧を適用して動的選択する。再評価結果は完了後にこの記録へ追記する。本人由来の推論JSONLはfaculty内に残す。

## main選択の学習変種とSDPA障害（2026-11-22）

学習用語の選択もmainの`select_glossary`を使う。比較条件はdrop 0 / distractors 8、drop 0.15 / distractors 0、drop 0 / distractors 0で、2 epoch、seed 0、実効batch32、同じ学習率とデータを使う。初回の2条件がstep 1,304/5,996でPyTorch `mha_graph.execute`の失敗を起こした。cuDNN SDPAが選ばれたときの実行エラーと見られるが、根本原因は未特定。

PyTorch 2.13.0+cu129に`torch.backends.cuda.enable_cudnn_sdp(False)`があり、実行環境で有効/無効を切り替えられることをCPU側で確認した。失敗した条件を含む3条件はcuDNN SDPAを無効にした新しい出力先へ再投入した。これによりPyTorchが選ぶSDPA backendが変わるため、`train_summary.json`の`cudnn_sdp_enabled`とqueue使用率を確認し、結果の解釈に実行backendの差を明記する。途中checkpointを最終結果に使わない。

## SFT2と同じ用語一覧での再評価（2026-11-22）

動的に選んだ用語一覧による先の再評価では、B/C/B-2Bのtest-novel一覧がSFT2と218/500件しか一致しなかった。このためSFT2の保存済み一覧を全モデルへIDごとに固定して再評価した。A/B/C/B-2Bとも、test-novelの500行で表記と順序がSFT2と500/500一致し、正解語が一覧に入った件数は343/500だった。候補語はv1＋v2から除外83語を除いた31,332語、上限20語。本人50件とval1,000件でも、A型の2回目だけの入力文と一覧はSFT2保存出力に一致した。

SFT3推論は複数ASR文の比較指示を含む現在の`prompt.py`を使った。SFT2の保存済み出力は旧system指示で生成されたため、SFT2との差はモデル・runtimeだけでなく指示文の変更も含む。

| 系統 | 本人50件、全用語：CER / 正答 | 本人50件、見えない用語除外：CER / 正答 | val 1,000件：CER / 正答 | test-novel 500件：CER / 正答 |
| --- | --- | --- | --- | --- |
| SFT2（MLX 4bit） | 4.39% / 60/67 | 比較出力なし | 3.72% / 1301/1427 | 10.83% / 225/500 |
| A: 2回目だけ | 5.55% / 59/67 | 5.98% / 56/67（見えない14/20） | 3.68% / 1309/1427 | 10.40% / 197/500 |
| B: 1回目＋2回目 | 5.89% / 58/67 | 5.38% / 58/67（見えない16/20） | 3.31% / 1307/1427 | 8.26% / 253/500 |
| C: 1回目＋採否後の文 | 5.98% / 59/67 | 7.27% / 55/67（見えない13/20） | 3.40% / 1315/1427 | 8.37% / 243/500 |
| B-2B: B入力、2B | 4.52% / 61/67 | 4.43% / 61/67（見えない18/20） | 3.12% / 1328/1427 | 9.15% / 240/500 |

test-novelで一覧に正解語がある場合、SFT2は218/343 (63.6%)、Aは189/343 (55.1%)、Bは235/343 (68.5%)、Cは228/343 (66.5%)、B-2Bは234/343 (68.2%)だった。一覧に正解語が無い場合は順に7/157、8/157、18/157、15/157、6/157。BはSFT2より合計28語多く正解した。未出力語の文字列分類ではBが「読みのまま」1件、「別出力」81件、「脱落」26件。分類方法は`SequenceMatcher`で正解語位置に対応する置換文字を推定するもので、語義上の置換判定ではない。

本人50件のSFT2出力とAの入力・用語一覧は同一50 IDで一致したが、現行CERは102/2,325文字、4.39%となり、PM手元の3.82%は再現しなかった。SFT2出力ファイルは100行、今回のmanifestは50行で、残り50行は未知IDとして集計から除外された。3.82%側のmanifest・対象行・正規化条件は未確認で、原因は未解決。

推論はSFT2がMLX 4bit、SFT3がTransformers BF16である。BはAより平均入力tokenが約2.05倍、平均prompt tokenが約11%増えた。batch生成時間を件数で割った整形時間は、valでA/B/C/B-2Bが0.0493/0.0504/0.0503/0.0520秒/件、test-novelで0.0609/0.0632/0.0615/0.0718秒/件。これはbatch throughput換算値で単発遅延ではない。test-novelの一覧内外正表記率の図は[PNG](../../figures/formatter-sft3/test-novel-glossary-selection-accuracy.png)、全条件の集計・分類・入力照合は`runs/formatter-sft3/main-glossary-frozen-reeval-retry1-20261122.md`にある。本人読み上げの行別出力はfacultyにのみ保存した。

main選択を学習へ使う0.8B変種はfaculty queueで継続中。2026-11-22 19:02 JST時点でdrop 0/distractors 0のSDPA fallback版は1,961/5,996 step、drop 0.15/distractors 0のSDPA fallback版は1,759/5,996 step。drop 0/distractors 8の旧backend実行は3,463/5,996 stepで、新backendの再実行はpending。旧backend出力は公平な最終ablationには使わない。結果、平均GPU使用率、完了状態は学習後に追記する。

監査の再実行では、入力書き出しのsystem/user promptを現在の`src/voiceime/formatter/prompt.py`の定数から組み立てた。test-novelは500 IDがすべて一意で、A/B/C/B-2Bの実入力形式の照合は各500/500、SFT2と同じ選択語順も各500/500、正解語の一覧内件数も各343だった。入力JSONLには参照文・仮説を含めず、合成test-novelの入力文と用語一覧を保存した。監査結果は`runs/formatter-sft3/main-glossary-frozen-reeval-retry1-20261122/test-novel-audit-summary.json`にある。

### main選択variantの旧backend試行

drop 0／distractors 8の旧backend試行は2 epoch・5,996 stepを終了し、best checkpointは`checkpoint-5500`、選択val損失0.13121、train loss 0.06726、Trainer時間6,543秒だった。queue記録は終了コード0、GPU3、6,702秒、平均使用率94.0%（222 sample）。ただし、他2条件でcuDNN SDPA実装がstep 1,304で失敗したため、この試行は公平なablation比較に含めず、全3条件をSDPA fallback設定で再実行している。

### main選択学習変種の暫定評価（凍結SFT2用語一覧）

mainの用語選択を学習に使った変種のうち、`drop=0, distractors=0`と`drop=0.15, distractors=0`が完了した。比較用にSFT2の保存済み用語一覧を固定して評価したため、これは各変種の通常のmain選択による推論評価ではない。main選択での全モデル再評価は、残る`drop=0, distractors=8`の学習完了後に別途行う。

| 条件 | 本人50件 CER / 用語 | val CER / 用語 | test-novel CER / 用語 | test-novelで一覧内の正解語 / 一覧内正答率 |
| --- | --- | --- | --- | --- |
| 既存B（drop 0.15, distractors 8） | 5.89% / 58/67 | 3.31% / 1307/1427 | 8.26% / 253/500 | 235/343 (68.5%) |
| drop 0, distractors 0 | 6.15% / 59/67 | 3.59% / 1295/1427 | 7.93% / 286/500 | 274/343 (79.9%) |
| drop 0.15, distractors 0 | 5.16% / 57/67 | 3.82% / 1305/1427 | 8.13% / 263/500 | 250/343 (72.9%) |
| drop 0, distractors 8 | 5.98% / 58/67 | 3.40% / 1309/1427 | 8.24% / 280/500 | 267/343 (77.8%) |

凍結一覧での未採用内訳は、Bが108件（別出力81、脱落26、読みのまま1）、drop 0／distractors 0が69件（別出力58、脱落11）、drop 0.15／distractors 0が93件（別出力71、脱落20、読みのまま2）、drop 0／distractors 8が76件（別出力58、脱落17、読みのまま1）だった。dropを維持して無関係語の混入だけを止めた変種はBより一覧内正答を15件増やしたが、val CERは0.51ポイント悪化した。dropだけを0にした変種は一覧内正答を32件増やし、val用語正答は2件多いがCERは0.09ポイント悪化した。dropも同時に0にした変種は一覧内正答を39件増やしたが、2要因の変更なのでdrop単独の効果とは言えず、val用語正答も12件少ない。3条件ともtest-novelの総正答はSFT2の225/500を上回ったが、凍結一覧のval CERはBを下回らず、指定目標を満たす変種はなかった。

-学習はいずれも2 epoch、5,996 step、seed 0、学習率`2e-5`、実効batch 32。cuDNN SDPAを無効にした同じfallback環境で学習した。`drop=0, distractors=0`はbest checkpoint 5,750、best val loss 0.128180、Trainer時間6,718秒、queue時間6,863秒、平均GPU使用率92.6%。`drop=0.15, distractors=0`はbest checkpoint 5,750、best val loss 0.128116、Trainer時間6,658秒、queue時間6,802秒、平均GPU使用率92.7%。`drop=0, distractors=8`はbest checkpoint 5,500、best val loss 0.130523、train loss 0.067080、Trainer時間6,692秒、queue時間6,835秒、平均GPU使用率93.2%で終了した。3条件ともDataLoader worker 16、gradient checkpointing有効、実効batch32。

集計元は`runs/formatter-sft3/mainselect-b-clean-sdpa-fallback-20261122/`、`runs/formatter-sft3/mainselect-b-distractors0-sdpa-fallback-20261122/`、`runs/formatter-sft3/mainselect-b-drop0-sdpa-fallback-20261122/`。一覧内外・未採用分類は`runs/formatter-sft3/frozen-list-variants-drop0-audit-summary.json`に保存した。本人録音の行別出力はfaculty内に残し、ローカルへは持ち帰っていない。

## faculty旧用語選択器（1:1）による7条件再評価（2026-11-22）

この再評価ではfaculty複製の`src/voiceime/formatter/glossary.py`（SHA-256 `e4972d5fd93d31e6ed2bb002481b8371424cc69b3ea48528c085e3ed3555e10d`）が使われた。後から確認すると、これはmainの現行版（SHA-256 `e9db1b5d7ba52703300b4cb29099f2cb8da791361f6f895e931eac5f75eeedfa`）と異なり、順位の交互比率が1:1だった。したがって、以下の表は旧選択器による参考値であり、現行mainの最終比較には使わない。A/B/C/B-2BとB系3変種はTransformers BF16、greedy、batch32、用語上限20、同じ現行ASR入力で評価した。SFT2は保存済みMLX出力の参考値。

| 条件 | 本人50件 CER / 用語 | 見えない用語除外 CER / 用語 | val CER / 用語 | test-novel CER / 正答 |
| --- | --- | --- | --- | --- |
| SFT2（MLX 4bit、既報） | 4.39% / 60/67 | — | 3.72% / 1301/1427 | 10.83% / 225/500 |
| A | 5.55% / 59/67 | 5.98% / 56/67 | 3.68% / 1309/1427 | 10.40% / 197/500 |
| B | 5.72% / 58/67 | 5.38% / 58/67 | 3.31% / 1310/1427 | 8.35% / 243/500 |
| C | 5.81% / 59/67 | 7.27% / 55/67 | 3.41% / 1315/1427 | 8.54% / 234/500 |
| B-2B | 4.56% / 61/67 | 4.43% / 61/67 | 3.14% / 1329/1427 | 9.27% / 232/500 |
| B-clean | 5.94% / 60/67 | 7.27% / 53/67 | 3.67% / 1297/1427 | 8.16% / 281/500 |
| B-drop0 | 5.42% / 60/67 | 7.01% / 56/67 | 3.48% / 1306/1427 | 8.10% / 278/500 |
| B-no-distractors | 5.46% / 57/67 | 6.67% / 56/67 | 3.77% / 1307/1427 | 7.78% / 252/500 |

test-novelの正解語343件が7条件すべての一覧に入り、候補一覧外の出力は0件だった。B-cleanとB-drop0は一覧内正答265/343 (77.3%)、263/343 (76.7%)で、Bの222/343 (64.7%)より高かった。一方、どの変種もval CERはBの3.31%より悪く、Bの用語正答1310件を下回ったため、val条件とSFT2超えを同時に満たす変種は無かった。

1回目＋2回目入力では入力ASR tokenが平均60.38（本人）、65.20（val）、71.33（test-novel）で、Aの2回目だけ入力の29.46、31.76、34.78より長い。promptは本人で466.78対414.58 token、test-novelで521.88対471.04 tokenだった。整形時間はbatch throughput換算でBが0.1479/0.0470/0.0607秒/件、Aが0.1451/0.0501/0.0606秒/件（本人/val/test-novel）。`causal_conv1d`未導入で参照実装へfallbackした警告が出ており、時間は最適化kernel使用時より長い可能性がある。

全指標、選択語の内外別成績、失敗型、入力長・遅延は[`runs/formatter-sft3/main-selector-reeval-20261122.md`](../../runs/formatter-sft3/main-selector-reeval-20261122.md)に記録した。合成test-novelの実入力と選択一覧は`runs/formatter-sft3/inputs/test-novel-main-selector-actual-inputs.jsonl`、監査集計は`runs/formatter-sft3/main-selector-reeval-20261122/test-novel-audit-summary.json`。本人録音の行別出力はfaculty内に残した。

## 本人用manifest修正後の再集計（2026-11-22）

手元の`data/dev-user/manifest.jsonl`（SHA-256 `f6e6984bba39ea79241a451941e21c5461296026db0ba42520950bea58880f0b`）とfacultyにあった旧manifest（`15009248c7152e391a03f1f577a0b5429aa7b0a839595319ac0286128400dfa8`）は異なった。修正版は100行で、旧評価に使った50 IDはすべて含まれていた。残り50行は今回の比較対象外の自由発話だったため、旧評価と同じ50 IDを抽出し、facultyに無い`audio_path`だけを外して再集計した。50 ID内で変わったのは正解文5件（s013、s020、s033、s038、s046）と`s020`の`list`タグだけ。再集計manifestのSHA-256は`f3cfb4058713742c84a16fb6fb9878f2902d9959e55888b04d5f0da6b85f5309`。

保存済み推論出力を旧manifestと修正版manifestで別々に集計した。第2弾は旧版で102/2,325文字（4.39%）、修正版で89/2,330文字（3.82%）となり、PM手元の値と一致した。推論をやり直さずに差が再現したため、用語一覧やモデル差ではなく、正解文の修正がCER差の直接要因と確認できた。行別の本人用JSONLはfacultyに残し、ローカルへ移していない。

| 条件 | 本人50件 CER / 用語 | 見えない用語除外 CER / 用語 |
| --- | --- | --- |
| SFT2 | 3.82% / 60/67 | — |
| A | 5.24% / 59/67 | 5.67% / 56/67 |
| B | 5.41% / 58/67 | 5.06% / 58/67 |
| C | 5.75% / 59/67 | 7.21% / 55/67 |
| B-2B | 4.42% / 61/67 | 4.29% / 61/67 |
| B-clean | 5.62% / 60/67 | 6.95% / 53/67 |
| B-drop0 | 5.36% / 60/67 | 6.95% / 56/67 |
| B-no-distractors | 5.15% / 57/67 | 6.35% / 56/67 |

これは前節のmain選択再評価で保存した出力の再集計で、valとtest-novelの値は変更していない。集計JSONと表は`runs/formatter-sft3/corrected-devuser-reeval-20261122/`に保存した。

## drop 0追試：旧選択器での試行（中止）

2026-11-22に次の3条件をfacultyジョブキューへ登録したが、選択器が現行mainと異なることが判明したため、部分checkpointを最終結果に使わず停止した。3条件ともB入力、学習率`2e-5`、2 epoch、実効batch32、seedは条件名の通り、無関係語上限8、用語drop 0。0.8Bはmicrobatch32・累積1・worker16、2Bはmicrobatch4・累積8・worker4。全パラメータ更新、gradient checkpointingあり、最大長1,024 token。

| 条件 | モデル | 学習データ | seed | 状態 |
| --- | --- | --- | ---: | --- |
| B-2B-drop0 | Qwen3.5-2B | Bと同じ95,934行 | 0 | 停止（GPU1、rc=143） |
| B-drop0-focus | Qwen3.5-0.8B | 両方のASR文で崩れ、旧1:1選択器の一覧に正解語がある行を2回露出 | 0 | 停止（GPU2、rc=143） |
| B-drop0-seed1 | Qwen3.5-0.8B | Bと同じ95,934行 | 1 | 停止（GPU3、rc=143） |

queue記録の停止前平均使用率はfocus 91.2%（683秒）、2B 72.9%（668秒）、seed1 94.8%（1,224秒）。

focus用データは旧選択器で条件に合った実ASR行1,539件を重複し、同数の対象外行を固定seed `20261122` で置き換えた。総行数は95,934で、1 epochあたり5,996 step、valは変更していない。旧focus入力SHA-256は`93f18571443c3b105dfdc2e1f5a0319240b826941724c1f64f47128ad57cf0e0`。停止済みジョブのログとpartial checkpointはfacultyに残し、再利用しない。


## drop 0追試：現行main選択器（2:1）

mainの現行選択器をfacultyへ反映してから、focus用データを作り直し、同じ3条件を新しい出力先へ再登録する。学習は全条件で同じselector SHAを使い、旧試行の部分checkpointは使わない。評価のlauncherも修正版manifestと現行selectorを使う。

現行selectorのSHA-256は`e9db1b5d7ba52703300b4cb29099f2cb8da791361f6f895e931eac5f75eeedfa`。focus条件の再作成では、元データ95,934行中、両ASR passがある9,522行を調べ、正解語の出現11,393件を確認した。うち両方のASR文に表記・読みがなく、現行選択一覧に正解語がある1,585行を一度ずつ重複し、同数の非focus行を固定seed `20261122` で差し替えた。出力も95,934行、SHA-256 `dd0098d6199579ad0daecd59e1783821769e717ed3c093da2c8c2c5d4a34b515`。valデータは変更していない。

2026-11-22 22:59 JSTに3条件をpriority 10でfaculty queueへ登録した。キュー登録時点ではGPU1〜3は空き、GPU0は他の利用者が使用中。各ジョブが開始したGPU、使用率、学習結果は完了後に追記する。

2026-11-23 00:01 JST時点でfocus 3,207/5,996 step、seed1 3,205/5,996、2B 1,832/5,996。最新checkpointはそれぞれ3,000、3,000、1,750。queueの途中計測平均使用率はfocus 93.7%、seed1 94.2%、2B 77.8%（各120サンプル）。2Bはval評価中にGPU使用率が下がる区間があり、直近の利用率は98%。学習と評価は継続中で、途中checkpointは比較結果に使わない。

2026-11-23 00:54 JSTまでにfocusとseed1の学習が終了し、両方とも終了コード0。focusはGPU1、6,736秒、平均使用率93.8%（223サンプル）、best checkpoint `checkpoint-5500`、val loss 0.129856。seed1はGPU2、6,755秒、平均使用率93.5%（224サンプル）、best checkpoint `checkpoint-5996`、val loss 0.129609。両者ともcuDNN SDPA無効、実効batch32、2 epoch、学習率`2e-5`、drop 0、無関係語上限8。

focus/seed1の現行selector評価launcherはpriority 20でqueue待ち。B-2B-drop0は同時点で3,455/5,996 step、GPU3で継続中。各モデルの評価結果と全条件表は評価完了後に追記する。

## 現行main選択器によるdrop 0再学習の結果（2026-11-23）

### 仮説と条件

用語のdropを0にすると、モデルへ一覧を渡した初見語を正しい表記で出す割合が上がると予想した。さらに、両方のASR文で用語が崩れ、かつ現行一覧に正解語が含まれる学習例を増やすと、一覧の語を採る率が上がると予想した。

追加した3条件はB形式（1回目＋2回目）、v3を含む同じ95,934行、同じval、seed以外の設定を固定した。共通設定は全パラメータ更新、2 epoch・5,996 step、学習率`2e-5`、実質batch 32、最大長1,024 token、gradient checkpointing有効、用語drop 0、無関係語上限8、現行main用語選択器SHA-256 `e9db1b5d7ba52703300b4cb29099f2cb8da791361f6f895e931eac5f75eeedfa`。0.8Bはmicrobatch 32・累積1・worker 16、2Bはmicrobatch 4・累積8・worker 4とした。

| 条件 | モデル／seed | 学習データ | 最良checkpoint／val loss | GPU／キュー時間／平均使用率 |
| --- | --- | --- | --- | --- |
| B-drop0-focus | Qwen3.5-0.8B／0 | 95,934行。focus例1,585行を各1回追加し、同数の非focus行と置換。出力SHA-256 `dd0098d6199579ad0daecd59e1783821769e717ed3c093da2c8c2c5d4a34b515` | 5,500／0.129856 | GPU1／6,736秒／93.8%（223 sample） |
| B-drop0-seed1 | Qwen3.5-0.8B／1 | B-drop0と同じ95,934行 | 5,996／0.129609 | GPU2／6,755秒／93.5%（224 sample） |
| B-2B-drop0 | Qwen3.5-2B／0 | Bと同じ95,934行 | 5,500／0.127688 | GPU3／11,561秒／79.9%（383 sample） |

0.8Bはrevision `2fc06364715b967f1860aea9cf38778875588b17`、2Bは`15852e8c16360a2fea060d615a32b45270f8a8fc`。GPU処理はすべてキュー経由。新しい0.8Bの3条件はcuDNN SDPA無効、B-2B-drop0は有効だった。既存BとB-2Bの`train_summary.json`にはbackend設定が記録されていないため、新旧条件間のbackend一致は確認できず、dropの効果だけを切り分ける比較には限界がある。

### 評価結果

本人の読み上げは修正済みmanifestの同じ50 ID（SHA-256 `f3cfb4058713742c84a16fb6fb9878f2902d9959e55888b04d5f0da6b85f5309`）を使った。SFT2は保存済み出力を再集計し、推論はやり直していない。valは1,000件、test-novelは500件。SFT3はTransformers BF16 greedyで生成し、mainの`apply_output_style`と評価定義を使った。SFT2保存済み出力へも現行の`apply_output_style`を適用したとき、本人・val・test-novelのいずれも変更行は0件だった。

| 条件 | 本人50件 CER／用語 | 見えない用語除外 CER／用語 | val CER／用語 | test-novel全体 | 一覧内正答 | 一覧外正答 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SFT2 | 3.82%／60/67 | — | 3.72%／1301/1427 | 225/500 | 218/343（63.6%） | 7/157（4.5%） |
| A | 5.24%／59/67 | 5.67%／56/67 | 3.70%／1309/1427 | 197/500 | 191/349（54.7%） | 6/151（4.0%） |
| B | 5.41%／58/67 | 5.06%／58/67 | 3.29%／1311/1427 | 247/500 | 228/354（64.4%） | 19/146（13.0%） |
| C | 5.75%／59/67 | 7.21%／55/67 | 3.41%／1316/1427 | 240/500 | 223/354（63.0%） | 17/146（11.6%） |
| B-2B | 4.42%／61/67 | 4.29%／61/67 | 3.13%／1329/1427 | 233/500 | 226/354（63.8%） | 7/146（4.8%） |
| B-clean | 5.62%／60/67 | 6.95%／53/67 | 3.63%／1300/1427 | 286/500 | 272/354（76.8%） | 14/146（9.6%） |
| B-drop0 | 5.36%／60/67 | 6.95%／56/67 | 3.48%／1308/1427 | 282/500 | 269/354（76.0%） | 13/146（8.9%） |
| B-no-distractors | 5.15%／57/67 | 6.35%／56/67 | 3.73%／1308/1427 | 257/500 | 243/354（68.6%） | 14/146（9.6%） |
| B-drop0-focus | 4.12%／59/67 | 5.67%／55/67 | 3.60%／1297/1427 | 271/500 | 261/354（73.7%） | 10/146（6.8%） |
| B-drop0-seed1 | 5.02%／57/67 | 6.22%／54/67 | 3.51%／1292/1427 | 284/500 | 274/354（77.4%） | 10/146（6.8%） |
| B-2B-drop0 | 4.85%／58/67 | 5.32%／58/67 | 3.53%／1305/1427 | 278/500 | 264/354（74.6%） | 14/146（9.6%） |

test-novelの用語poolは第1版＋第2版から除外83語を引いた31,332語。全500 IDでASR入力の照合に通過した。B形式の全条件はBと同じ用語一覧を500/500件で使った。一方、AはBとの一覧一致が218/500件、SFT2の保存済み一覧とBの完全一致（順序を含む）は68/500件だった。SFT2では正解語が343件、現行B一覧では354件に含まれていたため、test-novelの全体正答数をSFT2とSFT3の同条件比較として扱わない。現行B入力条件同士の一覧内率は同じ354件を対象にしている。

一覧内で正解できなかった主な出力型は、読みのまま、別表記・別語、脱落だった。Bは93件が別出力、32件が脱落、1件が読みのまま。B-drop0は66件が別出力、18件が脱落、1件が読みのまま。B-drop0-focusは68件が別出力、24件が脱落、1件が読みのまま。B-drop0-seed1は62件が別出力、18件が脱落し、B-2B-drop0は69件が別出力、21件が脱落した。

### 分析と次の仮説

drop 0の0.8B seed 0は、Bより一覧内正答が41件増えた（228→269/354）が、val CERは0.19ポイント悪化し、用語正答は3件減った。focus版はBより一覧内正答が33件増えたが、val CERは0.31ポイント悪化し、用語正答は14件減った。seed 1ではseed 0よりtest-novel全体が2件増えた一方、val CERは0.03ポイント悪化し、val用語正答は16件減った。seedは各1回のため、この差が乱数によるばらつきとして十分かは未確定である。

2B-drop0はB-2Bより一覧内正答が38件増え（226→264/354）、test-novel全体は45件増えた一方、val CERは0.40ポイント悪化し、val用語正答は24件減った。既存B-2Bがval CER 3.13%・用語1329/1427で最良。今回の追加学習条件では、Bのval CERと用語正答を両方維持しながら一覧内正答を上げたものは無かった。SFT2とのtest-novel全体数は一覧数と選択内容が違うため、改善の結論には使わない。

現行の候補では、seed 1のB-drop0が一覧内正答率77.4%で最高だったが、Bよりvalが悪い。B-drop0とseed1は同じ設定でseedだけを変えた比較で、val CERは3.48%から3.51%、用語正答は1308から1292、test-novel全体は282から284、一覧内正答率は76.0%から77.4%となった。各seedは1回のため、差をseed由来の分散とみなせるかは確定していない。

次はSFT2と同じ正解語集合を明示的に揃えたtest-novelの対比較を行い、一覧差とモデル差を分ける。並行して、一覧内の失敗を減らしつつvalを維持する追加学習では、seed間の追加反復を含めて確認する。

### batch 1の整形遅延

val 1,000件をB入力・greedy・batch 1で測った。CUDA同期を含めて`model.generate()`だけを計測し、モデル読み込みとtokenizeは除外した。facultyのH100での値で、Mac上の実遅延ではない。

| モデル | 件数 | 中央値 | 平均 | p90 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5-0.8B | 1,000 | 0.448秒 | 0.520秒 | 0.862秒 |
| Qwen3.5-2B | 1,000 | 0.459秒 | 0.528秒 | 0.881秒 |

計測ログには`causal_conv1d`が未導入のため参照PyTorch実装へfallbackした警告があり、最適化kernelを使った速度ではない。実行結果は[`runs/formatter-sft3/mainselector21-final-20261123/table.md`](../../runs/formatter-sft3/mainselector21-final-20261123/table.md)、一覧内正答率とval CERの比較図は[`figures/formatter-sft3/mainselector21-val-vs-testnovel-listed-accuracy.png`](../../figures/formatter-sft3/mainselector21-val-vs-testnovel-listed-accuracy.png)。図はB形式5条件で一覧内正答率とval CERを示す。val用語正答数は上の表で確認する。

集計表は[`runs/formatter-sft3/corrected-all-results-mainselector21-20261123/table.md`](../../runs/formatter-sft3/corrected-all-results-mainselector21-20261123/table.md)、一覧・入力監査は[`runs/formatter-sft3/test-novel-audit-summary-mainselector21-all-corrected-20261123.json`](../../runs/formatter-sft3/test-novel-audit-summary-mainselector21-all-corrected-20261123.json)、モデルへ渡したtest-novelの入力・一覧は[`runs/formatter-sft3/inputs/test-novel-mainselector21-all-corrected-20261123.jsonl`](../../runs/formatter-sft3/inputs/test-novel-mainselector21-all-corrected-20261123.jsonl)。本人の行別入力と推論出力は、集計後にfacultyの作業場所から削除した。
