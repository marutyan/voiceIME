# 用語選択の索引化と優先順位の評価（2026-11-22）

## 仮説

読みの一部が一致しただけの長い用語を一致範囲の割合で減点し、読みと表記の索引から候補だけを採点すれば、第2版でも正解語を上位8件へ多く残せる。本人用と第1版の用語を先に選び、第2版を残りの枠へ回せば、第1版の語の取りこぼしを増やさず、選択時間を1件20ms以内にできる。

## 条件

比較対象は変更前の全語採点（`旧`）と、今回の候補索引・部分一致減点（`新`）。第1版単独と、第2版単独の旧選択、および第1版を優先して第2版で空き枠を埋める新選択を比較した。全条件で最小スコア75、選択上限16語とし、上位4・8・16語に正解用語が含まれる割合を集計した。1件の正解用語を1単位とし、選択語は発話ごとの`terms`に表記があるかで判定した。

第1版は1,458語。第2版は31,415語で、除外リストの84表記を指定した。このうち第2版に含まれていた83語を除き、旧第2版と新方式の第2版プールは31,332語になった。除外リストの残り1語は第2版に元から無い。新方式では索引を一度構築し、選択時間には構築時間を含めない。頻出n-gramの候補取得上限は2文字が100語、3文字が500語。

読みはカタカナとローマ字のキーを索引に登録し、発話文のカタカナと英数字が混じる区間もローマ字にそろえて照合した。英字表記はNFKC・小文字化と空白・記号の除去を行った。一致スコアには、照合器の類似度と「一致した読みの長さ／用語キー全体の長さ」の百分率の小さい方を使う。同点なら本人用・第1版を先にし、その後で元の用語集順を保つ。

本人用の用語集ファイルは評価環境に見つからず、0件で実行した。したがって本人用語集の実データを含めた成績は未測定。第1版と旧第2版の語彙選択は、保存済みASR結果に対して旧選択処理を再現した比較用コードで再計算した。ASRと整形LLMは再実行していない。選択規則と閾値は全評価の前に固定し、`dev-user`は回帰確認に使った。複数seedの反復と信頼区間は測定していない。

辞書のSHA-256は第1版が`008fdc9223406c950e80f940dc10b2215c1d90a46f82e35c35a30062d250fccf`、第2版が`7a46b80506fa7e7983a005db83d241c253f8878413b3bf5a9406daf1d6b798c9`、除外リストが`62ee11ebea71edf3083a70edd1ea0a598dfd593879d7a3d8505483c86de8f51e`。

| データ | 発話数・正解用語数 | 正解の出典（SHA-256） | 保存済み1回目のASR出力（SHA-256） |
| --- | ---: | --- | --- |
| `dev-user` | 100件・67語 | `data/dev-user/manifest.jsonl`<br>`f6e6984bba39ea79241a451941e21c5461296026db0ba42520950bea58880f0b` | `runs/v2gloss/asr-v2-t16-s75.hints.jsonl`の`first_pass`<br>`8e84e4f94a8e628cbfa430edeeb2f8dd8e9126a5e4ecb6247ea5711d24c181a2` |
| `test-novel` | 500件・500語 | `runs/asr-tts/r3-audio-20261122/test-novel-source.jsonl`<br>`9fb8c7ef83fde5d845a87164871635a97285f62892b2c45b1348fe11202753ac` | `runs/asr-tts/r3-audio-20261122/test-novel-include-novel-plain.jsonl`の`hyp`<br>`d0d29ecbb4351700e9098d0d0de23225cde238de07b4fda62388018188e754d8` |
| `val` | 1,000件・1,427語 | `data/tts/val/manifest.jsonl`<br>`89d96b02e9fa064b9b93f8c6ea21cea87fb19acc7b04aa26965661f7cb0424b6` | `runs/asr-tts/haas-val.jsonl`の`hyp`<br>`64122926c8dc9a9333d9c8e4a9adb04fab2309e4d9a7313f66228d2b9bc00708` |

`test-novel`では第1版に正解語が1つも無いため、第1版の正解含有率は算出できない。評価スクリプトは`data/text/glossary.jsonl`、`data/text/glossary-v2.jsonl`、`data/text/glossary-v2-excluded.txt`を読み、`runs/term-select/selection-comparison.json`に発話文を含めず集計値を保存した。比較コードは`feat/term-select`の作業ツリー（開始時のHEAD `61e23f4f81b6be293cb7552954b1e43f1e584d1b`）にある`scripts/evaluate_term_selection.py`。

## 結果

### 上位K語に正解が入る割合

セルは「正解語を含んだ数／対象正解語数（率）」。

#### `dev-user`（67語）

