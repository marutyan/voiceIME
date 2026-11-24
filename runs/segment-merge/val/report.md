| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| val-twopass+sft2-qwen | e2e | 1000/1000 | 2418/47431 (5.10%; 置換 760、挿入 861、削除 797) | — | 1286/1427 (90.12%) | — | 42 | 6/1608 (0.37%) | 0.560 / 0.887 | 0 | 0.325 / 0.391 | 0.525 / 0.686 | 0.859 / 1.037 |
| val-m060+sft2-qwen | e2e | 1000/1000 | 1833/47431 (3.86%; 置換 467、挿入 713、削除 653) | — | 1301/1427 (91.17%) | — | 40 | 7/1608 (0.44%) | 0.565 / 0.896 | 0 | 0.322 / 0.390 | 0.524 / 0.686 | 0.863 / 1.038 |
| val-m080+sft2-qwen | e2e | 1000/1000 | 1792/47431 (3.78%; 置換 448、挿入 696、削除 648) | — | 1301/1427 (91.17%) | — | 41 | 7/1608 (0.44%) | 0.564 / 0.892 | 0 | 0.318 / 0.396 | 0.524 / 0.686 | 0.859 / 1.043 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| val-twopass+sft2-qwen | e2e | self_correction | 203/203 | 816/7777 (10.49%; 置換 166、挿入 426、削除 224) | 111/203 (54.68%)（言い直しの正答率） | — |
| val-twopass+sft2-qwen | e2e | english_phrase | 95/95 | 291/4947 (5.88%; 置換 81、挿入 107、削除 103) | 53/95 (55.79%) | — |
| val-twopass+sft2-qwen | e2e | instruction_like | 123/123 | 343/6299 (5.45%; 置換 74、挿入 149、削除 120) | 81/123 (65.85%) | 1 |
| val-twopass+sft2-qwen | e2e | no_change | 99/99 | 83/4315 (1.92%; 置換 48、挿入 8、削除 27) | 79/99 (79.80%)（無変更の保持） | — |
| val-twopass+sft2-qwen | e2e | list | 84/84 | 367/4894 (7.50%; 置換 104、挿入 154、削除 109) | 31/84 (36.90%) | — |
| val-m060+sft2-qwen | e2e | self_correction | 203/203 | 649/7777 (8.35%; 置換 105、挿入 336、削除 208) | 121/203 (59.61%)（言い直しの正答率） | — |
| val-m060+sft2-qwen | e2e | english_phrase | 95/95 | 253/4947 (5.11%; 置換 61、挿入 101、削除 91) | 59/95 (62.11%) | — |
| val-m060+sft2-qwen | e2e | instruction_like | 123/123 | 285/6299 (4.52%; 置換 60、挿入 147、削除 78) | 84/123 (68.29%) | 1 |
| val-m060+sft2-qwen | e2e | no_change | 99/99 | 29/4315 (0.67%; 置換 15、挿入 5、削除 9) | 85/99 (85.86%)（無変更の保持） | — |
| val-m060+sft2-qwen | e2e | list | 84/84 | 327/4894 (6.68%; 置換 85、挿入 137、削除 105) | 33/84 (39.29%) | — |
| val-m080+sft2-qwen | e2e | self_correction | 203/203 | 658/7777 (8.46%; 置換 108、挿入 336、削除 214) | 120/203 (59.11%)（言い直しの正答率） | — |
| val-m080+sft2-qwen | e2e | english_phrase | 95/95 | 247/4947 (4.99%; 置換 55、挿入 98、削除 94) | 59/95 (62.11%) | — |
| val-m080+sft2-qwen | e2e | instruction_like | 123/123 | 293/6299 (4.65%; 置換 63、挿入 147、削除 83) | 84/123 (68.29%) | 1 |
| val-m080+sft2-qwen | e2e | no_change | 99/99 | 23/4315 (0.53%; 置換 13、挿入 2、削除 8) | 86/99 (86.87%)（無変更の保持） | — |
| val-m080+sft2-qwen | e2e | list | 84/84 | 326/4894 (6.66%; 置換 83、挿入 140、削除 103) | 34/84 (40.48%) | — |

