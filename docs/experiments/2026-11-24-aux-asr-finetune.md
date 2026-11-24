# 補助ASRの全層追加学習（2026-11-24）

**上限48語でASRFT-bが学習済み用語の95%目標に到達した。** valは1,367/1,427語（95.80%、従来比+18語）。元モデルを同じ手順で再実行した場合と比べても+16語だった。上限48でのval CERとtest-novelはばらつきの範囲。実音声500件のASR CERは14.05%から11.53%に下がった。

初見語の正答数も重視すると、aの上限32語はval 1,359/1,427語（95.23%）、test-novel 427/500語（85.4%）で両目標に達した。合成音声だけで学習したcは実音声のCERが10.49ポイント悪化した。

## 結果

全体評価の差は用語6語とCER 0.30ポイントをそれぞれ超えたときに改善または悪化と判定する。valで95%に達するには1,356語が必要。

### 全体評価

| 上限 | 条件 | val用語 /1,427 | val CER | test-novel用語 /500 | test-novel CER |
| ---: | --- | ---: | ---: | ---: | ---: |
| 20 | 保存済み基準 | 1,353 | 2.61% | 378 | 4.06% |
| 20 | 元モデルの再実行 | 1,354 | 2.60% | 379 | 4.03% |
| 20 | ASRFT-a | 1,360 | 2.53% | 419 | 3.33% |
| 20 | ASRFT-b | 1,375 | 2.55% | 395 | 3.60% |
| 20 | ASRFT-c | 1,361 | 2.61% | 421 | 3.24% |
| 32 | 保存済み基準 | 1,351 | 2.67% | 403 | 3.63% |
| 32 | 元モデルの再実行 | 1,352 | 2.65% | 404 | 3.60% |
| 32 | ASRFT-a | 1,359 | 2.61% | 427 | 3.18% |
| 32 | ASRFT-b | 1,373 | 2.57% | 410 | 3.39% |
| 32 | ASRFT-c | 1,359 | 2.64% | 432 | 3.48% |
| 48 | 保存済み基準 | 1,349 | 2.74% | 412 | 3.40% |
| 48 | 元モデルの再実行 | 1,351 | 2.71% | 413 | 3.37% |
| 48 | ASRFT-a | 1,355 | 2.70% | 427 | 3.25% |
| 48 | ASRFT-b | 1,367 | 2.68% | 410 | 3.34% |
| 48 | ASRFT-c | 1,353 | 2.72% | 431 | 3.04% |

- 上限48のbは、保存済み基準に対してval +18語・CER −0.06ポイント、test-novel −2語・CER −0.06ポイント。用語一覧に入るvalの正解語は1,308語から1,398語に増えた。整形後のval用語正答数の改善が、95%到達につながった。
- 上限32のaは同じ上限の保存済み基準に対してval +8語、test-novel +24語・CER −0.45ポイント。運用中の上限48の保存済み基準との比較ではval +10語、test-novel +15語で、両CERはばらつきの範囲。
- cの上限48はtest-novelが+19語・CER −0.36ポイント。実音声に対する精度低下は下表のとおり。
- 元モデルの再実行と保存済み基準の差は、全上限で最大2語・0.04 CERポイント未満だった。

Haasの再認識はヒント列が変わった発話で実施した。残りは保存済みの認識と採否を再利用した。採否後の本文を保存済み基準と比べた。

| 条件 | valの再認識 /1,000 | valの本文差分 | test-novelの再認識 /500 | test-novelの本文差分 |
| --- | ---: | ---: | ---: | ---: |
| 元モデルの再実行 | 49 | 3 | 4 | 0 |
| ASRFT-a | 765 | 53 | 437 | 57 |
| ASRFT-b | 773 | 53 | 438 | 58 |
| ASRFT-c | 768 | 55 | 445 | 62 |

### 補助ASR単体

| 条件 | val表記 /1,427 | val CER | test-novel表記 /500 | test-novel CER | 実音声500件 CER | pub-eval 300件 CER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 元モデルの再実行 | 223 | 14.07% | 31 | 14.80% | 14.05% | 50.53% |
| ASRFT-a | 1,117 | 5.56% | 241 | 10.07% | 11.54% | 48.09% |
| ASRFT-b | 1,257 | 3.77% | 206 | 10.05% | 11.53% | 48.92% |
| ASRFT-c | 1,147 | 5.38% | 241 | 9.83% | 24.54% | 57.80% |

実音声500件では元モデルからaが−2.51、bが−2.52、cが+10.49 CERポイント。1ポイント以上悪化したのはcだった。pub-evalでもaとbはCERが下がり、cは7.27ポイント悪化した。aとcは学習率とepoch数が共通で、実音声を混ぜたaのほうが実音声のCERを抑えた。1 epochの総ステップ数はaが559、cが445。aとbは学習率とepoch数が両方異なる。

