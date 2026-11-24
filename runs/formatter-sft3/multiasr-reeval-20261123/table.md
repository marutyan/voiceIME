# 多言語ASR併用入力での既存モデル再評価

評価はfacultyのTransformers BF16 greedy推論。val 1,000件、test-novel 500件。用語正答はmainの`src/voiceime/eval/`定義、出力には`apply_output_style`を適用した。すべての新条件でHaas 1回目を共通にし、2回目と用語一覧をQwen併用データへ差し替えた。

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

従来条件の値は[2026-11-22の再評価記録](../../../docs/experiments/2026-11-22-formatter-sft3.md)から引用した。従来条件とQwen条件では2回目のASR文と用語一覧が異なる。Qwen plainの2回目はHaas 1回目と同じ本文だったため、Qwen plainはQwen併用用語一覧を使ったときの比較になる。Qwen segment-mergeでは2回目の本文も区間結合後へ変わる。

Qwen併用の選択一覧にはtest-novel正解語が369/500件、val正解語が1,312/1,427件含まれた。新条件4モデル×2 split×2 variantすべてで、予測JSONLのID順、1回目、2回目、用語一覧が指定元と一致することを[`audit_multiasr_eval.py`](../audit_multiasr_eval.py)で確認した。集計JSONは[`selected-term-audit.json`](selected-term-audit.json)。

評価ジョブの所要時間とGPU使用率はB 147秒・27.6%、B-2B 148秒・38.2%、B-drop0-seed1 143秒・23.0%、B-2B-drop0 147秒・52.0%。各値はキューの`.util`記録による。GPU使用率の再調整は行っていない。
