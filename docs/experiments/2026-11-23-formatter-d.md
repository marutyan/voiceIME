# 整形LLM第3弾D：多言語ASRの仮説を加える（2026-11-23）

## 仮説と比較

Haasの1回目にQwen3-ASR 0.6Bの仮説を加えて用語を選ぶと、用語が一覧に入る率は上がる。一方、既存整形LLMは多言語ASRの仮説を使う学習をしていないため、一覧の改善が出力正答へ十分反映されない可能性がある。条件Dでは、Haas 1回目、区間単位の採否を反映したsegment-merge文、Qwen仮説、整形用語一覧を一つの入力に含める。

## 入力形式と実装

`FormatterInput`に`qwen_hypothesis`欄を加え、学習・評価で同じprompt定義を共有する。学習データ変換は複数のASR runをIDで照合し、Haas 1回目、segment-merge文、Qwen仮説、構造化用語一覧を分けて保存する。評価経路はQwen仮説を空にできるため、本人の読み上げ50件の参考評価にも使う。

変更箇所は`src/voiceime/formatter/prompt.py`、`train/formatter/train.py`、`train/formatter/eval_transformers.py`、`tests/formatter/test_formatter.py`、`runs/formatter-sft3/prepare_multiasr_runs.py`、`runs/formatter-sft3/audit_multiasr_eval.py`、`runs/formatter-sft3/audit_d_eval.py`。小さなCPU動作確認ではprompt、学習データ組み立て、test-novel用語読込、評価入力の準備を確認した。リモートの学習・評価CLI起動確認も通過した。`audit_d_eval.py`は通常の入力とQwen出力が空のfixtureで、入力一致と一覧内外の件数を確認しPASS。`bash -n`とPython構文確認もPASS。手元とfaculty環境のPythonにpytestが無いため、pytestは未実行。外部selector一覧を固定用語行にも適用する学習・検証のCPU動作確認はPASS。

## 既存重みの多言語ASR併用評価

Qwen併用ASR出力は`~/voiceime-work-asr/r3-multiasr-20261122/outputs/`から読み、既存モデルB、B-2B、B-drop0-seed1、B-2B-drop0を追加学習なしで評価した。Haas 1回目は従来の入力を維持し、2回目と用語一覧をQwen併用版に置き換えた。Qwen併用用語一覧は上限20語で、test-novel正解語369/500件、val正解語1,312/1,427件を含んだ。

既存重みの追加評価とDの学習後評価は`apply_output_style`を適用し、mainの`src/voiceime/eval/`定義でCERと用語を集計した。評価はfacultyのTransformers BF16 greedy推論を使った。

| 条件 | 入力 | val CER | val用語 | test-novel用語 | 一覧内正答 |
| --- | --- | ---: | ---: | ---: | ---: |
| SFT2 | 従来の保存済み入力・一覧 | 3.72% | 1301/1427 | 225/500 | 218/343 |
| B | 従来のB入力・一覧 | 3.29% | 1311/1427 | 247/500 | 228/354 |
| B | Qwen plain | 3.44% | 1313/1427 | 177/500 | 164/369 |
| B | Qwen segment-merge | 3.10% | 1328/1427 | 252/500 | 235/369 |
| B-2B | 従来のB入力・一覧 | 3.13% | 1329/1427 | 233/500 | 226/354 |
| B-2B | Qwen plain | 3.23% | 1328/1427 | 167/500 | 156/369 |
| B-2B | Qwen segment-merge | 3.15% | 1333/1427 | 249/500 | 237/369 |
| B-drop0-seed1 | 従来のB入力・一覧 | 3.51% | 1292/1427 | 284/500 | 274/354 |
| B-drop0-seed1 | Qwen plain | 3.42% | 1302/1427 | 250/500 | 239/369 |
| B-drop0-seed1 | Qwen segment-merge | 3.23% | 1319/1427 | 289/500 | 277/369 |
| B-2B-drop0 | 従来のB入力・一覧 | 3.53% | 1305/1427 | 278/500 | 264/354 |
| B-2B-drop0 | Qwen plain | 3.63% | 1310/1427 | 238/500 | 225/369 |
| B-2B-drop0 | Qwen segment-merge | 3.30% | 1323/1427 | 276/500 | 260/369 |