推論はfacultyのTransformers BF16で行った。アプリのMLX 8bitでの精度と遅延は未測定。GPUキューの完了後、今回の学習・評価・監視プロセスが残っていないことを確認した。[全条件の集計](../../runs/asr-ft/results.json)

## データ

| 集合 | 件数 | 正解文 |
| --- | ---: | --- |
| 合成の学習音声 | 56,953 | `spoken_text_mixed`。フィラーと言い直しを含む |
| 実音声の学習音声 | 14,515 | YODASの投稿者字幕 `spoken_text` |
| 合成val | 1,000 | 学習中のlossは `spoken_text_mixed` |
| test-novel | 500 | ASR単体と全体の評価 |
| 実音声の検証 | 500 | 投稿者字幕。ID順から `random.Random(0).sample` で取り分けた |
| pub-eval | 300 | 既存の公開音声評価の投稿者字幕 |

合成音声の元56,970件は、以前のASR出力の12,000件と44,970件にそれぞれIDで照合した。学習用の既存除外表に収録されている初見語500語は、初見語専用の既存リスト `exclude-v2-plus-novel.txt` にも全語があった。このリストを書き起こしへ照合すると、用語ラベルに記載されていない表記が17件あった。音声ごと除外した内訳はK-means 6件、INI 5件、AOT 6件。残った学習行への表記混入、評価とのID・音声パスの重複、pub-evalとのYODAS動画IDの重複はいずれも0件。表記の検査はNFKC・大小文字をそろえ、英数字と下線の境界を用いた。実音声の元15,015件は、Haasか元のQwenのCERが投稿者字幕に対して15%以下だった発話から成る。発話単位で取り分けた実音声500件のうち498件は、学習データにも発話がある動画から採られている。[データ監査](../../runs/asr-ft/data-audit.json) · [動画の重複集計](../../runs/asr-ft/real-video-audit.json)

## 学習条件

| 条件 | 合成 | 実音声 | 学習率 | Epoch |
| --- | ---: | ---: | ---: | ---: |
| ASRFT-a | 56,953 | 14,515 | 1e-5 | 1 |
| ASRFT-b | 56,953 | 14,515 | 3e-5 | 2 |
| ASRFT-c | 56,953 | 0 | 1e-5 | 1 |

