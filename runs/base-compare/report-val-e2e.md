| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 1000/1000 | 14925/47482 (31.43%; 置換 3498、挿入 10644、削除 783) | — | 961/1427 (67.34%) | — | 277 | 1594/1608 (99.13%) | 0.355 / 0.585 | 0 | 0.196 / 0.251 | 0.330 / 0.448 | 0.561 / 0.702 |
| haas2p+sft2-qwen | e2e | 1000/1000 | 2551/47482 (5.37%; 置換 779、挿入 935、削除 837) | — | 1286/1427 (90.12%) | — | 42 | 6/1608 (0.37%) | 0.559 / 0.882 | 0 | 0.326 / 0.389 | 0.521 / 0.683 | 0.853 / 1.032 |
| haas2p+sft2-qwen-rerun | e2e | 1000/1000 | 2479/47482 (5.22%; 置換 773、挿入 864、削除 842) | — | 1286/1427 (90.12%) | — | 42 | 6/1608 (0.37%) | 0.643 / 1.034 | 0 | 0.360 / 0.464 | 0.591 / 0.829 | 0.982 / 1.303 |
| haas2p-excl(no-format) | e2e | 1000/1000 | 15925/47482 (33.54%; 置換 4625、挿入 10388、削除 912) | — | 704/1427 (49.33%) | — | 214 | 1596/1608 (99.25%) | 0.350 / 0.584 | 0 | 0.212 / 0.250 | 0.324 / 0.446 | 0.568 / 0.704 |
| haas2p-excl+sft2-qwen | e2e | 1000/1000 | 2890/47482 (6.09%; 置換 1027、挿入 930、削除 933) | — | 1212/1427 (84.93%) | — | 44 | 5/1608 (0.31%) | 0.550 / 0.890 | 0 | 0.329 / 0.390 | 0.508 / 0.683 | 0.865 / 1.029 |