従来条件とQwen条件では、2回目の本文と用語一覧が違うため、全体の増減をQwen仮説だけの効果とは解釈しない。Qwen plainの2回目はHaas 1回目と同じ本文で、用語一覧のみQwen併用版に変わる。4モデルともsegment-mergeはplainよりtest-novel用語正答が増え、Bは+75語、B-2Bは+82語、B-drop0-seed1は+39語、B-2B-drop0は+38語だった。モデルへ渡した入力の一致と一覧内正答の詳細は[`runs/formatter-sft3/multiasr-reeval-20261123/table.md`](../../runs/formatter-sft3/multiasr-reeval-20261123/table.md)と同ディレクトリの監査JSONにある。

評価ジョブはキュー経由で実行した。Bは147秒・平均GPU使用率27.6%、B-2Bは148秒・38.2%、B-drop0-seed1は143秒・23.0%、B-2B-drop0は147秒・52.0%だった。使用率を上げるための再試行は行っていない。

## D学習データの到着状況

ASR担当の生成はfacultyの`~/voiceime-work-asr/r3-multiasr-train-20261123/`で進行中である。2026-11-23 10:33 JST時点の`outputs/input-metadata.json`では、第3弾文章56,971行中、音声がある学習行は12,000件、音声が無い行は44,971件、valは1,000件だった。11:00 JSTには3つのASR shardが終了コード0となり、統合候補の12,000件が出力された。出力READMEと統合処理はまだ無い。

既存B学習の95,934行中、Haas実出力と対応する行は9,522件。これらはASR担当のv3 manifestには含まれないが、Qwen ASRの既存train manifestに全9,522 IDと音声ファイルがあることを確認した。入力範囲を揃えるため、同じQwen3-ASR 0.6B推論関数で旧9,522行を補うジョブを優先度36でキューに登録した。初回は`python-deps`が`PYTHONPATH`に無く`soundfile`を読み込めず終了コード1。retry1ではQwen環境のsite-packagesを指定せず`torch`を読み込めず、retry2ではQwen-ASRのソースディレクトリを解決できず、いずれもGPU使用率0%で終了した。Qwen環境のsite-packages、`python-deps`、Qwen-ASR source、ASR担当のmain-codeとscriptを明示した隔離環境のCPU import確認はPASS。確認環境はPyTorch `2.11.0+cu128`、Transformers `4.57.6`、soundfile `0.14.0`。retry3を再登録した。ASR担当の出力ディレクトリは変更していない。本番学習は新旧両方の実ASR行の入力と用語一覧を照合するまで作成しない。

D学習の比較条件は、0.8B・drop 0.075、2B・drop 0.075、0.8B・drop 0、その他は共通。seed 0、2 epoch、学習率`2e-5`、実効batch 32、同じSDPA backendとする。学習データとASR対応行が揃った後、用語poolへの漏れを監査し、3条件をキューへ投入する。

音声なしの学習行74,412件は`asr_noise.py`でHaas 1回目とsegment-merge相当の文を作り、Qwen欄は空にする。Qwen-ASRは音声入力がない行について仮説を出しておらず、Qwenの証拠を人為的に作らないためである。実ASR行21,522件では3つのASR文とselector一覧を使う。

## ファイルと転送範囲

新しい評価JSONL、summary、監査入力の合計転送量は19,945,801 bytesで、上限25MB以内。対象は合成val/test-novelの入力・出力で、重みと本人の読み上げ行別データは含めていない。本人の行別データはfaculty内で評価後に削除する。

## 学習の保存領域不足と再実行（2026-11-23）

