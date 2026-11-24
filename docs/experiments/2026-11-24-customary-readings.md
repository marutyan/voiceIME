# IT用語の慣習読みと合成音声での評価

慣習読みを追加すると、読みを差し替えた合成音声の整形正答はval-customで28→36/56、novel-customで1→2/16となった。val-customの「アイクリア」は2件とも `ICLR` で出力された。「維持会」「二次会」と認識された `IJCAI` は2件とも候補に入らなかった。通常文の正答はval、test-novelで各1語減り、CERの変動は最大0.03ポイントだった。

## 条件

| 段階 | 入力と判定 |
| --- | --- |
| 教師から提案 | 第1版＋第2版の英字を含む31,415表記。既存のGemma 4 31B-it revision `842da3794eaa0b77d5f08bae87a17459d91ff475`、FP8、temperature 0。実際に使う頭字語読み・略称を最大3件 |
| 教師で再検証 | 例示なしの別プロンプトを使い、同じモデルが「はい」と答えた候補を採る。第1版・第2版・前回の追加読みとの正規化後の重複を除く。同音の語は `homophones` に記録する |
| 種の分割 | PMの99語を `random.Random(0)` で並べ替え、先頭49語を例示し、残り50語で用語単位と読み単位の再現率を測る。既存と重複しない読みの再現率も別に出す。利用者指定のIJCAI・ICLRの読みは再現率の採点後に直接登録する |
| val-custom | 通常valから、用語の印が一箇所で正解文に表記がある文を最大500文。元の話者とTTSを保ち、対象語の読みだけを1件差し替える |
| novel-custom | 通常test-novelから同じ条件の全文、最大300文。方式を先に固定し、評価に使う |
| ASR | Haas CUDA encoder・CPU decodeとQwen3-ASR 0.6Bの日本語greedy。HaasとQwenの初回仮説から候補を選び、Haasのヒント付き2回目と既存の区間採否を行う。ヒントに渡す読みは元の先頭読み |
| 文字形の集計 | TTS入力の左右の文脈から対象箇所を特定し、正しい表記・慣習読みの仮名・漢字や別の語・脱落に分類する。区間を一意に追えない行は判定不能で別に数える |
| 選択・整形 | Haas初回＋Qwen初回で上限48。追加前と、選択の照合と選択済み語の整形プロンプトに慣習読みを足した条件を比較する。FULL-scratch best、容量評価と同じTransformers推論器、batch 32 |
| 通常文での副作用 | `capacity-eval.sh` の通常val・test-novelの初回・結合ASR入力を固定する。上限48の基準一覧の再現を全行で確認し、慣習読みを加えた一覧で上限48の整形を採点する。通常文のASR再認識と区間採否は基準側の保存結果を再利用する |
| train-custom | 既存の合成train音声manifest 56,970行から最大8文／語、計20,000文。評価の元ID、評価の正解文と変更語の組、held-out語を除く。元の正解文はそのまま、条件Dの初回・採否後・Qwen初回と上限20の用語一覧を保存する |

追加読みの照合は前回の `GlossaryIndex` と同じカタカナ区間の完全一致を使う。ひらがなだけの区間や漢字の転写形は文字形の集計で扱う。通常文の変動を判断する目安は、過去の学習し直しで見た用語6件、CER 0.3ポイント。

## 再現手順

手元のPCで `runs/custom-readings/` のスクリプト、`datagen/text_v3/client.py`、PMの `seed.tsv` をfacultyの `~/voiceime-work-custom/` へ置く。起点の `ead1bdb` から `src/voiceime` と `datagen/text` を同ディレクトリの `code/` 以下へ配置する。facultyの既存 `r3-multiasr-train-20261123/scripts/train_pipeline.py` を作業ディレクトリにコピーし、Haas worker名を `voiceime-custom-haas-worker` にする。

