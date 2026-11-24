# 実ASR入力を追加した学習（FULL）

## 目的

合成音声を実際に認識した入力で学習すると、言い直しを含むvalでの削除が減り、一覧外の学習済み語と初見語の正答数が上がるかを調べる。FULL-contとFULL-cont-dropの比較では、一覧から学習済みの正解語を抜くことで、一覧外の正答数が増えるかを確かめる。

[FIX2](2026-11-23-omitted-terms-fix2.md)で採用した無条件の表記書き換えをやめ、[fix1](2026-11-23-omitted-terms-fix.md)と同じく、一覧またはsegment-merge後の文に表記があるときに正解文へ表記を書く。評価は合成音声で行う。削除数は削りすぎの目安に使う。

## データ

facultyの `~/voiceime-work-asr/r3-multiasr-train-20261123/outputs/` にある `train-available-12000.jsonl` と `train-topup44970.jsonl` を、条件Dの元の学習データにIDで結合した。READMEは `~/voiceime-work-fr3/repo/README.md` の「第3弾の追加学習音声 ASR最終結果（44,970件）」。56,970件のIDに重複がなく、全件で元の正解文と一致した。Haas初回、HaasとQwenの候補をもとに作った用語一覧、segment-merge後の文、Qwen 0.6Bの初回認識を使う。12,000件の既存入力は4欄とも一致した。別系列の既存9,522行にも従来の実ASRを使った。

| 元データの入力 | fix1まで | FULL |
| --- | ---: | ---: |
| 第3弾の既存12,000件の実ASR | 11,999 | 11,999 |
| 第3弾の追加44,970件の実ASR | 0 | 44,968 |
| 別系列の実ASR | 9,522 | 9,522 |
| 音声なし。従来の合成ASR | 74,410 | 29,442 |
| 合計 | 95,931 | 95,931 |

合成ASRを使う行には、音声長の条件でASR成果物から欠けた `train-v3-025116` を含む。条件Dと同様に `--allow-partial-asr` を使った。新しい実ASR一覧の上限は20で、学習用用語集への所属とheld-out除外表を照合した。test-novelは評価工程で使った。

omitted語を持つ元8,372行をfix1の変換関数で再処理した。既存12,000件は1,095行を書き換え、278行を読みのまま残し、読みが2回の1行を外した。追加44,970件は5,803行を書き換え、1,193行を読みのまま残し、読みが2回の2行を外した。拡張データはfix1の `augmentation-fixed.jsonl` 36,778行を同じSHA-256のまま使用した。 [データ監査](../../runs/weightops/full1/data-audit.json)

### 取り出し監査

元と拡張の全132,709行を学習コードから1回ずつ取り出し、トークン化直前の一覧、segment-merge後の文、正解文を比較した。2,000行ごとにseedを固定した。元8,369行、拡張1,822行のomitted語で、一覧に表記があるのに正解が読みのままの行は0行だった。結合文に表記があるのに正解が読みのまま、一覧と結合文の両方に表記が無いのに正解が表記、の件数も各0行。語境界付きの照合から漏れた3行は、正解文に表記文字列があり、読みは残っていなかった。

FULL-cont-dropで対象語が一覧にあったのは5,322行・5,389語。実際に一覧から抜いたのは828行・832語で、全学習行の0.62%、元データの0.86%、対象のある行の15.56%。抜いた832語のうち294語はsegment-merge後の文にも表記が無かった。割合は固定seedでの取り出し監査値。拡張データやomitted語の一覧にdropの影響がないことを確認した。48行で、drop直前までの出力が同一seedのfix1学習コードと一致した。 [全行監査](../../runs/weightops/full1/verify-dynamic.json)

## 学習

| 条件 | 初期重み | epoch | 学習率 | 学習済み語を一覧から抜く率 |
| --- | --- | ---: | ---: | ---: |
| FULL-cont | `outputs/fixsoup-a050` | 1 | 1e-5 | 0 |
| FULL-scratch | 元のQwen3.5-0.8B | 2 | 2e-5 | 0 |
| FULL-cont-drop | `outputs/fixsoup-a050` | 1 | 1e-5 | 0.15 |

全層、batch 16 × accumulation 2、seed 0、最大1,024トークン、用語一覧上限20、混ぜ物最大8語、cuDNN SDPA無効、gradient checkpointingを指定した。val-select 970行で250 stepごとに損失を測り、最良の `best` と最終の `final` を `~/voiceime-work-wops/full1/outputs/<条件>/` に保存する。FULL-contとFULL-scratchはfix1の学習スクリプトを使った。

