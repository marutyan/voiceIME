# 用語の工程別切り分け

対象は50発話、用語67回。

| 段階 | 正表記の件数 |
| --- | ---: |
| 1回目 | 0 |
| 2回目 | 44 |
| 整形後 | 56 |
| 2回目で1回目の正表記を破壊 | 0 |
| 2回目で読み距離が増加 | 25 |
| 整形で修正 / 破壊 | 13 / 1 |

## 最終失敗の分類

| 原因 | 件数 |
| --- | ---: |
| first_pass_reading_not_close_or_missing | 8 |
| formatter_broke_two_pass_correct | 1 |
| gold_candidate_not_hinted | 1 |
| two_pass_did_not_correct_term | 1 |

## 略語読みの追加による候補数の見積もり

現行 49/67、自動読み追加 49/67、差 +0。
候補は1回目の保存済み出力に対してのみ再計算し、ASRは動かしていない。

整形JSONLのinput_textと2回目出力の不一致: 0件。