元の重みは `Qwen/Qwen3-ASR-0.6B` revision `5eb144179a02acc5e5ba31e748d22b0cf3e303b0`。前回の1段化実験のfaculty環境 `~/voiceime-work-qwenasr/exp-2026-11-21-qwen3asr-e2e/.venv` を再利用した。全782,426,112パラメータを対象に、seedとdata seedは0、batch 8 × 勾配蓄積16、実効batch 128、AdamW、linear scheduler、warmup 2%、最大勾配ノルム1.0を共通にした。合成val全件で200 stepごととepoch末にlossを測定し、最良の `best` と最後の `final` をHF形式で保存する。[Qwen3-ASRの公式学習手順](https://github.com/QwenLM/Qwen3-ASR/blob/7c6daf77a2421100f5fb066495372c00129d39ff/finetuning/README.md)

公式のprocessorとTrainerを使い、推論と同じ空のsystem messageと `language Japanese<asr_text>` を入力に置いた。教師ラベルは書き起こし本文と終了トークンだけ。CPUで確認した24件の学習・検証例では、教師ラベルを復号した文字列が全件で一致した。前回の全層学習で音声エンコーダの勾配が非有限になったため、パラメータとAdamWの状態をFP32で保持し、順伝播はBF16の自動混合精度を使った。cuDNN SDPAを無効にした。公式forwardはmicrobatch内の平均lossを返すため、Trainerで各stepの勾配蓄積回数で割る設定にした。

### 学習の完了記録

| 条件 | GPU | 実行時間 | 最良ステップ | 合成val loss |
| --- | ---: | ---: | ---: | ---: |
| ASRFT-a | 1 | 46分46秒 | 559 | 0.09215 |
| ASRFT-b | 2 | 85分58秒 | 1,118 | 0.07248 |
| ASRFT-c | 3 | 37分29秒 | 445 | 0.09023 |

3条件とも最良は最終ステップだった。各条件の `best` と `final` の重みは同じSHA-256で、全6ファイルの各782,426,112要素に非有限値はなかった。学習終了時の出力ディレクトリは各条件に `best` と `final` の2つだった。[学習と検証の集計](../../runs/asr-ft/results.json)

初回はプロセス名の付け方で仮想環境を認識できず、学習前に終了した。作業ディレクトリ内の仮想環境のリンクで修正した。次の起動では勾配蓄積時の損失の割り算が省かれていると確認し、3本とも最初の保存前に停止した。上表は補正後に共通の条件で最初から実行した結果。

## 評価方法

- ASR単体は、元と追加学習のbestをTransformers BF16、greedy、batch 8、最大512トークン、日本語指定・context空で比較する。合成valとtest-novelのCERは既存 `voiceime.eval` の処理で用語を最初の読みにそろえ、発話文を参照にする。用語表記は正解出現数までの厳密一致を主指標とする。実音声とpub-evalのCERは字幕を参照にする。
- 全体はHaas初回の保存結果を使う。Haasのヒントは当時と同じ候補プール・上限16語・240文字で選び直す。ヒントが変わった発話はspeech.cppで認識し直し、読み類似度の閾値0.80で区間の採否を行う。同じヒント列の発話は保存済みの認識と採否を再利用する。
- 整形用の一覧は、Haas初回と追加学習後Qwenの出力を改行でつなぎ、既存の選択器 `c2ad276` で上限20・32・48語を選び直す。FULL-scratch bestと `fix1/capacity-eval.sh` と同じ整形入力・推論・採点を使用する。最終文のCERは `target_text` を参照にする。
- valの保存済み基準では、整形用の一覧選択と、Haasのヒント選択・条件Dの入力で、元のQwenの別の推論結果を使っていた。1,000件のうち854件で本文が一致する。保存済み基準の照合には当時のそれぞれの出力を使う。元のQwenを追加学習版と同じ条件で推論し直した評価も行い、この比較では新しい出力を両方で使う。

## 再現手順

facultyの `~/voiceime-work-asrft/` に今回のスクリプトと入力・実行結果がある。facultyで `python3 prepare.py` を実行すると、入力の照合とseed 0の分割を再現できる。集計対象の学習は `60-asrft-{a,b,c}-train-retry2.sh` をキューへ登録し、`python3 -u monitor.py` で完了した順に評価を登録した。GPUの指定はキューが行う。再実行時は新しい出力名を使う。行ごとの出力とモデルはfaculty側にある。全体評価の初回は、valのHaas初回JSONLに処理時間が無く停止した。対応する既存トレースの値を使うよう修正し、保存済みのQwen出力から評価を再開した。学習・評価スクリプト、元の重み、整形の重みの参照情報は集計とともに保存した。[実行設定](../../runs/asr-ft/config.json) · [従来の基準を再採点した集計](../../runs/asr-ft/pipeline-baseline.json)

## MLX 8bitへの変換

MLX Audio 0.6.7の `mlx_audio.convert` はローカルのHF形式を読み、Qwen3-ASRの `thinker.` 接頭辞と畳み込み重みの軸順をMLX用に変換する。Qwen3-ASRの量子化条件は音声エンコーダを対象外にする。現行 `mlx-community/Qwen3-ASR-0.6B-8bit` は affine 8bit・group size 64で、非量子化の浮動小数点重みはBF16。現行と同じ指定で変換できる。手元の実行環境ではMetalデバイスを開けなかったため、変換後モデルの読み込みと推論は未確認。[MLX Audioの変換手順](https://github.com/Neywa-Labs/mlx-audio#quantization) · [Qwen3-ASRのMLX実装](https://github.com/Neywa-Labs/mlx-audio/blob/main/mlx_audio/stt/models/qwen3_asr/qwen3_asr.py) · [現行8bit版の設定](https://huggingface.co/mlx-community/Qwen3-ASR-0.6B-8bit/blob/main/config.json)

PMのApple Silicon Macで、HF形式の重みと補助ファイルがそろったディレクトリを `HF_DIR` に指定する。既存の `uv` 環境からMLX Audio 0.6.7を使う。

```bash
HF_DIR='/path/to/ASRFT-a/best'
MLX_DIR='./models/asr/qwen3-asr-0.6b-asrft-a-8bit'

uv run --no-sync python -m mlx_audio.convert \
  --hf-path "$HF_DIR" --mlx-path "$MLX_DIR" --model-domain stt \
  --dtype bfloat16 --quantize --q-bits 8 --q-group-size 64 --q-mode affine

uv run --no-sync python -c '
import sys
from pathlib import Path
from voiceime.asr.base import load_audio
from voiceime.asr.mlx_audio_backend import MlxAudioLLMTranscriber
model = MlxAudioLLMTranscriber(sys.argv[1], "qwen3-asr")
print(model.transcribe(load_audio(Path(sys.argv[2]))).text)
' "$MLX_DIR" /path/to/check.wav
```