facultyで `nvidia-smi` を確認し、`70-custom-teacher.sh` を優先度70でキューに登録する。`queue-custom-sequence.sh` を作業ディレクトリで実行すると、教師ジョブのGPU解放後に `70-custom-pipeline.sh` を登録する。各GPUジョブはキューからGPU1〜3のうち1枚を受け取り、直前にも空きを確認する。パイプラインは段階2、段階3の順で処理し、各段階を `PROGRESS.md` に1行記録する。

worktreeは `exp/alt-readings` の起点を保ち、新規ファイルを追加した。容量評価の手順は `main` の `runs/weightops/fix1/capacity-eval.sh` を参照した。

## 段階1の結果

31,415語から603語・610読みを採った。296読みは別の用語の読みと同音で、対応する表記を `homophones` に記録した。再検証の内訳は「はい」2,487件、「いいえ」242件、「不明」380件。利用者指定の `IJCAI` の「イジカイ」と `ICLR` の「アイクリア」を種の採点後に登録した。`GNU` の「グヌー」と `K8s` の「クーバネティス」も収録した。

| 種の再現率（例示した49語を除く） | 再現数 |
| --- | ---: |
| 用語単位で候補を一つ以上再現 | 22/50（44.0%） |
| 読み単位 | 23/61（37.7%） |
| 既存の用語集と前回の追加読みの両方に無かった読み | 3/25（12.0%） |

種はPMの一覧をそのまま使った。再検証は同じモデルの別プロンプトによる判定で、実際の利用頻度は不明。目視用に種0で無作為抽出した50語を保存した。[教師集計](../../runs/custom-readings/teacher-summary.json) · [種の分割](../../runs/custom-readings/seed-split.json) · [種の読み別結果](../../runs/custom-readings/seed-held-results.jsonl) · [目視用50語](../../runs/custom-readings/spot-check-50.jsonl)

`data/text/glossary-custom-readings.jsonl` は既存の `data/` の設定によりGit管理外。SHA-256は `3c1faa0f1ff2c2d2c4b6a50b1471bb54f22d95c8d3c567372beed5a60e899483`。教師はGPU3で274秒実行した。

## 合成セットの件数と再開

元のval 1,000文のうち、学習済み語の読みだけを差し替えられる文は56文・38語だった。test-novel 500文では16文・16語だった。該当した全文を各1回採った。val-customは目標500文に対して444文不足した。[合成入力の集計](../../runs/custom-readings/eval-plan.json)

段階2の初回は、Qwen TTSがモデル名を受けてトークナイザーの初期化中にHubへ問い合わせ、オフライン設定で停止した。同じ保存済みrevision `fd4b254389122332181a7c3db7f27e918eec64e3` のローカルパスを指定し、Irodoriで生成済みの発話を保って再開した。

## 段階2の結果

予定した72文すべてを合成し、両方のASRで認識した。元の話者・TTS・正解文を全件で照合した。慣習読みを入れた文について、対象語の選択と整形を上限48で比べた。

| データ | 用語一覧への包含（追加前 → 追加後） | 整形で正しい表記（追加前 → 追加後） |
| --- | ---: | ---: |
| val-custom | 22/56 → 36/56（39.3% → 64.3%） | 28/56 → 36/56（50.0% → 64.3%） |
| novel-custom | 3/16 → 7/16（18.8% → 43.8%） | 1/16 → 2/16（6.3% → 12.5%） |

| データ | ASR | 正しい表記 | 慣習読みの仮名 | 漢字や別の語 | 脱落 | 判定不能 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| val-custom | Haas初回 | 3 | 26 | 23 | 0 | 4 |
| val-custom | Qwen 0.6B | 3 | 26 | 16 | 0 | 11 |
| novel-custom | Haas初回 | 0 | 4 | 7 | 0 | 5 |
| novel-custom | Qwen 0.6B | 0 | 5 | 8 | 0 | 3 |

