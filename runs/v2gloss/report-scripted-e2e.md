| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1-t16-s75+sft2-qwen | e2e | 50/50 | 147/2331 (6.31%; 置換 59、挿入 43、削除 45) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.439 / 0.610 | 0 | 0.166 / 0.166 | 0.372 / 0.562 | 0.597 / 0.729 |
| v2-t16-s75+sft2-qwen | e2e | 50/50 | 229/2331 (9.82%; 置換 112、挿入 56、削除 61) | — | 51/67 (76.12%) | — | 2 | 1/98 (1.02%) | 0.772 / 1.160 | 0 | 0.327 / 0.327 | 0.744 / 0.955 | 1.070 / 1.242 |
| v2-t8-s75+sft2-qwen | e2e | 50/50 | 198/2331 (8.49%; 置換 85、挿入 53、削除 60) | — | 51/67 (76.12%) | — | 2 | 1/98 (1.02%) | 0.831 / 1.218 | 0 | 0.388 / 0.388 | 0.761 / 1.030 | 1.162 / 1.497 |
| v2-t16-s90+sft2-qwen | e2e | 50/50 | 211/2331 (9.05%; 置換 107、挿入 43、削除 61) | — | 52/67 (77.61%) | — | 2 | 1/98 (1.02%) | 0.800 / 1.198 | 0 | 0.330 / 0.330 | 0.770 / 1.028 | 1.128 / 1.299 |
| v2-t8-s90+sft2-qwen | e2e | 50/50 | 180/2331 (7.72%; 置換 82、挿入 40、削除 58) | — | 52/67 (77.61%) | — | 2 | 1/98 (1.02%) | 0.762 / 1.166 | 0 | 0.314 / 0.314 | 0.721 / 0.959 | 1.064 / 1.208 |
| v2-t16-s100+sft2-qwen | e2e | 50/50 | 211/2331 (9.05%; 置換 107、挿入 43、削除 61) | — | 52/67 (77.61%) | — | 2 | 1/98 (1.02%) | 0.800 / 1.228 | 0 | 0.315 / 0.315 | 0.743 / 1.099 | 1.183 / 1.356 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| v1-t16-s75+sft2-qwen | e2e | english_phrase | 10/10 | 33/437 (7.55%; 置換 13、挿入 8、削除 12) | 3/10 (30.00%) | — |
| v1-t16-s75+sft2-qwen | e2e | instruction_like | 11/11 | 39/512 (7.62%; 置換 11、挿入 21、削除 7) | 2/11 (18.18%) | 0 |
| v1-t16-s75+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v1-t16-s75+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v1-t16-s75+sft2-qwen | e2e | self_correction | 8/8 | 27/391 (6.91%; 置換 3、挿入 18、削除 6) | 2/8 (25.00%)（言い直しの正答率） | — |
| v2-t16-s75+sft2-qwen | e2e | english_phrase | 10/10 | 47/437 (10.76%; 置換 24、挿入 8、削除 15) | 2/10 (20.00%) | — |
| v2-t16-s75+sft2-qwen | e2e | instruction_like | 11/11 | 54/512 (10.55%; 置換 33、挿入 15、削除 6) | 2/11 (18.18%) | 0 |
| v2-t16-s75+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t16-s75+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t16-s75+sft2-qwen | e2e | self_correction | 8/8 | 67/391 (17.14%; 置換 22、挿入 23、削除 22) | 2/8 (25.00%)（言い直しの正答率） | — |
| v2-t8-s75+sft2-qwen | e2e | english_phrase | 10/10 | 30/437 (6.86%; 置換 8、挿入 8、削除 14) | 3/10 (30.00%) | — |
| v2-t8-s75+sft2-qwen | e2e | instruction_like | 11/11 | 54/512 (10.55%; 置換 33、挿入 15、削除 6) | 2/11 (18.18%) | 0 |
| v2-t8-s75+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t8-s75+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t8-s75+sft2-qwen | e2e | self_correction | 8/8 | 67/391 (17.14%; 置換 22、挿入 23、削除 22) | 2/8 (25.00%)（言い直しの正答率） | — |
| v2-t16-s90+sft2-qwen | e2e | english_phrase | 10/10 | 47/437 (10.76%; 置換 22、挿入 8、削除 17) | 2/10 (20.00%) | — |
| v2-t16-s90+sft2-qwen | e2e | instruction_like | 11/11 | 54/512 (10.55%; 置換 33、挿入 15、削除 6) | 2/11 (18.18%) | 0 |
| v2-t16-s90+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t16-s90+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t16-s90+sft2-qwen | e2e | self_correction | 8/8 | 49/391 (12.53%; 置換 19、挿入 10、削除 20) | 3/8 (37.50%)（言い直しの正答率） | — |
| v2-t8-s90+sft2-qwen | e2e | english_phrase | 10/10 | 30/437 (6.86%; 置換 8、挿入 8、削除 14) | 3/10 (30.00%) | — |
| v2-t8-s90+sft2-qwen | e2e | instruction_like | 11/11 | 54/512 (10.55%; 置換 33、挿入 15、削除 6) | 2/11 (18.18%) | 0 |
| v2-t8-s90+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t8-s90+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t8-s90+sft2-qwen | e2e | self_correction | 8/8 | 49/391 (12.53%; 置換 19、挿入 10、削除 20) | 3/8 (37.50%)（言い直しの正答率） | — |
| v2-t16-s100+sft2-qwen | e2e | english_phrase | 10/10 | 47/437 (10.76%; 置換 22、挿入 8、削除 17) | 2/10 (20.00%) | — |
| v2-t16-s100+sft2-qwen | e2e | instruction_like | 11/11 | 54/512 (10.55%; 置換 33、挿入 15、削除 6) | 2/11 (18.18%) | 0 |
| v2-t16-s100+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| v2-t16-s100+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| v2-t16-s100+sft2-qwen | e2e | self_correction | 8/8 | 49/391 (12.53%; 置換 19、挿入 10、削除 20) | 3/8 (37.50%)（言い直しの正答率） | — |

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
    },
    {
      "run": "runs/v2gloss/e2e-v2-t8-s75+sft2-qwen.jsonl",
      "system": "v2-t8-s75+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 198,
        "substitutions": 85,
        "insertions": 53,
        "deletions": 60,
        "reference_characters": 2331,
        "rate": 0.08494208494208494
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
            "edit_errors": 30,
            "substitutions": 8,
            "insertions": 8,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.06864988558352403
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
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
          "median_s": 0.8309725205181167,
          "p90_s": 1.217696274619084
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.38819129089824855,
            "p90_s": 0.38819129089824855
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.7613268540007994,
            "p90_s": 1.0303574164863676
          },
          ">15s": {
            "count": 13,
            "median_s": 1.161511291982606,
            "p90_s": 1.4967731002951041
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
      "run": "runs/v2gloss/e2e-v2-t16-s90+sft2-qwen.jsonl",
      "system": "v2-t16-s90+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 211,
        "substitutions": 107,
        "insertions": 43,
        "deletions": 61,
        "reference_characters": 2331,
        "rate": 0.09051909051909052
      },
      "raw_cer": null,
      "terms": {
        "correct": 52,
        "total": 67,
        "accuracy": 0.7761194029850746,
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
            "substitutions": 22,
            "insertions": 8,
            "deletions": 17,
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
            "edit_errors": 49,
            "substitutions": 19,
            "insertions": 10,
            "deletions": 20,
            "reference_characters": 391,
            "rate": 0.12531969309462915
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
          "median_s": 0.800245916005224,
          "p90_s": 1.1976114334422163
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.3295097079826519,
            "p90_s": 0.3295097079826519
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.7699660834623501,
            "p90_s": 1.027725646039471
          },
          ">15s": {
            "count": 13,
            "median_s": 1.1284406259655952,
            "p90_s": 1.2987914165947587
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
      "run": "runs/v2gloss/e2e-v2-t8-s90+sft2-qwen.jsonl",
      "system": "v2-t8-s90+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 180,
        "substitutions": 82,
        "insertions": 40,
        "deletions": 58,
        "reference_characters": 2331,
        "rate": 0.07722007722007722
      },
      "raw_cer": null,
      "terms": {
        "correct": 52,
        "total": 67,
        "accuracy": 0.7761194029850746,
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
            "edit_errors": 30,
            "substitutions": 8,
            "insertions": 8,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.06864988558352403
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
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
            "edit_errors": 49,
            "substitutions": 19,
            "insertions": 10,
            "deletions": 20,
            "reference_characters": 391,
            "rate": 0.12531969309462915
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
          "median_s": 0.7616793130291626,
          "p90_s": 1.1655114789842629
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.3135964999673888,
            "p90_s": 0.3135964999673888
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.7210625214502215,
            "p90_s": 0.9591440000222065
          },
          ">15s": {
            "count": 13,
            "median_s": 1.0644365419866517,
            "p90_s": 1.2076943578664214
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
      "run": "runs/v2gloss/e2e-v2-t16-s100+sft2-qwen.jsonl",
      "system": "v2-t16-s100+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 211,
        "substitutions": 107,
        "insertions": 43,
        "deletions": 61,
        "reference_characters": 2331,
        "rate": 0.09051909051909052
      },
      "raw_cer": null,
      "terms": {
        "correct": 52,
        "total": 67,
        "accuracy": 0.7761194029850746,
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
            "substitutions": 22,
            "insertions": 8,
            "deletions": 17,
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
            "edit_errors": 49,
            "substitutions": 19,
            "insertions": 10,
            "deletions": 20,
            "reference_characters": 391,
            "rate": 0.12531969309462915
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
          "median_s": 0.8001627919729799,
          "p90_s": 1.2282803455600515
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.31479687604587525,
            "p90_s": 0.31479687604587525
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.7432528540375642,
            "p90_s": 1.0994947709841654
          },
          ">15s": {
            "count": 13,
            "median_s": 1.182904624962248,
            "p90_s": 1.355622450169176
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
