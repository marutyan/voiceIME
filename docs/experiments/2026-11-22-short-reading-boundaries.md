# 短い読みの区間境界を評価する（2026-11-22）

## 仮説

短いカタカナ読みが長い読みの一部に一致しただけで用語が選ばれると、two-passが普通の語を英字用語へ置き換える。読みと英字表記を、カタカナ列または英数字列の全体に照合すれば、誤候補を減らしながら正解語を上位に残せる。ひらがな列は一般語の一部と短い読みに偶然一致しやすいため、保存済みの`val`と`test-novel`で頻度を確かめてから採否を決める。

## 条件

- 第1版は1,458語、第2版は31,415語から除外リストにある83語を除いた31,332語。新選択では第1版を優先し、第2版で空き枠を埋めた。評価時に本人用語集のファイルは指定していない。
- 全条件で最大16語、最小スコア75。正解率は上位4・8・16語に含まれた正解用語の数を、辞書内にある正解語数で割った。正解外候補は上位16語のうち発話行の`terms`に無い表記数で、意味上の関連性を人手では判定していない。
- 「旧全件」は前回保存した`runs/term-select/selection-comparison.json`の値。「境界前」は前回の索引選択を保存済み1回目の出力で再現した。「境界後」は今回の境界ガードを同じ出力で再計算した。旧全件の再計算は省き、保存済み集計を使った。
- 境界対象の短い読みは長音などを除いて正規化した後で1〜2仮名のものとした。カタカナ読みはカタカナ区間全体が読みと等しい場合に限り、ローマ字読みは英数字区間全体とのLevenshtein類似度が75以上の場合に限った。短い読みを持つ語の英字表記も、ローマ字化した仮名列ではなく英数字区間全体だけで照合した。ひらがな列は選択にも区間採否にも使わない。
- 区間採否の`merge_two_pass_text`にも同じ全区間条件を入れた。短い読みはカタカナ区間全体との完全一致、または英数字区間全体とのLevenshtein類似度80以上で採用する。比較には差分部分だけでなく1回目の全文を使い、差分分割が「グラフ」の「ラフ」を独立した区間に見せる場合も誤採用しない。長い読みと英字・仮名混在区間の既存照合は変更していない。
- ASR出力と正解の入力は前回と同じ。データ件数とSHA-256は次のとおり。

| 分割 | 発話数・正解語数 | 正解の出典 | 保存済み1回目の出力 |
| --- | ---: | --- | --- |
| `dev-user` | 100・67 | `data/dev-user/manifest.jsonl` `f6e6984bba39ea79241a451941e21c5461296026db0ba42520950bea58880f0b` | `runs/v2gloss/asr-v2-t16-s75.hints.jsonl`の`first_pass` `8e84e4f94a8e628cbfa430edeeb2f8dd8e9126a5e4ecb6247ea5711d24c181a2` |
| `test-novel` | 500・500 | `runs/asr-tts/r3-audio-20261122/test-novel-source.jsonl` `9fb8c7ef83fde5d845a87164871635a97285f62892b2c45b1348fe11202753ac` | `runs/asr-tts/r3-audio-20261122/test-novel-include-novel-plain.jsonl`の`hyp` `d0d29ecbb4351700e9098d0d0de23225cde238de07b4fda62388018188e754d8` |
| `val` | 1,000・1,427 | `data/tts/val/manifest.jsonl` `89d96b02e9fa064b9b93f8c6ea21cea87fb19acc7b04aa26965661f7cb0424b6` | `runs/asr-tts/haas-val.jsonl`の`hyp` `64122926c8dc9a9333d9c8e4a9adb04fab2309e4d9a7313f66228d2b9bc00708` |

辞書のSHA-256は、第1版が`008fdc9223406c950e80f940dc10b2215c1d90a46f82e35c35a30062d250fccf`、第2版が`7a46b80506fa7e7983a005db83d241c253f8878413b3bf5a9406daf1d6b798c9`、除外リストが`62ee11ebea71edf3083a70edd1ea0a598dfd593879d7a3d8505483c86de8f51e`。