FULL-cont-dropの対象は元の学習正解文に表記があり、`terms` にもある語。fix1の拡張データの正解語すべてと、元データのomitted語すべてを表記の幅・大小・空白をそろえて除外した。11,842種類の学習済み語から対象は1,424種類。元データの各行で正解文にも一覧にもある対象語を、混ぜ物の追加後に個別に0.15で抜く。正解文は表記を保ち、drop専用の乱数を使う。 [学習の引数](../../runs/weightops/full1/train-and-eval.sh) · [学習コードの差分](../../runs/weightops/full1/train_full_drop.patch)

| 条件 | 開始–終了（JST、評価・採点込み） | best step | 最良のval loss | 最後のstep |
| --- | --- | ---: | ---: | ---: |
| FULL-cont | 00:10–01:32（GPU1） | 4,148 | 0.1100 | 4,148 |
| FULL-scratch | 00:10–02:46（GPU2） | 7,750 | 0.1054 | 8,296 |
| FULL-cont-drop | 00:11–01:32（GPU3） | 4,000 | 0.1089 | 4,148 |

優先度60の3ジョブを準備順に登録した。3本とも終了コード0で、重みが各条件のbestとfinalだけであること、評価直後に各GPUの計算プロセスが空になったこと、終了後のプロセス一覧に対象3条件がいないことを確認した。 [学習ログ集計](../../runs/weightops/full1/training.json)

## 評価

fix1の `capacity-eval.sh` で学習済みの `best` を評価した。比較に用いたのはHaas初回とQwen 0.6Bで選んだ上限20、32、48の一覧。valは1,000行・1,427語、test-novelは500行・500語。言い直しの削除数は、valの `self_correction` 203行を対象に、CERの削除操作の数を足した。容量評価のreportに出たタグ別集計と照合した。

FIX2のスクリプトを再利用して採点した。一覧外の学習済み語は、RSIの元データと拡張の正解文に表記があり、`terms` にもある語で固定した。各行の一覧に含まれない正解語の出現数を分母にし、上限20は122語、上限32・48は119語。未発話語の挿入は、行の一覧またはmanifestの用語集にある語で、正解語や発話原文・読みの文に表記も読みも無いものの出現数。RSIとFIX-0.8B-contの既存値は全項目で再現した。 [採点コード](../../runs/weightops/full1/score_full.py)

## 結果

モデル出力をそのまま採点した結果。各条件が終わるたびにfacultyの `~/voiceime-work-wops/runs/full1/PROGRESS.md` へ1行追記した。全指標と読み復元ありの値も保存した。 [進捗3行](../../runs/weightops/full1/PROGRESS.md) · [採点集計](../../runs/weightops/full1/score.json)

### val

| 上限 | 条件 | val用語 | val CER | 一覧外の学習済み語 | 一覧内取りこぼし | 未発話語挿入 | 言い直しの削除 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | RSI-0.8B | 1359/1427 | 2.64% | 76/122 | 22 | 31 | 173 |
| 20 | FIX-0.8B-cont | 1357/1427 | 2.82% | 74/122 | 22 | 33 | 148 |
| 20 | fixsoup-a050 | 1360/1427 | 2.64% | 75/122 | 20 | 33 | 158 |
| 20 | FULL-cont | 1350/1427 | 2.72% | 73/122 | 28 | 37 | 242 |
| 20 | FULL-scratch | 1353/1427 | 2.61% | 75/122 | 27 | 30 | 175 |
| 20 | FULL-cont-drop | 1355/1427 | 2.65% | 78/122 | 28 | 33 | 212 |
| 32 | RSI-0.8B | 1358/1427 | 2.68% | 72/119 | 22 | 38 | 175 |
| 32 | FIX-0.8B-cont | 1357/1427 | 2.76% | 72/119 | 23 | 32 | 148 |
| 32 | fixsoup-a050 | 1355/1427 | 2.78% | 70/119 | 23 | 41 | 160 |
| 32 | FULL-cont | 1350/1427 | 2.75% | 72/119 | 30 | 38 | 244 |
| 32 | FULL-scratch | 1351/1427 | 2.67% | 73/119 | 30 | 33 | 162 |
| 32 | FULL-cont-drop | 1354/1427 | 2.66% | 76/119 | 30 | 39 | 208 |
| 48 | RSI-0.8B | 1361/1427 | 2.65% | 74/119 | 21 | 37 | 144 |
| 48 | FIX-0.8B-cont | 1356/1427 | 2.90% | 75/119 | 27 | 33 | 166 |
| 48 | fixsoup-a050 | 1356/1427 | 2.75% | 72/119 | 24 | 39 | 162 |
| 48 | FULL-cont | 1351/1427 | 2.75% | 73/119 | 30 | 38 | 235 |
| 48 | FULL-scratch | 1349/1427 | 2.74% | 72/119 | 31 | 35 | 163 |
| 48 | FULL-cont-drop | 1354/1427 | 2.67% | 77/119 | 31 | 36 | 208 |