初回D学習は優先度40でGPU1〜3へ投入した。確認時にfacultyの`/home`ファイルシステムは100%（空き4 KiB）で、GPUプロセスは3本とも残っていなかった。各出力にstep 250 checkpointがあり、最終重みはなかった。2Bの保存ログには`torch.save`中の`basic_ios::clear: iostream error`が残り、drop0のキュー終了コードは1。drop0.075はキューの`running/`にログと使用率記録が残ったまま完了記録が無く、終了状態を確定できなかった。GPU平均使用率はdrop0が89.4%、drop0.075が89.2%、2Bが79.5%。drop0では20 MiBのCUDA allocator mapping失敗警告が出たが、その後も学習stepは進んでいた。`/home`の容量不足が原因と判断したが、drop0.075の直接の終了理由はログから特定できなかった。

既存checkpointを削除せず、3本の部分出力（合計37 GiB、各step 250）を`/var/tmp/voiceime-work-fr3-d-20261123/interrupted/`へ移した。これにより`/home`に37 GiB、`/var/tmp`のルートファイルシステムに230 GiBの空きができた。部分checkpointは訓練の継続には使わず、同じseed・同じ条件でstep 0から一度だけ再実行する。以後の重みと評価出力は`/var/tmp/voiceime-work-fr3-d-20261123/`へ保存する。入力データ、コード、キュー制御先は元のfaculty作業場所に置く。

2026-11-23 12:05:48 JST、優先度41の再実行3本をキューへ登録し、GPU1にD-0.8B-drop0、GPU2にD-0.8B-drop0.075、GPU3にD-2B-drop0.075が割り当てられた。すべてseed 0、2 epoch、learning rate `2e-5`、実効batch 32、`--disable-cudnn-sdp`。起動直後のGPU使用率はそれぞれ95%、97%、98%。2Bのログでは`causal_conv1d`が無いためPyTorch参照実装へfallbackする警告が出た。使用率の反復試運転はしていない。

### 本人読み上げ評価の入力

前回のfaculty評価用入力は作業場所に残っていなかったため、`voiceIME-wt/r3-audio/runs/term-select/metal2/`の100件のplain/segment-merge runから、既存の評価manifestと同じ`dev-user-s000`〜`dev-user-s049`を選んだ。正解文は修正版の`data/dev-user/manifest.jsonl`から同じIDを抽出し、音声パスを除いた。facultyへ置いたmanifestは50件で、過去に記録した修正版manifestのSHA-256 `f3cfb4058713742c84a16fb6fb9878f2902d9959e55888b04d5f0da6b85f5309`と一致した。plain、segment-merge、manifestの順序付きIDはすべて一致した。Qwen仮説は無いので空欄で評価する。本人の推論行は各評価launcherの終了時に削除し、入力JSONLも3条件の評価後に削除する。

## 0.8B学習のOOMとcheckpoint再開

優先度41の0.8B 2条件は、2026-11-23 12:54:22 JSTにstep 2,318付近でCUDA OOMにより終了した。両ログは同じ時点に逆伝播中の27.23 GiB割り当て失敗を記録し、PyTorchが使っていたGPUメモリは66.43 GiB、空きは25.43 GiBだった。GPU1・2の学習プロセスが同時に失敗したが、GPU3の2B学習は継続している。保存先の空きは152 GiBあり、今回は保存領域ではなく長い入力のmicrobatchが原因と判断した。

両条件にstep 2,250のcheckpointがあり、モデル、optimizer、Trainer状態、乱数状態を確認した。学習順序と実効batchを維持して続けるため、`train.py`に`--resume-from-checkpoint`を追加し、両方を同じcheckpointから再開する。microbatch 32でのOOMを避けるためbatch 16、gradient accumulation 2へ変更し、実効batch 32を保つ。seed、2 epoch、学習率`2e-5`、データと前処理、drop設定、worker数、SDPA backendは変えない。microbatchの分割変更は追加の差として記録し、drop 0と0.075の比較では同一設定にする。

2026-11-23 12:58 JST、再開ジョブをキューへ登録した。GPU1にdrop 0、GPU2にdrop 0.075が割り当てられ、GPU3の2B条件はstep 1,450付近で継続中。再開後の完了状況と使用率は、最終評価とともに追記する。

