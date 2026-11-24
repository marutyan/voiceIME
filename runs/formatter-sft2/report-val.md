| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 1000/1000 | 14925/47482 (31.43%; 置換 3498、挿入 10644、削除 783) | — | 961/1427 (67.34%) | — | 277 | 1594/1608 (99.13%) | 0.355 / 0.585 | 0 | 0.196 / 0.251 | 0.330 / 0.448 | 0.561 / 0.702 |
| haas2p+sft1-qwen | e2e | 1000/1000 | 4040/47482 (8.51%; 置換 1565、挿入 1308、削除 1167) | — | 1191/1427 (83.46%) | — | 39 | 47/1608 (2.92%) | 0.577 / 0.920 | 0 | 0.337 / 0.397 | 0.535 / 0.718 | 0.883 / 1.098 |
| haas2p+sft2-qwen | e2e | 1000/1000 | 2551/47482 (5.37%; 置換 779、挿入 935、削除 837) | — | 1286/1427 (90.12%) | — | 42 | 6/1608 (0.37%) | 0.559 / 0.882 | 0 | 0.326 / 0.389 | 0.521 / 0.683 | 0.853 / 1.032 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | self_correction | 203/203 | 5439/7784 (69.87%; 置換 689、挿入 4656、削除 94) | 0/203 (0.00%)（言い直しの正答率） | — |
| haas2p(no-format) | e2e | english_phrase | 95/95 | 2180/4948 (44.06%; 置換 965、挿入 1017、削除 198) | 0/95 (0.00%) | — |
| haas2p(no-format) | e2e | instruction_like | 123/123 | 1841/6303 (29.21%; 置換 475、挿入 1236、削除 130) | 3/123 (2.44%) | 21 |
| haas2p(no-format) | e2e | no_change | 99/99 | 195/4325 (4.51%; 置換 138、挿入 34、削除 23) | 65/99 (65.66%)（無変更の保持） | — |
| haas2p(no-format) | e2e | list | 84/84 | 1499/4894 (30.63%; 置換 366、挿入 1054、削除 79) | 4/84 (4.76%) | — |
| haas2p+sft1-qwen | e2e | self_correction | 203/203 | 1194/7784 (15.34%; 置換 278、挿入 581、削除 335) | 80/203 (39.41%)（言い直しの正答率） | — |
| haas2p+sft1-qwen | e2e | english_phrase | 95/95 | 714/4948 (14.43%; 置換 274、挿入 289、削除 151) | 34/95 (35.79%) | — |
| haas2p+sft1-qwen | e2e | instruction_like | 123/123 | 479/6303 (7.60%; 置換 149、挿入 198、削除 132) | 60/123 (48.78%) | 1 |
| haas2p+sft1-qwen | e2e | no_change | 99/99 | 203/4325 (4.69%; 置換 137、挿入 32、削除 34) | 64/99 (64.65%)（無変更の保持） | — |
| haas2p+sft1-qwen | e2e | list | 84/84 | 577/4894 (11.79%; 置換 175、挿入 244、削除 158) | 23/84 (27.38%) | — |
| haas2p+sft2-qwen | e2e | self_correction | 203/203 | 827/7784 (10.62%; 置換 169、挿入 427、削除 231) | 108/203 (53.20%)（言い直しの正答率） | — |
| haas2p+sft2-qwen | e2e | english_phrase | 95/95 | 293/4948 (5.92%; 置換 82、挿入 107、削除 104) | 52/95 (54.74%) | — |
| haas2p+sft2-qwen | e2e | instruction_like | 123/123 | 349/6303 (5.54%; 置換 77、挿入 149、削除 123) | 79/123 (64.23%) | 1 |
| haas2p+sft2-qwen | e2e | no_change | 99/99 | 93/4325 (2.15%; 置換 48、挿入 8、削除 37) | 78/99 (78.79%)（無変更の保持） | — |
| haas2p+sft2-qwen | e2e | list | 84/84 | 407/4894 (8.32%; 置換 104、挿入 194、削除 109) | 31/84 (36.90%) | — |