| 選択条件 | 上位4語 | 上位8語 | 上位16語 |
| --- | ---: | ---: | ---: |
| 第1版・旧 | 37/67（55.2%） | 44/67（65.7%） | 51/67（76.1%） |
| 第1版・新 | 49/67（73.1%） | 58/67（86.6%） | 60/67（89.6%） |
| 第2版・旧 | 34/67（50.7%） | 42/67（62.7%） | 45/67（67.2%） |
| 第2版・新（第1版を優先） | 52/67（77.6%） | 58/67（86.6%） | 59/67（88.1%） |

#### `test-novel`（500語）

| 選択条件 | 上位4語 | 上位8語 | 上位16語 |
| --- | ---: | ---: | ---: |
| 第1版・旧／新 | —（正解0語が辞書内） | —（正解0語が辞書内） | —（正解0語が辞書内） |
| 第2版・旧 | 76/500（15.2%） | 102/500（20.4%） | 145/500（29.0%） |
| 第2版・新（第1版を優先） | 46/500（9.2%） | 160/500（32.0%） | 286/500（57.2%） |

#### `val`（1,427語）

| 選択条件 | 上位4語 | 上位8語 | 上位16語 |
| --- | ---: | ---: | ---: |
| 第1版・旧 | 811/1,427（56.8%） | 1,046/1,427（73.3%） | 1,143/1,427（80.1%） |
| 第1版・新 | 998/1,427（69.9%） | 1,123/1,427（78.7%） | 1,184/1,427（83.0%） |
| 第2版・旧 | 781/1,427（54.7%） | 987/1,427（69.2%） | 1,068/1,427（74.8%） |
| 第2版・新（第1版を優先） | 1,062/1,427（74.4%） | 1,170/1,427（82.0%） | 1,207/1,427（84.6%） |

### 上位16語の正解外候補数と選択時間

「正解外」は発話ごとの`terms`に表記が無い選択語を指す。語の意味上の関連性を人手で判定した数ではない。時間は1回の選択あたりの中央値／p90。

| データ | 条件 | 正解外候補数（発話あたり） | 選択時間（中央値／p90） |
| --- | --- | ---: | ---: |
| `dev-user` | 第1版・旧 | 1,068（10.68） | 7.797／12.402 ms |
|  | 第1版・新 | 1,268（12.68） | 1.244／3.046 ms |
|  | 第2版・旧 | 1,384（13.84） | 182.183／271.927 ms |
|  | 第2版・新 | 1,271（12.71） | 3.021／11.725 ms |
| `test-novel` | 第1版・旧 | 5,901（11.80） | 7.434／11.061 ms |
|  | 第1版・新 | 7,365（14.73） | 1.081／2.624 ms |
|  | 第2版・旧 | 7,747（15.49） | 182.094／260.696 ms |
|  | 第2版・新 | 7,369（14.74） | 3.481／8.976 ms |
| `val` | 第1版・旧 | 11,451（11.45） | 7.658／11.242 ms |
|  | 第1版・新 | 13,218（13.22） | 1.013／2.742 ms |
|  | 第2版・旧 | 14,240（14.24） | 184.488／274.371 ms |
|  | 第2版・新 | 13,401（13.40） | 2.958／9.688 ms |

一度だけ構築する索引の時間は、第1版で18.0〜24.3ms、第1版と第2版の結合で458.3〜484.5msだった。これは各データを評価した際の実測範囲で、発話ごとの選択時間には含まれない。

## 分析

第2版の新方式は`test-novel`の上位8語で20.4%から32.0%へ、`val`で69.2%から82.0%へ上がった。`dev-user`でも62.7%から86.6%へ上がった。第2版の上位16語に入った正解外候補は、3データすべてで減った。

`test-novel`の上位4語は15.2%から9.2%へ下がった。第1版を優先するため、新しい語が上位4枠に届きにくくなる一方、ASRに渡す候補の上位8・16語では正解率が上がった。

第1版単独の新方式は`dev-user`と`val`の上位4・8・16語で旧方式を下回らなかった。一方、正解外候補は`dev-user`で200語、`val`で1,767語増えた。本人読み上げの正解含有率を保ちながら正解外候補を減らす余地が残る。

新方式の第2版選択時間は中央値約3ms、p90は最大11.725msで、目安の20ms以内だった。旧方式の中央値は約182〜184msだった。索引構築は初回の費用として別にかかる。`dev-user`に合わせた調整はしていない。ASR再実行前の語選択評価なので、two-pass後の認識精度、整形後の正表記率、CERへの効果は未確認。

上の表の率はJSONに保存した正解ヒット数を分母で割り、小数第1位に丸めた。評価スクリプトと集計値は`scripts/evaluate_term_selection.py`と`runs/term-select/selection-comparison.json`にある。

## 分かったこと