再開ジョブは両方ともstep 5,996で終了し、終了コード0。`best_eval_loss`はdrop 0が0.104990（checkpoint 5,996）、drop 0.075が0.103849（checkpoint 5,996）。キュー記録の平均GPU使用率はそれぞれ92.4%、93.5%。12:58:05/06 JST開始、14:17:24/31 JST終了。どちらもcheckpoint-2,250からbatch 16・accumulation 2で残りの学習を行った。GPU3の2B条件は14:17時点でstep 3,900、継続中。

0.8Bの評価はdrop 0を優先度51でGPU1、drop 0.075をGPU2へ投入し、両方終了コード0で完了した。結果表と遅延は以下に記録する。

### D 0.8Bの評価結果（2026-11-23）

2条件はどちらもTransformers BF16 greedyで評価した。valとtest-novelはQwen 0.6B併用のsegment-merge文と同じselector一覧を使い、dev-user 50件はQwen仮説欄を空にした。dev-user行別出力はlauncher終了時のtrapで削除した。

| 条件 | val CER | val用語 | test-novel用語 | 一覧内正答 | 一覧外正答 | dev-user CER / 用語 | 見えない用語除外 CER / 用語 | batch 1中央値 / p90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D-0.8B-drop0 | 2.84% | 1344/1427 | 357/500 | 313/369 (84.8%) | 44/131 (33.6%) | 6.44% / 56/67 | 6.48% / 53/67 | — |
| D-0.8B-drop0.075 | 2.84% | 1346/1427 | 345/500 | 305/369 (82.7%) | 40/131 (30.5%) | 4.72% / 56/67 | 4.76% / 56/67 | 0.456 / 0.902秒 |

両条件のval CERは同じで、drop 0.075はval用語が2件多く、dev-user CERが1.72ポイント低かった。drop 0はtest-novelが12語多く、一覧内正答率も2.1ポイント高かった。設定間の比較はseed 0、同じデータと実効batch 32で行ったが、0.8Bはstep 2,250からmicrobatch 16・accumulation 2へ再開した。したがって、drop差の評価にはこの共通再開設定を含む。

既存重みの追加評価はASR担当の2026-11-22出力を使い、D学習・評価は2026-11-23の学習用出力を使った。test-novelの一覧内正解語はどちらも369/500だったが、valの一覧内正解語は既存重み評価が1312/1427、D評価が1310/1427。val指標の差には2語分の一覧差も含まれる。

両方の`train_summary.json`で`cudnn_sdp_enabled=false`、batch 16、gradient accumulation 2、seed 0、2 epoch、学習率`2e-5`、best checkpoint 5,996を確認した。2Bのbackendと設定も学習終了時のsummaryで照合する。

drop 0の評価は14:20:08–14:21:57 JST、drop 0.075は14:20:23–14:31:13 JST。queueの平均GPU使用率はそれぞれ6.2%と30.4%。短い評価とbatch 1遅延測定を含み、学習ジョブの使用率とは比較できない。反復試行はしていない。batch 1遅延はdrop 0.075のval 1,000件で測り、中央値0.456秒、p90 0.902秒、平均0.533秒。

### D-2Bの学習完了（2026-11-23）

D-2B-drop0.075はGPU3で15:29:51 JSTに終了コード0となった。開始12:05:48、実行3時間24分、queue記録の平均GPU使用率86.7%。best checkpointはstep 5,750、val loss 0.102163。`train_summary.json`で`cudnn_sdp_enabled=false`、microbatch 4、gradient accumulation 8、実効batch 32、seed 0、2 epoch、学習率`2e-5`、resumeなしを確認した。0.8Bのdrop 0/0.075と同じデータ・入力・実効batch・seed・optimizer設定・backendで、microbatchの分割だけが異なる。

drop 0.8Bの集計値はfacultyの`/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123/D-0.8B-drop0/`と`D-0.8B-drop0.075/`の`reports/`、`audit.json`、drop 0.075の`latency-val-batch1.json`に記録した。本人50件の行別入力・出力JSONLは、すべての評価後にfaculty上から削除した。