## 結果

各セルは「正解数（率）」、率の分母は見出しの正解語数。`正解外@16`は全発話の正解外候補数。`未カバー／内側`は、正解外候補の短い読みがローマ字化した区間全体を覆わなかった数と、両端とも区間の内側に当たった数を示す。旧全件の短読み診断は保存されていない。

### `dev-user`（67語）

| 選択条件 | 上位4 | 上位8 | 上位16 | 正解外@16 | 未カバー／内側 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 第1版・旧全件 | 37（55.2%） | 44（65.7%） | 51（76.1%） | 1,068 | — |
| 第1版・境界前 | 49（73.1%） | 58（86.6%） | 60（89.6%） | 1,268 | 249／52 |
| 第1版・境界後 | 52（77.6%） | 60（89.6%） | 60（89.6%） | 1,188 | 2／1 |
| 第2版・旧全件 | 34（50.7%） | 42（62.7%） | 45（67.2%） | 1,384 | — |
| 第2版・境界前 | 52（77.6%） | 58（86.6%） | 59（88.1%） | 1,271 | 150／53 |
| 第2版・境界後 | 52（77.6%） | 59（88.1%） | 59（88.1%） | 1,255 | 4／4 |

### `test-novel`（500語）

| 選択条件 | 上位4 | 上位8 | 上位16 | 正解外@16 | 未カバー／内側 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 第1版・旧全件 | —（正解語なし） | —（正解語なし） | —（正解語なし） | 5,901 | — |
| 第1版・境界前 | —（正解語なし） | —（正解語なし） | —（正解語なし） | 7,365 | 1,547／346 |
| 第1版・境界後 | —（正解語なし） | —（正解語なし） | —（正解語なし） | 6,968 | 26／2 |
| 第2版・旧全件 | 76（15.2%） | 102（20.4%） | 145（29.0%） | 7,747 | — |
| 第2版・境界前 | 46（9.2%） | 160（32.0%） | 286（57.2%） | 7,369 | 889／371 |
| 第2版・境界後 | 69（13.8%） | 195（39.0%） | 306（61.2%） | 7,301 | 15／8 |

### `val`（1,427語）

| 選択条件 | 上位4 | 上位8 | 上位16 | 正解外@16 | 未カバー／内側 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 第1版・旧全件 | 811（56.8%） | 1,046（73.3%） | 1,143（80.1%） | 11,451 | — |
| 第1版・境界前 | 998（69.9%） | 1,123（78.7%） | 1,184（83.0%） | 13,218 | 2,769／529 |
| 第1版・境界後 | 1,039（72.8%） | 1,145（80.2%） | 1,195（83.7%） | 12,399 | 32／8 |
| 第2版・旧全件 | 781（54.7%） | 987（69.2%） | 1,068（74.8%） | 14,240 | — |
| 第2版・境界前 | 1,062（74.4%） | 1,170（82.0%） | 1,207（84.6%） | 13,401 | 1,551／538 |
| 第2版・境界後 | 1,084（76.0%） | 1,178（82.6%） | 1,202（84.2%） | 13,222 | 57／16 |

境界後の第2版選択時間は、索引構築を除いて`dev-user`が中央値3.052ms／p90 11.936ms、`test-novel`が3.645ms／9.246ms、`val`が3.043ms／9.830msだった。第1版は順に1.306ms／3.098ms、1.199ms／2.700ms、1.105ms／2.879msだった。

用語集の313種類の二仮名読みをひらがなに直し、ASR出力中のひらがな列を部分文字列検索した。`test-novel`は372/500発話で876箇所、`val`は733/1,000発話で1,715箇所の一致があり、そのうち正解語の読みと表記が対応する一致はtest-novelで0箇所、valで2箇所だった。この集計は文字列の偶然一致を含み、ASRが意図した用語をひらがなで出したと人手判定した件数ではない。ひらがな列を一致対象にしない判断は、この頻度と境界後の上位率に基づく。

## 分析

