# 用語選択に別の読みを加える

## 仮説と測定条件

既存の読みと異なる発音でも用語選択で照合できれば、一覧の正解語が増える。候補が増えると、発話の対象語に含まれない語も入りやすくなる。両方を同じ発話で数える。

- 起点は `a703ba2`。第1版と第2版の用語集を重複表記でまとめ、[第3弾ASR評価](2026-11-22-r3-multiasr.md)と同じmanifestと除外リストを使う。valのheld-out語は候補集合から除き、test-novelでは候補に含める。音声の再生成やASRの再実行は行わない。
- facultyの `~/voiceime-work-asr/r3-multiasr-20261122/outputs/` からHaas、Qwen3-ASR 0.6B、1.7Bの初回仮説を用いる。Haas単独と、Haasに各Qwenの仮説を改行で連結した条件を比べる。現行エンジンの補助ASRに合わせ、valの採点にはHaas＋Qwen 0.6Bを使う。
- 正解語数はmanifestの `terms` の各インスタンスについて、`select_glossary()` の上位20語・32語に同じ表記があれば1件とする。分母はval 1,427語・1,000発話とtest-novel 500語・500発話。候補上限は整形に渡す一覧の枠で、ASRの16語・240字制限の適用前を数える。
- 誤選択数は、発話ごとに候補表記から `terms` の集合を引き、その件数を合計する。話した語の代替表記、注釈されていない語、固有名詞に含まれる部分語も数える場合がある。正解と誤選択の増減は、追加された件数と脱落した件数も記録する。
- valでは規則のみと規則＋教師を比較する。上限20と32それぞれで「追加前からの正解増分×10 − 誤選択増分」を計算し、合計が高い方を選ぶ。同点では規則のみを選ぶ。10対1は一覧段階での比較に使う重みで、認識や整形の失敗への換算には使わない。合計が正でなければ基準より改善したとは判断しない。test-novelにはvalで固定した方式を1回当てる。

## 追加読みの生成と照合

1. 語尾の `d`、`ed`、`er`、ヴ・ブ、ティ・チ、ディ・ジ、促音、オ段の長音と「ウ」の表記差を、表記と既存読みから候補にする。短い略語の一字読みと数字の英語・日本語読みも作る。同じ読みへの複数規則の組み合わせは作らない。
2. 教師には用語の表記と既存読みを渡し、実際に使われそうな別の発音を最大1件求める。候補は読みの形式、数字の順序、既存読みとの長さの比、表記か既存読みと対応する子音列の順序を検査する。機械検査は発音としての近さを判定するもので、使用頻度の裏づけにはならない。
3. 長音記号などを従来どおり正規化した後、元の読みと重複する候補、別の語と同音になる候補、3文字未満の候補を除く。出力は `surface` と `readings` を持つJSONL。別の読みは `GlossaryIndex` で完全一致だけを99点とし、3〜4文字はカタカナ区間全体が一致する場合に限る。5文字以上は区間内でも照合する。既存の読みと表記の索引や採点規則、ヒントに渡す先頭読みは従来どおり使う。

`containerd` に対する `コンテナード` は、語尾の `-er` を長音にし、末尾の `d` を「ド」と読む規則から得る。

## 再現手順

手元のPCから `runs/alt-readings/{85-altread-teacher.sh,teacher_requests.py,build_readings.py,evaluate.py}` と `datagen/text_v3/client.py` をfacultyの `~/voiceime-work-altread/20261124/` へ置く。`src/voiceime/formatter/glossary.py` と同階層および親の `__init__.py` も、同作業ディレクトリの `src/` 以下へ配置する。

facultyで `nvidia-smi` を確認後、`85-altread-teacher.sh` を優先度85でキューに入れる。ジョブは割り当てられたGPU 1枚と、キャッシュ済みのGemma 4 31B-itを使う。モデルrevisionは `842da3794eaa0b77d5f08bae87a17459d91ff475`。設定は重みFP8・KVキャッシュFP8、temperature 0、seed 0。応答はfacultyに保存する。

教師生成完了後はfacultyで次を実行する。追加読みとselector、辞書、評価コードのSHA-256をval集計に保存し、test-novelは同じファイルであることを検査してから実行する。

```bash
cd ~/voiceime-work-altread/20261124
export PYTHONPATH="$PWD/src"
altread_python=~/voiceime-work-asr/.venv/bin/python
altread_dictionary=~/voiceime-work-asr/data/glossary

"$altread_python" build_readings.py \
  --glossary "$altread_dictionary/glossary.jsonl" "$altread_dictionary/glossary-v2.jsonl" \
  --output rules.jsonl --report rules-build.json
"$altread_python" build_readings.py \
  --glossary "$altread_dictionary/glossary.jsonl" "$altread_dictionary/glossary-v2.jsonl" \
  --requests requests.jsonl --responses responses.jsonl \
  --output combined.jsonl --report combined-build.json
"$altread_python" evaluate.py --split val \
  --rules rules.jsonl --combined combined.jsonl --output val.json
"$altread_python" evaluate.py --split test-novel \
  --rules rules.jsonl --combined combined.jsonl --val-report val.json --output test-novel.json
```

手元のPCでは、評価した追加読みを使う場合にエンジンの起動時に `--glossary-alt-readings data/text/glossary-alt-readings.jsonl` を指定する。`--glossary` は既存の用語集を指定する引数。追加読みのファイルは、読み込む本体の辞書にある用語にだけ適用される。

## 教師生成とvalでの選択