### D-2Bの評価結果（2026-11-23）

D-2B-drop0.075は15:30:56 JSTにGPU1へ投入し、15:42:07に終了コード0となった。評価はTransformers BF16 greedyで、val、test-novel、Qwen欄を空にした本人50件、batch 1のval 1,000件を処理した。出力には`apply_output_style`を適用し、CERと用語指標は`src/voiceime/eval/`の定義（`CER_EQUIVALENT_FORMS`を含む）で集計した。queueの平均GPU使用率は31.8%。

| 条件 | val CER | val用語 | test-novel用語 | 一覧内正答 | 一覧外正答 | dev-user CER / 用語 | 見えない用語除外 CER / 用語 | batch 1中央値 / p90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D-0.8B-drop0 | 2.84% | 1344/1427 | 357/500 | 313/369 (84.8%) | 44/131 (33.6%) | 6.44% / 56/67 | 6.48% / 53/67 | — |
| D-0.8B-drop0.075 | 2.84% | 1346/1427 | 345/500 | 305/369 (82.7%) | 40/131 (30.5%) | 4.72% / 56/67 | 4.76% / 56/67 | 0.456 / 0.902秒 |
| D-2B-drop0.075 | 2.92% | 1361/1427 | 330/500 | 291/369 (78.9%) | 39/131 (29.8%) | 6.01% / 53/67 | 5.88% / 53/67 | 0.473 / 0.927秒 |

2Bのbatch 1遅延は中央値0.473秒、p90 0.927秒、平均0.551秒。今回の2B値は0.8B D入力測定より中央値0.017秒、p90 0.025秒長い。GPU上で測った値であり、Mac上の遅延は未測定。

3条件ともval CERと用語正答はBを上回った。test-novelはD-0.8B-drop0が357/500で最良だが、80%目標の400件には43件不足する。一覧内の正解語369件のうち56件を取りこぼしており、選択一覧の拡大と一覧内語を出力へ反映する学習を分けて改善する余地がある。D-2Bはval用語1361/1427で最良だが、test-novelは330/500にとどまり、モデルを2Bへ広げただけでは初見語が改善しなかった。本人50件ではD-0.8B-drop0.075がCER 4.72%で最良だった。次の初見語改善ではdrop 0の0.8Bを主比較条件とし、D-0.8B-drop0.075は本人録音の参考条件、D-2Bはval基準として残す。

既存B重みのQwen segment-merge評価はtest-novel252/500、一覧内235/369だった。D-0.8B-drop0は357/500、313/369へ増えたが、既存重みのQwen評価は11月22日版、D学習・評価は11月23日版の入力と一覧を使っているため、差のすべてを学習条件だけの効果とは解釈しない。

2Bの集計値はfacultyの`/var/tmp/voiceime-work-fr3-d-20261123/runs/formatter-sft3/d-eval-20261123/D-2B-drop0.075/`に保存した。本人の行別評価出力はlauncherの終了処理で削除済みで、入力JSONL 3件も`~/voiceime-work-fr3/inputs/d-eval-devuser-20261123/`ごと削除した。val/test-novelの行別JSONLと重みはfacultyに残し、ローカルへ転送していない。

## 最終所見と成果物

比較表は[`runs/formatter-sft3/d-final-20261123/table.md`](../../runs/formatter-sft3/d-final-20261123/table.md)。D系の集計レポート、summary、selector監査、batch 1遅延JSONは同ディレクトリの`aggregate-source/`に置いた。今回の集計転送は76,394 bytesで、前の集計19,945,801 bytesと合わせて20,022,195 bytes。25MB以内。モデル重みと本人の行別データは含まない。

GPU1〜3の評価・学習プロセスはすべて終了し、`nvidia-smi`と`~/voiceime-ps.sh`で自分のプロセスが無いことを確認した。GPU0には他者のプロセスが残っていたため触れていない。`docs/STATUS.md`は編集していない。

