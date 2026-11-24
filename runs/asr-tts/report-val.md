| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数 | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0 | asr | 1000/1000 | 5355/59405 (9.01%; 置換 2922、挿入 227、削除 2206) | 8881/59222 (15.00%; 置換 5095、挿入 216、削除 3570) | 4/1427 (0.28%) | 533/1427 (37.35%) | 2 | 1604/1608 (99.75%) | 0.180 / 0.293 | 0 | 0.097 / 0.160 | 0.164 / 0.226 | 0.283 / 0.346 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 1000/1000 | 6150/59405 (10.35%; 置換 3639、挿入 467、削除 2044) | 14993/59222 (25.32%; 置換 10084、挿入 1515、削除 3394) | 961/1427 (67.34%) | 995/1427 (69.73%) | 277 | 1594/1608 (99.13%) | 0.355 / 0.585 | 0 | 0.196 / 0.251 | 0.330 / 0.448 | 0.561 / 0.702 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0 | asr | self_correction | 203/203 | 5867/7784 (75.37%; 置換 1423、挿入 4323、削除 121) | 0/203 (0.00%)（言い直しの正答率） | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | english_phrase | 95/95 | 2598/4948 (52.51%; 置換 1476、挿入 892、削除 230) | 0/95 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | instruction_like | 123/123 | 2410/6303 (38.24%; 置換 1130、挿入 1077、削除 203) | 1/123 (0.81%) | 15 |
| haas-ja-v1.0-speechcpp-q8_0 | asr | no_change | 99/99 | 49/4325 (1.13%; 置換 29、挿入 2、削除 18) | 76/99 (76.77%)（無変更の保持） | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | list | 84/84 | 1716/4894 (35.06%; 置換 619、挿入 966、削除 131) | 0/84 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | self_correction | 203/203 | 5439/7784 (69.87%; 置換 689、挿入 4656、削除 94) | 0/203 (0.00%)（言い直しの正答率） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | english_phrase | 95/95 | 2180/4948 (44.06%; 置換 965、挿入 1017、削除 198) | 0/95 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | instruction_like | 123/123 | 1841/6303 (29.21%; 置換 475、挿入 1236、削除 130) | 3/123 (2.44%) | 21 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | no_change | 99/99 | 195/4325 (4.51%; 置換 138、挿入 34、削除 23) | 65/99 (65.66%)（無変更の保持） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | list | 84/84 | 1499/4894 (30.63%; 置換 366、挿入 1054、削除 79) | 4/84 (4.76%) | — |

JSON:
```json
{
  "manifest": "/Users/marutyan/PrivateDev/voiceIME/data/tts/val/manifest.jsonl",
  "results": [
    {
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/asr-tts/haas-val.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0",
      "stage": "asr",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 5355,
        "substitutions": 2922,
        "insertions": 227,
        "deletions": 2206,
        "reference_characters": 59405,
        "rate": 0.09014392727884858
      },
      "raw_cer": {
        "edit_errors": 8881,
        "substitutions": 5095,
        "insertions": 216,
        "deletions": 3570,
        "reference_characters": 59222,
        "rate": 0.14996116308128735
      },
      "terms": {
        "correct": 4,
        "total": 1427,
        "accuracy": 0.002803083391730904,
        "loose_correct": 533,
        "loose_accuracy": 0.373510861948143
      },
      "inserted_terms": {
        "count": 2
      },
      "fillers": {
        "residual_count": 1604,
        "manifest_count": 1608,
        "residual_rate": 0.9975124378109452
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 5867,
            "substitutions": 1423,
            "insertions": 4323,
            "deletions": 121,
            "reference_characters": 7784,
            "rate": 0.7537255909558068
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 2598,
            "substitutions": 1476,
            "insertions": 892,
            "deletions": 230,
            "reference_characters": 4948,
            "rate": 0.5250606305578012
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 2410,
            "substitutions": 1130,
            "insertions": 1077,
            "deletions": 203,
            "reference_characters": 6303,
            "rate": 0.38235760748849756
          },
          "exact_matches": 1,
          "exact_match_rate": 0.008130081300813009,
          "suspected_responses": 15,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 49,
            "substitutions": 29,
            "insertions": 2,
            "deletions": 18,
            "reference_characters": 4325,
            "rate": 0.011329479768786127
          },
          "exact_matches": 76,
          "exact_match_rate": 0.7676767676767676,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 1716,
            "substitutions": 619,
            "insertions": 966,
            "deletions": 131,
            "reference_characters": 4894,
            "rate": 0.35063342868818964
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.1800329374964349,
          "p90_s": 0.2929055411135778
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.0967342290095985,
            "p90_s": 0.15961093750083818
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.16350593703100458,
            "p90_s": 0.22594249995891008
          },
          ">15s": {
            "count": 236,
            "median_s": 0.28309145849198103,
            "p90_s": 0.3459414375247434
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
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/asr-tts/haas2p-val.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 6150,
        "substitutions": 3639,
        "insertions": 467,
        "deletions": 2044,
        "reference_characters": 59405,
        "rate": 0.10352663917178688
      },
      "raw_cer": {
        "edit_errors": 14993,
        "substitutions": 10084,
        "insertions": 1515,
        "deletions": 3394,
        "reference_characters": 59222,
        "rate": 0.2531660531559218
      },
      "terms": {
        "correct": 961,
        "total": 1427,
        "accuracy": 0.6734407848633497,
        "loose_correct": 995,
        "loose_accuracy": 0.6972669936930623
      },
      "inserted_terms": {
        "count": 277
      },
      "fillers": {
        "residual_count": 1594,
        "manifest_count": 1608,
        "residual_rate": 0.9912935323383084
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 5439,
            "substitutions": 689,
            "insertions": 4656,
            "deletions": 94,
            "reference_characters": 7784,
            "rate": 0.6987410071942446
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 2180,
            "substitutions": 965,
            "insertions": 1017,
            "deletions": 198,
            "reference_characters": 4948,
            "rate": 0.44058205335489087
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 1841,
            "substitutions": 475,
            "insertions": 1236,
            "deletions": 130,
            "reference_characters": 6303,
            "rate": 0.2920831350150722
          },
          "exact_matches": 3,
          "exact_match_rate": 0.024390243902439025,
          "suspected_responses": 21,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 195,
            "substitutions": 138,
            "insertions": 34,
            "deletions": 23,
            "reference_characters": 4325,
            "rate": 0.04508670520231214
          },
          "exact_matches": 65,
          "exact_match_rate": 0.6565656565656566,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 1499,
            "substitutions": 366,
            "insertions": 1054,
            "deletions": 79,
            "reference_characters": 4894,
            "rate": 0.3062934205149162
          },
          "exact_matches": 4,
          "exact_match_rate": 0.047619047619047616,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.3548763540457003,
          "p90_s": 0.5852695077308454
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.19591491640312597,
            "p90_s": 0.2506948627182283
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.32979237439576536,
            "p90_s": 0.4477371915127151
          },
          ">15s": {
            "count": 236,
            "median_s": 0.5610186874982901,
            "p90_s": 0.7019643124658614
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