val-customの `ICLR` はHaas、Qwenとも「アイクリア」と書き、一覧への包含と整形の正答はいずれも0→2/2だった。`IJCAI` はHaasが「二次会」「維持会」と1件ずつ書き、Qwenでは周辺文脈から対象区間を確定できなかった。一覧・整形とも0/2だった。左右の文脈が揃わない行は判定不能に含めているため、表の脱落0件は対象区間を特定できた範囲の数値。語ごとの形と回数は [val-custom](../../runs/custom-readings/val-custom-asr-forms.jsonl) と [novel-custom](../../runs/custom-readings/novel-custom-asr-forms.jsonl) に記載した。

専用文の両条件で、Haasのヒント付き2回目と区間採否を行った。ヒント一覧はval-customで21/56文、novel-customで4/16文変わった。2回目の仮説が変わったのはval-customの3文、採否後の文まで変わったのは2文だった。novel-customの2回目と採否後の文は全件同じだった。[音声とヒントの照合](../../runs/custom-readings/stage2-audit.json)

| 通常文・上限48 | 用語正答（追加前 → 追加後） | CER（追加前 → 追加後） |
| --- | ---: | ---: |
| val | 1,349/1,427 → 1,348/1,427 | 2.74% → 2.74% |
| test-novel | 412/500 → 411/500 | 3.40% → 3.37% |

通常文では容量評価の上限48の基準一覧を全行で再現し、既存のASR入力を保って慣習読みを加えた。差は過去に見た学習し直しのばらつき（用語6件・CER 0.3ポイント）より小さい。専用文では、選択と整形の両方に読みを提示する条件をまとめて比較した。novel-customは16文のため、初見語全体への効果は不明。[全採点結果](../../runs/custom-readings/evaluation-summary.json)

## 段階3の結果

trainから選んだ1,757文をすべて合成し、HaasとQwen 0.6Bで認識した。test-novelの表記が元文に出た1文と、Haasの認識結果に出た別の1文を除き、347語の1,755文（6.46時間、1語につき最大7文）を条件Dの学習材料にした。学習実行はPMの判断待ち。今回の実行では元の1,757文の計画を再開に使い、最後に表記検査を行った。現行の準備スクリプトは元文で見つかる表記を音声生成前にも除く。[計画](../../runs/custom-readings/train-plan.json) · [完了件数](../../runs/custom-readings/train-summary.json) · [除外記録](../../runs/custom-readings/excluded-novel-surface.jsonl)

| facultyでの置き場所 | 内容 |
| --- | --- |
| `~/voiceime-work-custom/tts/train-custom/` | 合成音声とmanifest |
| `~/voiceime-work-custom/asr/train-custom/` | Haasの初回と再認識、区間採否後、Qwen初回、用語一覧 |
| `~/voiceime-work-custom/train-material/train.jsonl` | 元の正解文と条件Dの3入力・一覧を持つ学習行 |
| `~/voiceime-work-custom/train-material/` | IDで対応する `first-pass.jsonl`、`segment-merge.jsonl`、`qwen06-hypothesis.jsonl`、`formatter-glossary.jsonl` |

全1,755行について、元の正解文・話者・TTS、音声の16 kHzモノラル、ASRと一覧のID、評価文と語の72組、test-novelの500語との分離を検査した。facultyで実行する確認コマンドは次のとおり。[検査結果とハッシュ](../../runs/custom-readings/train-audit.json)

```bash
cd ~/voiceime-work-custom
PYTHONPATH="$PWD/code/src:$PWD/code/datagen/text" python3 audit_material.py
```

回復後の段階2・3のGPU1ジョブは2,635秒で完走した。教師に使ったGPU3、段階2・3に使ったGPU1の解放と、終了時に実験のプロセスが0件であることを確認した。facultyの `PROGRESS.md` に3段階の結果を各1行記録した。手元への転送は、辞書と集計を合わせて99,177バイト。既存の依存で `uv run pytest -q` は123件成功した。