## 用語一覧の上限とWhisper仮説（2026-11-23）

### 比較条件

仮説は、用語一覧の上限を広げることとWhisper large-v3-turboの仮説を選択文字列へ加えることで、正解語が一覧へ入る割合が上がり、Dモデルの出力にも反映されることである。D-0.8B-drop0とD-0.8B-drop0.075について、一覧上限20・32・48語と、選択文字列へWhisperを含める／含めないを比較する。学習は行わない。

評価時の整形入力は従来のD評価と同じHaas 1回目、segment-merge文、Qwen仮説に固定し、変えるのは整形器へ渡す用語一覧だけとする。valは`manifest-val-no-audio.jsonl`の1,000件、test-novelは500件。Transformers BF16 greedy、出力整形、CER・用語指標も前節までと同じにする。評価CLIの一覧上限は48にし、20語・32語一覧も同じ実行で処理する。

一覧はmain commit `c2ad2769819bcdb3fe1cf90fb760279692206889` の`src/voiceime/formatter/glossary.py`（SHA-256 `e9db1b5d7ba52703300b4cb29099f2cb8da791361f6f895e931eac5f75eeedfa`）で作る。候補poolは用語集v1・v2の31,415語。test-novelだけは除外83語ファイルの83用語を除外し、valでは除外しない（ファイルは84行で、1行はコメント）。選択文字列はHaas 1回目と`multiasr-{val,test-novel}-qwen06-firstpass.jsonl`を改行で連結し、Whisper条件では指定の`multiasr-{val,test-novel}-whisper-firstpass.jsonl`を末尾へ加える。整形用Qwen欄は既存D評価のrunをそのまま使う。

最初の一覧生成ではvalの選択にD学習用Qwen runを誤って使い、従来の用語一覧との完全一致は66/1,000件だったため、モデル評価へ使わず別出力先に残した。既存の一覧生成に使われたQwen runへ直しても、mainの現行選択器で作る20語一覧との完全一致はval 67/1,000件だった。test-novelは500/500件一致した。valで一致しない理由は特定できていないため、既存D結果を旧一覧の基準として併記する。

### 用語一覧への正解語の包含

次表は出力正答ではなく、manifestの正解用語が選択一覧に含まれた件数である。

| 上限 | 選択文字列 | val包含 | test-novel包含 |
| ---: | --- | ---: | ---: |
| 20 | Haas＋Qwen | 1305/1427 | 369/500 |
| 20 | Haas＋Qwen＋Whisper | 1333/1427 | 393/500 |
| 32 | Haas＋Qwen | 1308/1427 | 414/500 |
| 32 | Haas＋Qwen＋Whisper | 1334/1427 | 435/500 |
| 48 | Haas＋Qwen | 1308/1427 | 429/500 |
| 48 | Haas＋Qwen＋Whisper | 1334/1427 | 450/500 |

Whisper追加はtest-novelの包含を各上限で21〜24語増やした。上限を32から48へ広げるとtest-novelの包含は15語増え、valは変わらなかった。これらが整形モデルの正答へ反映されるかは評価中である。

一覧と選択監査はfacultyの`~/voiceime-work-fr3/inputs/glossary-capacity-20261123-corrected/`に置いた。生成スクリプトは[`runs/formatter-sft3/build_glossary_capacity_variants.py`](../../runs/formatter-sft3/build_glossary_capacity_variants.py)。初回の評価launcherは評価CLIの既定上限20で32語・48語一覧を拒否され、推論前に終了した。平均GPU使用率は0%。再実行では上限を48に設定し、別の`retry1`出力先を使った。成功した実行結果は次節に記録した。

### 評価結果

評価後の全行入力と用語一覧は監査スクリプトで照合し、val各1,000行、test-novel各500行について一致した。CERはmainと同一の`src/voiceime/eval/metrics.py`、出力整形はmainと同一の`style.py`を使ったTransformers BF16 greedy評価である。結果は[`runs/formatter-sft3/glossary-capacity-20261123/table.md`](../../runs/formatter-sft3/glossary-capacity-20261123/table.md)、集計JSON・監査・評価レポートは同ディレクトリに保存した。推論行JSONLはfaculty上に残し、行単位の出力は手元へ転送していない。