用語正答率（見えない用語 / それ以外）
| 系統 | stage | 全体 | 見えない用語 | それ以外 | 緩い正答率：見えない用語（ASR） | 緩い正答率：それ以外（ASR） |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 961/1427 (67.34%) | 284/433 (65.59%) | 677/994 (68.11%) | — | — |
| haas2p+sft2-qwen | e2e | 1286/1427 (90.12%) | 375/433 (86.61%) | 911/994 (91.65%) | — | — |
| haas2p+sft2-qwen-rerun | e2e | 1286/1427 (90.12%) | 375/433 (86.61%) | 911/994 (91.65%) | — | — |
| haas2p-excl(no-format) | e2e | 704/1427 (49.33%) | 9/433 (2.08%) | 695/994 (69.92%) | — | — |
| haas2p-excl+sft2-qwen | e2e | 1212/1427 (84.93%) | 300/433 (69.28%) | 912/994 (91.75%) | — | — |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | self_correction | 203/203 | 5439/7784 (69.87%; 置換 689、挿入 4656、削除 94) | 0/203 (0.00%)（言い直しの正答率） | — |
| haas2p(no-format) | e2e | english_phrase | 95/95 | 2180/4948 (44.06%; 置換 965、挿入 1017、削除 198) | 0/95 (0.00%) | — |
| haas2p(no-format) | e2e | instruction_like | 123/123 | 1841/6303 (29.21%; 置換 475、挿入 1236、削除 130) | 3/123 (2.44%) | 21 |
| haas2p(no-format) | e2e | no_change | 99/99 | 195/4325 (4.51%; 置換 138、挿入 34、削除 23) | 65/99 (65.66%)（無変更の保持） | — |
| haas2p(no-format) | e2e | list | 84/84 | 1499/4894 (30.63%; 置換 366、挿入 1054、削除 79) | 4/84 (4.76%) | — |
| haas2p+sft2-qwen | e2e | self_correction | 203/203 | 827/7784 (10.62%; 置換 169、挿入 427、削除 231) | 108/203 (53.20%)（言い直しの正答率） | — |
| haas2p+sft2-qwen | e2e | english_phrase | 95/95 | 293/4948 (5.92%; 置換 82、挿入 107、削除 104) | 52/95 (54.74%) | — |
| haas2p+sft2-qwen | e2e | instruction_like | 123/123 | 349/6303 (5.54%; 置換 77、挿入 149、削除 123) | 79/123 (64.23%) | 1 |
| haas2p+sft2-qwen | e2e | no_change | 99/99 | 93/4325 (2.15%; 置換 48、挿入 8、削除 37) | 78/99 (78.79%)（無変更の保持） | — |
| haas2p+sft2-qwen | e2e | list | 84/84 | 407/4894 (8.32%; 置換 104、挿入 194、削除 109) | 31/84 (36.90%) | — |
| haas2p+sft2-qwen-rerun | e2e | self_correction | 203/203 | 827/7784 (10.62%; 置換 169、挿入 427、削除 231) | 108/203 (53.20%)（言い直しの正答率） | — |
| haas2p+sft2-qwen-rerun | e2e | english_phrase | 95/95 | 293/4948 (5.92%; 置換 82、挿入 107、削除 104) | 52/95 (54.74%) | — |
| haas2p+sft2-qwen-rerun | e2e | instruction_like | 123/123 | 349/6303 (5.54%; 置換 77、挿入 149、削除 123) | 79/123 (64.23%) | 1 |
| haas2p+sft2-qwen-rerun | e2e | no_change | 99/99 | 93/4325 (2.15%; 置換 48、挿入 8、削除 37) | 78/99 (78.79%)（無変更の保持） | — |
| haas2p+sft2-qwen-rerun | e2e | list | 84/84 | 367/4894 (7.50%; 置換 104、挿入 154、削除 109) | 31/84 (36.90%) | — |
| haas2p-excl(no-format) | e2e | self_correction | 203/203 | 5567/7784 (71.52%; 置換 885、挿入 4578、削除 104) | 0/203 (0.00%)（言い直しの正答率） | — |
| haas2p-excl(no-format) | e2e | english_phrase | 95/95 | 2295/4948 (46.38%; 置換 1091、挿入 991、削除 213) | 0/95 (0.00%) | — |
| haas2p-excl(no-format) | e2e | instruction_like | 123/123 | 1991/6303 (31.59%; 置換 647、挿入 1196、削除 148) | 1/123 (0.81%) | 18 |
| haas2p-excl(no-format) | e2e | no_change | 99/99 | 182/4325 (4.21%; 置換 132、挿入 27、削除 23) | 66/99 (66.67%)（無変更の保持） | — |
| haas2p-excl(no-format) | e2e | list | 84/84 | 1512/4894 (30.89%; 置換 385、挿入 1036、削除 91) | 3/84 (3.57%) | — |
| haas2p-excl+sft2-qwen | e2e | self_correction | 203/203 | 841/7784 (10.80%; 置換 187、挿入 426、削除 228) | 103/203 (50.74%)（言い直しの正答率） | — |
| haas2p-excl+sft2-qwen | e2e | english_phrase | 95/95 | 321/4948 (6.49%; 置換 96、挿入 109、削除 116) | 45/95 (47.37%) | — |
| haas2p-excl+sft2-qwen | e2e | instruction_like | 123/123 | 392/6303 (6.22%; 置換 112、挿入 160、削除 120) | 71/123 (57.72%) | 1 |
| haas2p-excl+sft2-qwen | e2e | no_change | 99/99 | 105/4325 (2.43%; 置換 56、挿入 13、削除 36) | 79/99 (79.80%)（無変更の保持） | — |
| haas2p-excl+sft2-qwen | e2e | list | 84/84 | 415/4894 (8.48%; 置換 115、挿入 172、削除 128) | 29/84 (34.52%) | — |

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
        "loose_accuracy": null,
        "unseen": {
          "correct": 284,
          "total": 433,
          "accuracy": 0.6558891454965358,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 677,
          "total": 994,
          "accuracy": 0.6810865191146881,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
        "loose_accuracy": null,
        "unseen": {
          "correct": 375,
          "total": 433,
          "accuracy": 0.8660508083140878,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 911,
          "total": 994,
          "accuracy": 0.9164989939637826,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
    },
    {
      "run": "runs/base-compare/val-haas2p+sft2-qwen-rerun.jsonl",
      "system": "haas2p+sft2-qwen-rerun",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 2479,
        "substitutions": 773,
        "insertions": 864,
        "deletions": 842,
        "reference_characters": 47482,
        "rate": 0.05220925824522977
      },
      "raw_cer": null,
      "terms": {
        "correct": 1286,
        "total": 1427,
        "accuracy": 0.9011913104414856,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 375,
          "total": 433,
          "accuracy": 0.8660508083140878,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 911,
          "total": 994,
          "accuracy": 0.9164989939637826,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
          "median_s": 0.6431176459882408,
          "p90_s": 1.0341364239808173
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.36002748005557805,
            "p90_s": 0.46390763324452566
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5908066040137783,
            "p90_s": 0.8289496284793131
          },
          ">15s": {
            "count": 236,
            "median_s": 0.98169314552797,
            "p90_s": 1.3033020829898305
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
      "run": "runs/base-compare/val-haas2p-excl-noformat.jsonl",
      "system": "haas2p-excl(no-format)",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 15925,
        "substitutions": 4625,
        "insertions": 10388,
        "deletions": 912,
        "reference_characters": 47482,
        "rate": 0.3353902531485616
      },
      "raw_cer": null,
      "terms": {
        "correct": 704,
        "total": 1427,
        "accuracy": 0.4933426769446391,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 9,
          "total": 433,
          "accuracy": 0.020785219399538105,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 695,
          "total": 994,
          "accuracy": 0.6991951710261569,
          "loose_correct": null,
          "loose_accuracy": null
        }
      },
      "inserted_terms": {
        "count": 214,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 1596,
        "manifest_count": 1608,
        "residual_rate": 0.9925373134328358
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 5567,
            "substitutions": 885,
            "insertions": 4578,
            "deletions": 104,
            "reference_characters": 7784,
            "rate": 0.7151849948612539
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 2295,
            "substitutions": 1091,
            "insertions": 991,
            "deletions": 213,
            "reference_characters": 4948,
            "rate": 0.46382376717865803
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 1991,
            "substitutions": 647,
            "insertions": 1196,
            "deletions": 148,
            "reference_characters": 6303,
            "rate": 0.3158813263525305
          },
          "exact_matches": 1,
          "exact_match_rate": 0.008130081300813009,
          "suspected_responses": 18,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 182,
            "substitutions": 132,
            "insertions": 27,
            "deletions": 23,
            "reference_characters": 4325,
            "rate": 0.04208092485549133
          },
          "exact_matches": 66,
          "exact_match_rate": 0.6666666666666666,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 1512,
            "substitutions": 385,
            "insertions": 1036,
            "deletions": 91,
            "reference_characters": 4894,
            "rate": 0.3089497343686146
          },
          "exact_matches": 3,
          "exact_match_rate": 0.03571428571428571,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.3501717909821309,
          "p90_s": 0.5842586248531006
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.21221187559422106,
            "p90_s": 0.2501189700094983
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.32386687549296767,
            "p90_s": 0.4459972374956124
          },
          ">15s": {
            "count": 236,
            "median_s": 0.5680917914723977,
            "p90_s": 0.7041926039964892
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
      "run": "runs/base-compare/val-haas2p-excl+sft2-qwen.jsonl",
      "system": "haas2p-excl+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 2890,
        "substitutions": 1027,
        "insertions": 930,
        "deletions": 933,
        "reference_characters": 47482,
        "rate": 0.060865169959142415
      },
      "raw_cer": null,
      "terms": {
        "correct": 1212,
        "total": 1427,
        "accuracy": 0.849334267694464,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 300,
          "total": 433,
          "accuracy": 0.6928406466512702,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 912,
          "total": 994,
          "accuracy": 0.9175050301810865,
          "loose_correct": null,
          "loose_accuracy": null
        }
      },
      "inserted_terms": {
        "count": 44,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 5,
        "manifest_count": 1608,
        "residual_rate": 0.003109452736318408
      },
      "tags": {
        "self_correction": {
          "count": 203,
          "cer": {
            "edit_errors": 841,
            "substitutions": 187,
            "insertions": 426,
            "deletions": 228,
            "reference_characters": 7784,
            "rate": 0.10804213771839671
          },
          "exact_matches": 103,
          "exact_match_rate": 0.5073891625615764,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 321,
            "substitutions": 96,
            "insertions": 109,
            "deletions": 116,
            "reference_characters": 4948,
            "rate": 0.06487469684721099
          },
          "exact_matches": 45,
          "exact_match_rate": 0.47368421052631576,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 392,
            "substitutions": 112,
            "insertions": 160,
            "deletions": 120,
            "reference_characters": 6303,
            "rate": 0.062192606695224494
          },
          "exact_matches": 71,
          "exact_match_rate": 0.5772357723577236,
          "suspected_responses": 1,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 105,
            "substitutions": 56,
            "insertions": 13,
            "deletions": 36,
            "reference_characters": 4325,
            "rate": 0.024277456647398842
          },
          "exact_matches": 79,
          "exact_match_rate": 0.797979797979798,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 415,
            "substitutions": 115,
            "insertions": 172,
            "deletions": 128,
            "reference_characters": 4894,
            "rate": 0.08479771148344913
          },
          "exact_matches": 29,
          "exact_match_rate": 0.34523809523809523,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.5495521260309033,
          "p90_s": 0.8895087574957871
        },
        "duration_groups": {
          "<=5s": {
            "count": 60,
            "median_s": 0.32898645859677345,
            "p90_s": 0.39011677000671624
          },
          "5-15s": {
            "count": 704,
            "median_s": 0.5080297080567107,
            "p90_s": 0.6828807329759001
          },
          ">15s": {
            "count": 236,
            "median_s": 0.8648918124963529,
            "p90_s": 1.0291670005535707
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
  ],
  "unseen_terms": "data/eval/unseen-terms-val.txt"
}
```