境界ガードは第2版の上位8語の正解率を`test-novel`で32.0%から39.0%へ、`val`で82.0%から82.6%へ上げた。第2版の正解外候補も`test-novel`で7,369語から7,301語へ、`val`で13,401語から13,222語へ減った。短い読みが区間全体を覆わない正解外候補は`test-novel`で889語から15語へ、`val`で1,551語から57語へ減った。第1版の上位4・8・16語の正解率は`dev-user`と`val`で境界前より下がらなかった。

ひらがな列の部分一致は`test-novel`の74.4%、`val`の73.3%の発話に現れた一方、正解語と読みが対応する一致は2件だけだった。2件は文字列上の一致であり、発話意図の確認はしていない。現時点では、ひらがな内の短読み一致を採らない条件が妥当と判断した。

PMの前回Metal報告では、新選択によって本人の正表記が58/67件から60/67件へ増える一方、整形後CERが3.61%から5.92%へ悪化した。今回の変更後のASR・整形結果はまだ測っていないため、CERへの効果は未確認。PMがMetalで同じ入力を再実行して確かめる。

## 実装と検証

- `GlossaryIndex`は短い読みを索引キーに保持し、カタカナ列の内側一致と、短い読みを持つ英字用語のローマ字列内の部分一致を除いた。実際の英数字区間全体が読みに近い場合は選べる。
- `merge_two_pass_text`は短い読みの一致に元の1回目全文の境界を使う。差分抽出で仮に分かれた短い片を独立した発話区間として扱わない。
- `scripts/evaluate_term_selection.py --boundary-only`で保存済み出力を再計算し、集計だけを`runs/term-select/boundary-comparison.json`へ保存した。旧全件の値は`selection-comparison.json`から読み込んだ。
- `PYTHONPATH=src UV_PROJECT_ENVIRONMENT=/Users/marutyan/PrivateDev/voiceIME/.venv UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/voiceime-uv-cache uv run --offline pytest -q`は`108 passed in 2.92s`。`git diff --check`も通過。
- MetalでASRと整形を再実行していないため、二回目の認識結果、整形後の正表記率、CERは未測定。

## Metalでの再実行

ASR一括実行には前回と同じ引数へ`--two-pass-policy segment-merge`を追加する。出力先は既存結果を上書きしない新しい名前にする。

```bash
VOICEIME_DATA_ROOT=/Users/marutyan/PrivateDev/voiceIME/data
VOICEIME_MODEL=models/formatter/sft2-qwen3.5-0.8b-full/mlx-4bit

uv run python -m voiceime.asr.batch \
  --manifest "$VOICEIME_DATA_ROOT/dev-user/manifest.jsonl" \
  --system haas-ja-v1.0-speechcpp-q8_0 \
  --glossary-file "$VOICEIME_DATA_ROOT/text/glossary.jsonl" "$VOICEIME_DATA_ROOT/text/glossary-v2.jsonl" \
  --exclude-terms "$VOICEIME_DATA_ROOT/text/glossary-v2-excluded.txt" \
  --out-plain runs/term-select/metal/dev-user-short-boundary-plain.jsonl \
  --out-two-pass runs/term-select/metal/dev-user-short-boundary-twopass.jsonl \
  --two-pass-policy segment-merge \
  --workers 3 --threads 2

uv run python -m voiceime.formatter.run \
  --manifest "$VOICEIME_DATA_ROOT/dev-user/manifest.jsonl" \
  --asr-run runs/term-select/metal/dev-user-short-boundary-twopass.jsonl \
  --model "$VOICEIME_MODEL" --prefix-cache \
  --glossary "$VOICEIME_DATA_ROOT/text/glossary.jsonl" "$VOICEIME_DATA_ROOT/text/glossary-v2.jsonl" \
  --exclude-terms "$VOICEIME_DATA_ROOT/text/glossary-v2-excluded.txt" \
  --out runs/term-select/metal/dev-user-short-boundary-formatted.jsonl
```

この作業ツリーにある`dev-user/manifest.jsonl`は100件。PMの比較対象が50件の部分集合なら、同じ50件のmanifestを`--manifest`へ指定して比較する。今回の作業ではそのmanifestのパスを確認していない。
