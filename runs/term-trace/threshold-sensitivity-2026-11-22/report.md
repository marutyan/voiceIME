# 区間結合の閾値感度

## 仮説と選択規則

閾値0.75が本人録音以外でも読み揃えCERと用語正表記を両立し、valで選んだ閾値がtest-novelでも大きく崩れない。

閾値の選択にはvalだけを使う。dev-userとtest-novelは選択後の確認集合として数値を出す。
val内でterm exactを最大化しCERを最小化するPareto比較。唯一の非支配閾値を選び、全閾値同値なら既定0.75を保つ。

## 条件

- **val**: 1000発話、指標対象1000件。用語集v1、除外なし。asr.batchの実行例と2026-11-21のASR-TTS記録に従う。
  manifest `/Users/marutyan/PrivateDev/voiceIME/data/tts/val/manifest.jsonl`、用語集SHA-256 `008fdc9223406c950e80f940dc10b2215c1d90a46f82e35c35a30062d250fccf`、除外なし。
  ヒントはselect_glossary + asr_hints。方式 `surface-reading`。
- **test-novel**: 500発話、指標対象500件。用語集v2、既存84語を除外してnovel語は含める。2026-11-22-r3-audio記録とSHA-256を照合した。
  manifest `/Users/marutyan/PrivateDev/voiceIME/runs/asr-tts/r3-audio-20261122/test-novel-source.jsonl`、用語集SHA-256 `7a46b80506fa7e7983a005db83d241c253f8878413b3bf5a9406daf1d6b798c9`、84語除外、SHA-256 `62ee11ebea71edf3083a70edd1ea0a598dfd593879d7a3d8505483c86de8f51e`。
  ヒントはselect_glossary + asr_hints。方式 `surface-reading`。
- **dev-user**: 100発話、指標対象50件。v2glossの保存済み実ヒントを使用。metaはv1用語集、除外なし、score 75、選択上限20、ASRヒント上限16/240文字を記録。
  manifest `/Users/marutyan/PrivateDev/voiceIME/data/dev-user/manifest.jsonl`、用語集SHA-256 `008fdc9223406c950e80f940dc10b2215c1d90a46f82e35c35a30062d250fccf`、除外なし。
  ヒントはsaved。方式 `surface-reading`。

## 用語正表記と読み揃えCER

| 集合 | 方針 | 用語正表記 | 読み揃えCER |
| --- | --- | ---: | ---: |
| val | 2回目そのまま | 961/1427 | 6150/59405 (10.35%) |
| val | 区間結合 0.60 | 874/1427 | 6043/59405 (10.17%) |
| val | 区間結合 0.70 | 858/1427 | 5930/59405 (9.98%) |
| val | 区間結合 0.75 | 856/1427 | 5838/59405 (9.83%) |
| val | 区間結合 0.80 | 847/1427 | 5748/59405 (9.68%) |
| test-novel | 2回目そのまま | 96/500 | 5357/31168 (17.19%) |
| test-novel | 区間結合 0.60 | 82/500 | 4529/31168 (14.53%) |
| test-novel | 区間結合 0.70 | 81/500 | 4358/31168 (13.98%) |
| test-novel | 区間結合 0.75 | 80/500 | 4320/31168 (13.86%) |
| test-novel | 区間結合 0.80 | 80/500 | 4228/31168 (13.57%) |
| dev-user | 2回目そのまま | 44/67 | 412/2953 (13.95%) |
| dev-user | 区間結合 0.60 | 43/67 | 392/2953 (13.27%) |
| dev-user | 区間結合 0.70 | 43/67 | 382/2953 (12.94%) |
| dev-user | 区間結合 0.75 | 42/67 | 377/2953 (12.77%) |
| dev-user | 区間結合 0.80 | 42/67 | 375/2953 (12.70%) |

## valでの閾値判定

valのPareto閾値は 0.6, 0.7, 0.75, 0.8。複数指標に共通する単一の閾値は選べず、valのCERと用語正答率のどちらを優先するかPM判断が必要。
valで0.75が断った正解用語の型（出現数）: `{"mixed_latin_kana_surface_split": 53, "other_rejection": 50, "reading_similarity_0.70_to_0.75": 2}`。
`mixed_latin_kana_surface_split`は、正しいsurfaceが等価diffと変更diffにまたがり、1回目に英字と仮名が混ざるInfiniBand型。
`reading_similarity_0.70_to_0.75`は、0.70では採られるが0.75では読み距離で断るcontainerd型。分類は用語出現ごと。

## formatter入力

- **val**:
  - 閾値0.60: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/val-segment-merge-threshold-0.60.jsonl`
  - 閾値0.70: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/val-segment-merge-threshold-0.70.jsonl`
  - 閾値0.75: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/val-segment-merge-threshold-0.75.jsonl`
  - 閾値0.80: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/val-segment-merge-threshold-0.80.jsonl`
- **test-novel**:
  - 閾値0.60: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/test-novel-segment-merge-threshold-0.60.jsonl`
  - 閾値0.70: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/test-novel-segment-merge-threshold-0.70.jsonl`
  - 閾値0.75: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/test-novel-segment-merge-threshold-0.75.jsonl`
  - 閾値0.80: `/Users/marutyan/PrivateDev/voiceIME-wt/term-attrib/runs/term-trace/threshold-sensitivity-2026-11-22/merged/test-novel-segment-merge-threshold-0.80.jsonl`

valとtest-novelのformatter JSONLは元の2回目runの `latency_s` を引き継ぐ。`asr.batch`のtwo-pass行は1回目と2回目の測定時間の合計を保存する。dev-userは保存latencyが関数全体の時間でpassごとの和ではないため、formatter JSONLを出していない。

## 制約

- ASRは再実行していない。保存済みfirst-pass/finalに結合規則を後適用した反実仮想である。
- test-novelとvalは合成音声であり、本人録音以外への汎化をこの二集合で測った。
- formatterは未実行。valとtest-novelのthreshold JSONLはASR stageで、latency_sはtwo-pass行に記録済みの1回目+2回目合計を保持する。dev-userは保存latencyが関数全体の時間で各passの和ではないため、formatter入力JSONLを出していない。
- 閾値間のばらつきは同じ固定出力への決定的な再処理であり、ASR seed間の不確実性ではない。

## 再実行

`./.venv/bin/python runs/term-trace/.work/segment-merge-sensitivity-2026-11-22/analyze.py`