教師は31,415語を24語ずつ処理し、1,309要求すべてに応答した。形式が合う6,227件のうち、4,094件が表記との対応検査を通った。正規化後の重複と同音衝突を除いた結果、規則由来32,040件と教師由来1,679件、計33,719読みを20,117語に加えた。規則のみでは19,541語に32,042読みを加えた。集計は [規則のみ](../../runs/alt-readings/rules-build.json) と [規則＋教師](../../runs/alt-readings/combined-build.json) に保存した。

最初のキュー実行は、`exec -a` で設定した実行名からPythonが標準ライブラリの場所を解決できず、GPU推論前に終了した。Pythonの起動後にプロセス名を設定するよう修正し、同じ優先度で `85-altread-teacher-retry` を実行した。GPU2で278秒、平均使用率21.9%（10点）だった。終了後、GPU2の使用メモリは0 MiBで、教師・クライアントのプロセスは0件だった。vLLMは `0.32.0+cu129`、PyTorchは `2.13.0+cu129`、Transformersは `5.19.0`。

教師入力のSHA-256は `e0927c1efbf663c3f49f478ae3bdc8281477f2346d12ed8854c5ab62ec64d5c4`、応答は `3223b6c350b8fc68701a2bbf2b1ef8d7b4bdfc53322f9a67e60f2fa3c7c265bf`。両ファイルはfacultyの作業ディレクトリにある。

valでは、規則のみの正解語数と誤選択数は、3種類のASR入力と2つの上限すべてで追加前と同数だった。規則＋教師はHaas＋Qwen 0.6Bの両上限で正解を1件増やし、誤選択を1件減らした。val得点は規則のみ0、規則＋教師22なので、規則＋教師を固定した。正解語1,427件すべてが候補用語集に含まれている。[val集計](../../runs/alt-readings/val.json)

追加読み無効時は、起点commitの選択コードと現在のコードで上位32語の並びを比較した。valの1,000発話×3入力で差は0件だった。[比較結果](../../runs/alt-readings/baseline-check.json)

## 追加前後の結果

valで固定した規則＋教師をtest-novelに1回適用した。test-novelの正解語500件すべてが候補用語集に含まれていた。正解の包含数と誤選択の総数は、3種類のASR入力と両上限で同じだった。[test-novel集計](../../runs/alt-readings/test-novel.json)

| データ | ASR入力 | 上限 | 正解語数（追加前 → 追加後） | 誤選択数（追加前 → 追加後） | 誤選択の追加／脱落 |
| --- | --- | ---: | ---: | ---: | ---: |
| val | Haas | 20 | 1,216 → 1,217 / 1,427 | 16,386 → 16,385 | 2／3 |
| val | Haas | 32 | 1,218 → 1,219 / 1,427 | 24,656 → 24,656 | 2／2 |
| val | Haas＋Qwen 0.6B | 20 | 1,312 → 1,313 / 1,427 | 16,778 → 16,777 | 7／8 |
| val | Haas＋Qwen 0.6B | 32 | 1,314 → 1,315 / 1,427 | 25,800 → 25,799 | 5／6 |
| val | Haas＋Qwen 1.7B | 20 | 1,324 → 1,325 / 1,427 | 16,640 → 16,639 | 3／4 |
| val | Haas＋Qwen 1.7B | 32 | 1,326 → 1,327 / 1,427 | 25,532 → 25,531 | 3／4 |
| test-novel | Haas | 20 | 336 → 336 / 500 | 9,023 → 9,023 | 3／3 |
| test-novel | Haas | 32 | 362 → 362 / 500 | 13,746 → 13,746 | 3／3 |
| test-novel | Haas＋Qwen 0.6B | 20 | 369 → 369 / 500 | 9,313 → 9,313 | 2／2 |
| test-novel | Haas＋Qwen 0.6B | 32 | 414 → 414 / 500 | 14,520 → 14,520 | 2／2 |
| test-novel | Haas＋Qwen 1.7B | 20 | 376 → 376 / 500 | 9,213 → 9,213 | 3／3 |
| test-novel | Haas＋Qwen 1.7B | 32 | 409 → 409 / 500 | 14,267 → 14,267 | 5／5 |

現行エンジンに対応するHaas＋Qwen 0.6Bでは、valが上限20で91.94% → 92.01%、上限32で92.08% → 92.15%。test-novelは順に73.80%、82.80%で一定だった。test-novelの正解は入れ替わりも0件だった。誤選択の総数が同じ条件でも、語の入れ替わりは発生した。

既存の合成音声では、別読みを加えることで初見語の候補漏れが減るという仮説を支持する結果は得られなかった。規則のみの先行確認では、valのHaas初回仮説に追加読みが完全一致した発話は9/1,000件だった。実際に異なる発音をしたときの改善幅、再認識や整形後の精度は今回の集計では不明。エンジンでは明示指定で試せる形にした。

## 成果物と確認

- `data/text/glossary-alt-readings.jsonl` はvalで選んだ規則＋教師の33,719読みを収録する。SHA-256は `63944a8b7d0cce0cbd20874df64b9c13bea91051d4fbba0d731ec83dcb229e1c`。既存の `data/` の設定によりGit管理外。生成と集計のスクリプト、集計JSONは `runs/alt-readings/` にある。
- 手元で読み込んだ出力から「コンテナード」で `containerd` が選ばれ、`surface-reading` のヒントは `containerd=コンテナディー` になることを確かめた。val、test-novel、手元の追加読み、用語集、評価コードのハッシュも照合した。
- `uv run pytest -q` は123件成功（既存119件と追加4件）。facultyからの成果物転送は2,144,756バイト。