JSON:
```json
{
  "manifest": "data/tts/val/manifest.jsonl",
  "results": [
    {
      "run": "runs/segment-merge/val/e2e-twopass+sft2-qwen.jsonl",
      "system": "val-twopass+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 2418,
        "substitutions": 760,
        "insertions": 861,
        "deletions": 797,
        "reference_characters": 47431,
        "rate": 0.05097931732411292
      },
      "raw_cer": null,
      "terms": {
        "correct": 1286,
        "total": 1427,
        "accuracy": 0.9011913104414856,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 42,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 6,
        "manifest_count": 1608,
        "residual_rate": 0.0037313432835820895
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 816,
            "substitutions": 166,
            "insertions": 426,
            "deletions": 224,
            "reference_characters": 7777,
            "rate": 0.10492477819210493
          },
          "exact_matches": 111,
          "exact_match_rate": 0.5467980295566502,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 291,
            "substitutions": 81,
            "insertions": 107,
            "deletions": 103,
            "reference_characters": 4947,
            "rate": 0.058823529411764705
          },
          "exact_matches": 53,
          "exact_match_rate": 0.5578947368421052,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 343,
            "substitutions": 74,
            "insertions": 149,
            "deletions": 120,
            "reference_characters": 6299,
            "rate": 0.05445308779171297
          },
          "exact_matches": 81,
          "exact_match_rate": 0.6585365853658537,
          "suspected_responses": 1,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 83,
            "substitutions": 48,
            "insertions": 8,
            "deletions": 27,
            "reference_characters": 4315,
            "rate": 0.019235225955967557
          },
          "exact_matches": 79,
          "exact_match_rate": 0.797979797979798,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 367,
            "substitutions": 104,
            "insertions": 154,
            "deletions": 109,
            "reference_characters": 4894,
            "rate": 0.074989783408255
          },
          "exact_matches": 31,
          "exact_match_rate": 0.36904761904761907,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.5601287084282376,
          "p90_s": 0.8866252506617457
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.3254095421289094,
            "p90_s": 0.391262486402411
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5250200625159778,
            "p90_s": 0.6855976708000526
          },
          ">15s": {
            "count": 236,
            "median_s": 0.8591911044786684,
            "p90_s": 1.0366033326135948
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/segment-merge/val/e2e-m060+sft2-qwen.jsonl",
      "system": "val-m060+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 1833,
        "substitutions": 467,
        "insertions": 713,
        "deletions": 653,
        "reference_characters": 47431,
        "rate": 0.038645611519892056
      },
      "raw_cer": null,
      "terms": {
        "correct": 1301,
        "total": 1427,
        "accuracy": 0.9117028731604765,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 40,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 7,
        "manifest_count": 1608,
        "residual_rate": 0.004353233830845771
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 649,
            "substitutions": 105,
            "insertions": 336,
            "deletions": 208,
            "reference_characters": 7777,
            "rate": 0.08345120226308345
          },
          "exact_matches": 121,
          "exact_match_rate": 0.5960591133004927,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 253,
            "substitutions": 61,
            "insertions": 101,
            "deletions": 91,
            "reference_characters": 4947,
            "rate": 0.05114210632706691
          },
          "exact_matches": 59,
          "exact_match_rate": 0.6210526315789474,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 285,
            "substitutions": 60,
            "insertions": 147,
            "deletions": 78,
            "reference_characters": 6299,
            "rate": 0.0452452770280997
          },
          "exact_matches": 84,
          "exact_match_rate": 0.6829268292682927,
          "suspected_responses": 1,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 29,
            "substitutions": 15,
            "insertions": 5,
            "deletions": 9,
            "reference_characters": 4315,
            "rate": 0.006720741599073001
          },
          "exact_matches": 85,
          "exact_match_rate": 0.8585858585858586,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 327,
            "substitutions": 85,
            "insertions": 137,
            "deletions": 105,
            "reference_characters": 4894,
            "rate": 0.06681651001225991
          },
          "exact_matches": 33,
          "exact_match_rate": 0.39285714285714285,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.5653097295435145,
          "p90_s": 0.8956283295876347
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.32195568800671026,
            "p90_s": 0.39002930286806076
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5236286664730869,
            "p90_s": 0.6857914669206366
          },
          ">15s": {
            "count": 236,
            "median_s": 0.8632444160757586,
            "p90_s": 1.0379414994386025
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/segment-merge/val/e2e-m080+sft2-qwen.jsonl",
      "system": "val-m080+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 1792,
        "substitutions": 448,
        "insertions": 696,
        "deletions": 648,
        "reference_characters": 47431,
        "rate": 0.03778119795070734
      },
      "raw_cer": null,
      "terms": {
        "correct": 1301,
        "total": 1427,
        "accuracy": 0.9117028731604765,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 41,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 7,
        "manifest_count": 1608,
        "residual_rate": 0.004353233830845771
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 658,
            "substitutions": 108,
            "insertions": 336,
            "deletions": 214,
            "reference_characters": 7777,
            "rate": 0.0846084608460846
          },
          "exact_matches": 120,
          "exact_match_rate": 0.5911330049261084,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 247,
            "substitutions": 55,
            "insertions": 98,
            "deletions": 94,
            "reference_characters": 4947,
            "rate": 0.04992925005053568
          },
          "exact_matches": 59,
          "exact_match_rate": 0.6210526315789474,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 293,
            "substitutions": 63,
            "insertions": 147,
            "deletions": 83,
            "reference_characters": 6299,
            "rate": 0.04651531989204636
          },
          "exact_matches": 84,
          "exact_match_rate": 0.6829268292682927,
          "suspected_responses": 1,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 23,
            "substitutions": 13,
            "insertions": 2,
            "deletions": 8,
            "reference_characters": 4315,
            "rate": 0.005330243337195829
          },
          "exact_matches": 86,
          "exact_match_rate": 0.8686868686868687,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 326,
            "substitutions": 83,
            "insertions": 140,
            "deletions": 103,
            "reference_characters": 4894,
            "rate": 0.06661217817736004
          },
          "exact_matches": 34,
          "exact_match_rate": 0.40476190476190477,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.5637103554909118,
          "p90_s": 0.8918757173232734
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.31797879160149023,
            "p90_s": 0.39567675442667677
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5237813539570197,
            "p90_s": 0.6859448114410043
          },
          ">15s": {
            "count": 236,
            "median_s": 0.8586158125544898,
            "p90_s": 1.0432697290088981
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    }
  ]
}
```