| 条件 | 上限語数 | Whisper追加 | val CER | val用語 | test-novel用語 | 正解語の一覧包含 | 一覧内正答 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| D-0.8B-drop0 | 20 | なし | 2.82% | 1344/1427 | 357/500 | 369/500 | 313/369 (84.8%) |
| D-0.8B-drop0 | 20 | あり | 2.78% | 1349/1427 | 372/500 | 393/500 | 335/393 (85.2%) |
| D-0.8B-drop0 | 32 | なし | 2.84% | 1344/1427 | 378/500 | 414/500 | 352/414 (85.0%) |
| D-0.8B-drop0 | 32 | あり | 2.75% | 1348/1427 | 389/500 | 435/500 | 370/435 (85.1%) |
| D-0.8B-drop0 | 48 | なし | 2.85% | 1341/1427 | 386/500 | 429/500 | 363/429 (84.6%) |
| D-0.8B-drop0 | 48 | あり | 2.84% | 1346/1427 | 395/500 | 450/500 | 380/450 (84.4%) |
| D-0.8B-drop0.075 | 20 | なし | 2.89% | 1347/1427 | 345/500 | 369/500 | 305/369 (82.7%) |
| D-0.8B-drop0.075 | 20 | あり | 2.81% | 1353/1427 | 362/500 | 393/500 | 327/393 (83.2%) |
| D-0.8B-drop0.075 | 32 | なし | 2.95% | 1341/1427 | 367/500 | 414/500 | 344/414 (83.1%) |
| D-0.8B-drop0.075 | 32 | あり | 2.84% | 1349/1427 | 380/500 | 435/500 | 361/435 (83.0%) |
| D-0.8B-drop0.075 | 48 | なし | 2.88% | 1341/1427 | 373/500 | 429/500 | 355/429 (82.8%) |
| D-0.8B-drop0.075 | 48 | あり | 2.89% | 1343/1427 | 384/500 | 450/500 | 371/450 (82.4%) |

Whisper追加は、全6種類の上限・Whisper条件の組み合わせでtest-novelの正答を9〜17語増やした。上限20から32への拡大もWhisper有無にかかわらず正答を増やしたが、32から48への追加増分は4〜8語だった。最良はD-0.8B-drop0の48語＋Whisperで395/500（79.0%）。一覧には450/500語が入ったが、目標80%の400語には5語届かない。drop0.075の同条件は384/500（76.8%）。一覧内の正答率は同条件でそれぞれ380/450（84.4%）、371/450（82.4%）で、広い一覧でも下がり幅は小さい。

valでは、drop0は32語＋WhisperがCER 2.75%で最良、drop0.075は20語＋WhisperがCER 2.81%・用語1353/1427で最良だった。32語・48語を全条件で増やせばvalも一律に改善するわけではなく、drop0.075の32語・WhisperなしはCER 2.95%・用語1341/1427だった。

既存D評価の上限20語・Whisperなしと比べると、test-novelは両モデルとも元の一覧と500/500行で一致し、drop0は357/500・一覧内313/369、drop0.075は345/500・305/369を再現した。valの新しい上限20語一覧は旧D一覧と67/1,000行しか一致しないため、valの旧値（drop0 2.84%・1344/1427、drop0.075 2.84%・1346/1427）との差は一覧選択の変更を含み、同じ一覧での再評価ではない。

2ジョブはGPU1・2でそれぞれ406秒・402秒、終了コード0。平均GPU使用率はdrop0が36.7%、drop0.075が50.1%。`nvidia-smi`と`~/voiceime-ps.sh`で自分のGPUプロセスが無いことを確認した。GPU0の他者プロセスには触れていない。次はdrop0の48語＋Whisperを候補として、80%に届かない残り5語を学習入力へ反映する方法を検討する。
