| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1-t16-s75+sft2-qwen | e2e | 50/50 | 147/2331 (6.31%; 置換 59、挿入 43、削除 45) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.439 / 0.610 | 0 | 0.166 / 0.166 | 0.372 / 0.562 | 0.597 / 0.729 |
| v1-t16-s75+sft2-qwen-fmtv2 | e2e | 50/50 | 159/2331 (6.82%; 置換 75、挿入 42、削除 42) | — | 55/67 (82.09%) | — | 1 | 1/98 (1.02%) | 0.593 / 0.881 | 0 | 0.250 / 0.250 | 0.571 / 0.770 | 0.854 / 0.996 |
| v2-t16-s75+sft2-qwen-fmtv1 | e2e | 50/50 | 156/2331 (6.69%; 置換 67、挿入 35、削除 54) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.591 / 0.869 | 0 | 0.249 / 0.249 | 0.550 / 0.764 | 0.855 / 0.982 |
| v2-t16-s75+sft2-qwen | e2e | 50/50 | 229/2331 (9.82%; 置換 112、挿入 56、削除 61) | — | 51/67 (76.12%) | — | 2 | 1/98 (1.02%) | 0.772 / 1.160 | 0 | 0.327 / 0.327 | 0.744 / 0.955 | 1.070 / 1.242 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| v1-t16-s75+sft2-qwen | e2e | english_phrase | 10/10 | 33/437 (7.55%; 置換 13、挿入 8、削除 12) | 3/10 (30.00%) | — |
| v1-t16-s75+sft2-qwen | e2e | instruction_like | 11/11 | 39/512 (7.62%; 置換 11、挿入 21、削除 7) | 2/11 (18.18%) | 0 |
| v1-t16-s75+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v1-t16-s75+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v1-t16-s75+sft2-qwen | e2e | self_correction | 8/8 | 27/391 (6.91%; 置換 3、挿入 18、削除 6) | 2/8 (25.00%)（言い直しの正答率） | — |
| v1-t16-s75+sft2-qwen-fmtv2 | e2e | english_phrase | 10/10 | 35/437 (8.01%; 置換 13、挿入 10、削除 12) | 3/10 (30.00%) | — |
| v1-t16-s75+sft2-qwen-fmtv2 | e2e | instruction_like | 11/11 | 48/512 (9.38%; 置換 24、挿入 16、削除 8) | 2/11 (18.18%) | 0 |
| v1-t16-s75+sft2-qwen-fmtv2 | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v1-t16-s75+sft2-qwen-fmtv2 | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v1-t16-s75+sft2-qwen-fmtv2 | e2e | self_correction | 8/8 | 36/391 (9.21%; 置換 16、挿入 13、削除 7) | 2/8 (25.00%)（言い直しの正答率） | — |
| v2-t16-s75+sft2-qwen-fmtv1 | e2e | english_phrase | 10/10 | 38/437 (8.70%; 置換 16、挿入 6、削除 16) | 2/10 (20.00%) | — |
| v2-t16-s75+sft2-qwen-fmtv1 | e2e | instruction_like | 11/11 | 34/512 (6.64%; 置換 11、挿入 16、削除 7) | 2/11 (18.18%) | 0 |
| v2-t16-s75+sft2-qwen-fmtv1 | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t16-s75+sft2-qwen-fmtv1 | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t16-s75+sft2-qwen-fmtv1 | e2e | self_correction | 8/8 | 23/391 (5.88%; 置換 3、挿入 14、削除 6) | 3/8 (37.50%)（言い直しの正答率） | — |
| v2-t16-s75+sft2-qwen | e2e | english_phrase | 10/10 | 47/437 (10.76%; 置換 24、挿入 8、削除 15) | 2/10 (20.00%) | — |
| v2-t16-s75+sft2-qwen | e2e | instruction_like | 11/11 | 54/512 (10.55%; 置換 33、挿入 15、削除 6) | 2/11 (18.18%) | 0 |
| v2-t16-s75+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t16-s75+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t16-s75+sft2-qwen | e2e | self_correction | 8/8 | 67/391 (17.14%; 置換 22、挿入 23、削除 22) | 2/8 (25.00%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/metal-v2gloss/devuser-scripted.jsonl",
  "results": [
    {
      "run": "runs/v2gloss/e2e-v1-t16-s75+sft2-qwen.jsonl",
      "system": "v1-t16-s75+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 147,
        "substitutions": 59,
        "insertions": 43,
        "deletions": 45,
        "reference_characters": 2331,
        "rate": 0.06306306306306306
      },
      "raw_cer": null,
      "terms": {
        "correct": 56,
        "total": 67,
        "accuracy": 0.835820895522388,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 1,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 0,
        "manifest_count": 98,
        "residual_rate": 0.0
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 33,
            "substitutions": 13,
            "insertions": 8,
            "deletions": 12,
            "reference_characters": 437,
            "rate": 0.07551487414187644
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 39,
            "substitutions": 11,
            "insertions": 21,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.076171875
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 57,
            "substitutions": 34,
            "insertions": 10,
            "deletions": 13,
            "reference_characters": 653,
            "rate": 0.08728943338437979
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 6,
            "substitutions": 0,
            "insertions": 1,
            "deletions": 5,
            "reference_characters": 372,
            "rate": 0.016129032258064516
          },
          "exact_matches": 6,
          "exact_match_rate": 0.75,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 27,
            "substitutions": 3,
            "insertions": 18,
            "deletions": 6,
            "reference_characters": 391,
            "rate": 0.06905370843989769
          },
          "exact_matches": 2,
          "exact_match_rate": 0.25,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.43943968799430877,
          "p90_s": 0.6100080752861686
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.16613662510644644,
            "p90_s": 0.16613662510644644
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3721590419881977,
            "p90_s": 0.5620968965231441
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5966664998559281,
            "p90_s": 0.7287910079816357
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 50,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/v2gloss/e2e-v1-t16-s75+sft2-qwen-fmtv2.jsonl",
      "system": "v1-t16-s75+sft2-qwen-fmtv2",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 159,
        "substitutions": 75,
        "insertions": 42,
        "deletions": 42,
        "reference_characters": 2331,
        "rate": 0.0682110682110682
      },
      "raw_cer": null,
      "terms": {
        "correct": 55,
        "total": 67,
        "accuracy": 0.8208955223880597,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 1,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 1,
        "manifest_count": 98,
        "residual_rate": 0.01020408163265306
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 35,
            "substitutions": 13,
            "insertions": 10,
            "deletions": 12,
            "reference_characters": 437,
            "rate": 0.08009153318077804
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 48,
            "substitutions": 24,
            "insertions": 16,
            "deletions": 8,
            "reference_characters": 512,
            "rate": 0.09375
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 57,
            "substitutions": 34,
            "insertions": 10,
            "deletions": 13,
            "reference_characters": 653,
            "rate": 0.08728943338437979
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 6,
            "substitutions": 0,
            "insertions": 1,
            "deletions": 5,
            "reference_characters": 372,
            "rate": 0.016129032258064516
          },
          "exact_matches": 6,
          "exact_match_rate": 0.75,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 36,
            "substitutions": 16,
            "insertions": 13,
            "deletions": 7,
            "reference_characters": 391,
            "rate": 0.09207161125319693
          },
          "exact_matches": 2,
          "exact_match_rate": 0.25,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.5930207705823705,
          "p90_s": 0.8808785087778234
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.2501999579835683,
            "p90_s": 0.2501999579835683
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.5712226879550144,
            "p90_s": 0.7700666878954507
          },
          ">15s": {
            "count": 13,
            "median_s": 0.8542086670640856,
            "p90_s": 0.995716124237515
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 50,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/v2gloss/e2e-v2-t16-s75+sft2-qwen-fmtv1.jsonl",
      "system": "v2-t16-s75+sft2-qwen-fmtv1",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 156,
        "substitutions": 67,
        "insertions": 35,
        "deletions": 54,
        "reference_characters": 2331,
        "rate": 0.06692406692406692
      },
      "raw_cer": null,
      "terms": {
        "correct": 56,
        "total": 67,
        "accuracy": 0.835820895522388,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 1,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 0,
        "manifest_count": 98,
        "residual_rate": 0.0
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 38,
            "substitutions": 16,
            "insertions": 6,
            "deletions": 16,
            "reference_characters": 437,
            "rate": 0.08695652173913043
          },
          "exact_matches": 2,
          "exact_match_rate": 0.2,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 34,
            "substitutions": 11,
            "insertions": 16,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.06640625
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 57,
            "substitutions": 34,
            "insertions": 10,
            "deletions": 13,
            "reference_characters": 653,
            "rate": 0.08728943338437979
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 6,
            "substitutions": 0,
            "insertions": 1,
            "deletions": 5,
            "reference_characters": 372,
            "rate": 0.016129032258064516
          },
          "exact_matches": 6,
          "exact_match_rate": 0.75,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 23,
            "substitutions": 3,
            "insertions": 14,
            "deletions": 6,
            "reference_characters": 391,
            "rate": 0.058823529411764705
          },
          "exact_matches": 3,
          "exact_match_rate": 0.375,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.590549583430402,
          "p90_s": 0.8690758247743361
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.24879983300343156,
            "p90_s": 0.24879983300343156
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.5497343334718607,
            "p90_s": 0.7638444170588627
          },
          ">15s": {
            "count": 13,
            "median_s": 0.8547690830891952,
            "p90_s": 0.9823840669589117
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 50,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/v2gloss/e2e-v2-t16-s75+sft2-qwen.jsonl",
      "system": "v2-t16-s75+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 229,
        "substitutions": 112,
        "insertions": 56,
        "deletions": 61,
        "reference_characters": 2331,
        "rate": 0.09824109824109824
      },
      "raw_cer": null,
      "terms": {
        "correct": 51,
        "total": 67,
        "accuracy": 0.7611940298507462,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 2,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 1,
        "manifest_count": 98,
        "residual_rate": 0.01020408163265306
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 47,
            "substitutions": 24,
            "insertions": 8,
            "deletions": 15,
            "reference_characters": 437,
            "rate": 0.10755148741418764
          },
          "exact_matches": 2,
          "exact_match_rate": 0.2,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 54,
            "substitutions": 33,
            "insertions": 15,
            "deletions": 6,
            "reference_characters": 512,
            "rate": 0.10546875
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 57,
            "substitutions": 34,
            "insertions": 10,
            "deletions": 13,
            "reference_characters": 653,
            "rate": 0.08728943338437979
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 6,
            "substitutions": 0,
            "insertions": 1,
            "deletions": 5,
            "reference_characters": 372,
            "rate": 0.016129032258064516
          },
          "exact_matches": 6,
          "exact_match_rate": 0.75,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 67,
            "substitutions": 22,
            "insertions": 23,
            "deletions": 22,
            "reference_characters": 391,
            "rate": 0.17135549872122763
          },
          "exact_matches": 2,
          "exact_match_rate": 0.25,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.7723456874955446,
          "p90_s": 1.1599973964388481
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.32687895803246647,
            "p90_s": 0.32687895803246647
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.7438321039662696,
            "p90_s": 0.9549766869167797
          },
          ">15s": {
            "count": 13,
            "median_s": 1.0702998749911785,
            "p90_s": 1.2419040754437447
          }
        },
        "unknown_duration_rows": 0,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 50,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    }
  ]
}
```