読みと正規化表記を索引化し、一致範囲の割合で長い用語の部分一致を抑える変更により、第2版の上位8語の正解含有率と選択速度は`test-novel`と`val`で改善した。第1版の正解含有率も下がらなかった。一方、第1版単独では正解外候補が増え、第2版でも`test-novel`の上位4語の正解率は下がった。ASR・整形を同じ音声条件で再実行して、最終出力への影響を確認する必要がある。

## 実装検証

`PYTHONPATH=src UV_PROJECT_ENVIRONMENT=/Users/marutyan/PrivateDev/voiceIME/.venv UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/voiceime-uv-cache uv run --offline pytest -q`は`89 passed in 2.72s`。作業ツリーに仮想環境が無く、オフライン環境に`mlx-metal==0.32.4`が無かったため、既存の仮想環境を指定して依存関係の同期を止めた。`git diff --check`も通過した。

## 次の確認

PMが手元のMacでMetalを使ってASRと整形を再実行する。作業ツリーのルートで実行する。以下のASR出力先は新規パスで、既存結果を上書きしない。本人用の用語集がある環境では、`--glossary-file`の第1版と第2版の間にそのファイルを加える。

```bash
VOICEIME_DATA_ROOT=/Users/marutyan/PrivateDev/voiceIME/data

uv run python -m voiceime.asr.batch \
  --manifest "$VOICEIME_DATA_ROOT/dev-user/manifest.jsonl" \
  --system haas-ja-v1.0-speechcpp-q8_0 \
  --glossary-file "$VOICEIME_DATA_ROOT/text/glossary.jsonl" "$VOICEIME_DATA_ROOT/text/glossary-v2.jsonl" \
  --exclude-terms "$VOICEIME_DATA_ROOT/text/glossary-v2-excluded.txt" \
  --out-plain runs/term-select/metal/dev-user-plain.jsonl \
  --out-two-pass runs/term-select/metal/dev-user-twopass.jsonl \
  --workers 3 --threads 2

uv run python -m voiceime.asr.batch \
  --manifest "$VOICEIME_DATA_ROOT/tts/val/manifest.jsonl" \
  --system haas-ja-v1.0-speechcpp-q8_0 \
  --glossary-file "$VOICEIME_DATA_ROOT/text/glossary.jsonl" "$VOICEIME_DATA_ROOT/text/glossary-v2.jsonl" \
  --exclude-terms "$VOICEIME_DATA_ROOT/text/glossary-v2-excluded.txt" \
  --out-plain runs/term-select/metal/val-plain.jsonl \
  --out-two-pass runs/term-select/metal/val-twopass.jsonl \
  --workers 3 --threads 2
```

`test-novel`の保存済み正解・ASR出力は語選択の再計算に使えたが、現在の作業環境には音声付きmanifestが無い。`test-novel-source.jsonl`には`audio_path`欄がないため、ASR再実行には音声へのパスを含むmanifestが別途必要。

ASRの新しいtwo-pass出力を整形へ渡すコマンド例。`--manifest`にはASR対象のmanifest、`--asr-run`には上で作った`*-twopass.jsonl`を指定する。モデルの読み込みと生成はMetalを使う。

```bash
VOICEIME_MODEL=models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit

uv run python -m voiceime.formatter.run \
  --manifest "$VOICEIME_DATA_ROOT/dev-user/manifest.jsonl" \
  --asr-run runs/term-select/metal/dev-user-twopass.jsonl \
  --model "$VOICEIME_MODEL" --prefix-cache \
  --glossary "$VOICEIME_DATA_ROOT/text/glossary.jsonl" "$VOICEIME_DATA_ROOT/text/glossary-v2.jsonl" \
  --exclude-terms "$VOICEIME_DATA_ROOT/text/glossary-v2-excluded.txt" \
  --out runs/term-select/metal/dev-user-formatted.jsonl

uv run python -m voiceime.formatter.run \
  --manifest "$VOICEIME_DATA_ROOT/tts/val/manifest.jsonl" \
  --asr-run runs/term-select/metal/val-twopass.jsonl \
  --model "$VOICEIME_MODEL" --prefix-cache \
  --glossary "$VOICEIME_DATA_ROOT/text/glossary.jsonl" "$VOICEIME_DATA_ROOT/text/glossary-v2.jsonl" \
  --exclude-terms "$VOICEIME_DATA_ROOT/text/glossary-v2-excluded.txt" \
  --out runs/term-select/metal/val-formatted.jsonl
```

`test-novel`の整形も確認する場合は、音声付きmanifestとそのtwo-pass出力を同じ要領で指定する。ASRを再実行しない場合は、既存の`test-novel-include-novel-twopass.jsonl`を`--asr-run`に指定できるが、これは今回の新選択規則によるASR結果ではない。