JSON:
```json
{
  "manifest": "data/tts/val/manifest.jsonl",
  "results": [
    {
      "run": "runs/formatter-sft2/val-haas2p-raw.jsonl",
      "system": "haas2p(no-format)",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 14925,
        "substitutions": 3498,
        "insertions": 10644,
        "deletions": 783,
        "reference_characters": 47482,
        "rate": 0.3143296407059517
      },
      "raw_cer": null,
      "terms": {
        "correct": 961,
        "total": 1427,
        "accuracy": 0.6734407848633497,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 277,
        "basis": "target_textのterms"
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
    },
    {
      "run": "runs/formatter-sft2/val-haas2p+sft1-qwen.jsonl",
      "system": "haas2p+sft1-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 4040,
        "substitutions": 1565,
        "insertions": 1308,
        "deletions": 1167,
        "reference_characters": 47482,
        "rate": 0.08508487426814372
      },
      "raw_cer": null,
      "terms": {
        "correct": 1191,
        "total": 1427,
        "accuracy": 0.8346180798878766,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 39,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 47,
        "manifest_count": 1608,
        "residual_rate": 0.029228855721393034
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 1194,
            "substitutions": 278,
            "insertions": 581,
            "deletions": 335,
            "reference_characters": 7784,
            "rate": 0.15339157245632065
          },
          "exact_matches": 80,
          "exact_match_rate": 0.39408866995073893,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 714,
            "substitutions": 274,
            "insertions": 289,
            "deletions": 151,
            "reference_characters": 4948,
            "rate": 0.14430072756669363
          },
          "exact_matches": 34,
          "exact_match_rate": 0.35789473684210527,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 479,
            "substitutions": 149,
            "insertions": 198,
            "deletions": 132,
            "reference_characters": 6303,
            "rate": 0.07599555767095034
          },
          "exact_matches": 60,
          "exact_match_rate": 0.4878048780487805,
          "suspected_responses": 1,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 203,
            "substitutions": 137,
            "insertions": 32,
            "deletions": 34,
            "reference_characters": 4325,
            "rate": 0.046936416184971096
          },
          "exact_matches": 64,
          "exact_match_rate": 0.6464646464646465,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 577,
            "substitutions": 175,
            "insertions": 244,
            "deletions": 158,
            "reference_characters": 4894,
            "rate": 0.11789946873722926
          },
          "exact_matches": 23,
          "exact_match_rate": 0.27380952380952384,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.577354144945275,
          "p90_s": 0.9195320839760825
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.337266894930508,
            "p90_s": 0.39712929102825
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5353302499861456,
            "p90_s": 0.7177738329977729
          },
          ">15s": {
            "count": 236,
            "median_s": 0.883464917074889,
            "p90_s": 1.0983793954947032
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
      "run": "runs/formatter-sft2/val-haas2p+sft2-qwen.jsonl",
      "system": "haas2p+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 2551,
        "substitutions": 779,
        "insertions": 935,
        "deletions": 837,
        "reference_characters": 47482,
        "rate": 0.05372562234109768
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
            "edit_errors": 827,
            "substitutions": 169,
            "insertions": 427,
            "deletions": 231,
            "reference_characters": 7784,
            "rate": 0.10624357656731757
          },
          "exact_matches": 108,
          "exact_match_rate": 0.5320197044334976,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 293,
            "substitutions": 82,
            "insertions": 107,
            "deletions": 104,
            "reference_characters": 4948,
            "rate": 0.05921584478577203
          },
          "exact_matches": 52,
          "exact_match_rate": 0.5473684210526316,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 349,
            "substitutions": 77,
            "insertions": 149,
            "deletions": 123,
            "reference_characters": 6303,
            "rate": 0.05537045851181977
          },
          "exact_matches": 79,
          "exact_match_rate": 0.6422764227642277,
          "suspected_responses": 1,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 93,
            "substitutions": 48,
            "insertions": 8,
            "deletions": 37,
            "reference_characters": 4325,
            "rate": 0.021502890173410404
          },
          "exact_matches": 78,
          "exact_match_rate": 0.7878787878787878,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 407,
            "substitutions": 104,
            "insertions": 194,
            "deletions": 109,
            "reference_characters": 4894,
            "rate": 0.0831630568042501
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
          "median_s": 0.558572290930897,
          "p90_s": 0.8815570251550526
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.32555745862191543,
            "p90_s": 0.38940195770701397
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5212199590168893,
            "p90_s": 0.6829045041813516
          },
          ">15s": {
            "count": 236,
            "median_s": 0.8531125630252063,
            "p90_s": 1.0317064159899019
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