### test-novel

| 上限 | 条件 | test-novel用語 | test-novel CER | 一覧内取りこぼし | 結合文にある取りこぼし | 未発話語挿入 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 20 | RSI-0.8B | 359/500 | 5.23% | 54 | 24 | 42 |
| 20 | FIX-0.8B-cont | 381/500 | 4.24% | 28 | 6 | 44 |
| 20 | fixsoup-a050 | 384/500 | 4.21% | 28 | 9 | 40 |
| 20 | FULL-cont | 381/500 | 4.53% | 26 | 10 | 42 |
| 20 | FULL-scratch | 378/500 | 4.06% | 26 | 7 | 40 |
| 20 | FULL-cont-drop | 380/500 | 4.27% | 28 | 9 | 44 |
| 32 | RSI-0.8B | 379/500 | 4.88% | 64 | 22 | 36 |
| 32 | FIX-0.8B-cont | 407/500 | 3.90% | 35 | 6 | 39 |
| 32 | fixsoup-a050 | 412/500 | 3.69% | 31 | 8 | 36 |
| 32 | FULL-cont | 403/500 | 3.90% | 35 | 10 | 37 |
| 32 | FULL-scratch | 403/500 | 3.63% | 32 | 6 | 41 |
| 32 | FULL-cont-drop | 409/500 | 4.04% | 30 | 6 | 40 |
| 48 | RSI-0.8B | 385/500 | 4.75% | 66 | 22 | 34 |
| 48 | FIX-0.8B-cont | 412/500 | 3.92% | 38 | 6 | 38 |
| 48 | fixsoup-a050 | 415/500 | 3.79% | 35 | 9 | 35 |
| 48 | FULL-cont | 409/500 | 3.85% | 39 | 11 | 36 |
| 48 | FULL-scratch | 412/500 | 3.40% | 34 | 6 | 41 |
| 48 | FULL-cont-drop | 414/500 | 3.73% | 35 | 7 | 41 |

## 分かったこと

- 同じ補間重みから始めたFULL-contとFULL-cont-dropを比べると、dropにより一覧外の正答が上限20で5語、上限32と48で4語増えた。言い直しの削除は順に30、36、27件減り、test-novelは1件減、6件増、5件増だった。上限32では、一覧外76/119は6条件中最多。val CERは補間元の2.78%から2.66%に下がった。一方、test-novelは補間元の412から409、言い直しの削除は160から208だった。
- FULL-contは補間元に比べて、上限32で一覧外正答が70/119から72/119に増えた一方、test-novelは412から403に減り、言い直しの削除は160から244に増えた。FULL-scratchの削除は同上限で162件と補間元に近く、test-novelは403だった。
- 初期値と学習条件が同じ旧FIX-0.8B-scratchと比べると、FULL-scratchは上限32でval用語1,351のまま、CERは3.01%から2.67%、test-novelは397から403に変わった。実ASR入力の追加と、それに合わせた正解文の変更を含む比較である。 [旧FIX-scratchの採点](../../runs/weightops/fix1/score.json)
- 合成音声の1 seedで得た結果で、seed間のばらつきと本人の録音での効果は未測定。

## 再実行

初回はfacultyの `~/voiceime-work-wops/full1/` にスクリプトを配置し、学習データとdrop版の学習スクリプトを作る。

```bash
cd ~/voiceime-work-wops/full1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../fix1 python3 prepare_full.py
patch --output=train_full_drop.py ../fix1/train_fix.py < train_full_drop.patch
bash train-and-eval.sh audit
```

facultyのキューに `60-wops-full-cont.sh`、`60-wops-full-scratch.sh`、`60-wops-full-cont-drop.sh` を登録する。各ジョブは学習・容量評価・採点を順に実行する。全条件を再採点するときもfacultyで実行する。

```bash
source ~/voiceime-work-wops/rsi1/faculty-env.sh
export CUDA_VISIBLE_DEVICES=""
export PYTHONPATH="$WORK/fix1:$PYTHONPATH:$WORK/fix2"
"$PY" "$WORK/full1/score_full.py"
```

| faculty上のコード | SHA-256 |
| --- | --- |
| `fix1/train_fix.py` | `b9a896d85574029b47061d0e31e039f160bed780b865830f4bde410811d3caef` |
| `fix1/train_support.py` | `5f49e60097e3123b1f0537a1f8d5e5ec446aadc2ea71e1b5b4f85d90d7eaaf4a` |
| `fix1/capacity-eval.sh` | `14f4e968d122ea25b19d0fa6ff185a9e8d228d873e91f056bf6a105ac7fdf744` |
| `full1/train_full_drop.py` | `d6c733829c722ca683df051cb021ef426d2227df566e5e627916b3bece9ac51c` |
