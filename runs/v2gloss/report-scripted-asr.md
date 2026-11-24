| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1-t16-s75 | asr | 50/50 | 412/2953 (13.95%; 置換 224、挿入 25、削除 163) | 380/2876 (13.21%; 置換 222、挿入 23、削除 135) | 44/67 (65.67%) | 45/67 (67.16%) | 0 | 80/98 (81.63%) | 0.230 / 0.337 | 0 | 0.056 / 0.056 | 0.199 / 0.272 | 0.334 / 0.431 |
| v2-t16-s75 | asr | 50/50 | 433/2953 (14.66%; 置換 243、挿入 29、削除 161) | 450/2876 (15.65%; 置換 291、挿入 23、削除 136) | 41/67 (61.19%) | 42/67 (62.69%) | 0 | 80/98 (81.63%) | 0.401 / 0.624 | 0 | 0.140 / 0.140 | 0.365 / 0.475 | 0.595 / 0.680 |
| v2-t8-s75 | asr | 50/50 | 410/2953 (13.88%; 置換 223、挿入 25、削除 162) | 445/2876 (15.47%; 置換 282、挿入 19、削除 144) | 38/67 (56.72%) | 40/67 (59.70%) | 0 | 80/98 (81.63%) | 0.390 / 0.655 | 0 | 0.138 / 0.138 | 0.373 / 0.481 | 0.589 / 0.699 |
| v2-t16-s90 | asr | 50/50 | 424/2953 (14.36%; 置換 237、挿入 24、削除 163) | 468/2876 (16.27%; 置換 301、挿入 22、削除 145) | 40/67 (59.70%) | 41/67 (61.19%) | 0 | 80/98 (81.63%) | 0.387 / 0.579 | 0 | 0.143 / 0.143 | 0.369 / 0.474 | 0.567 / 0.673 |
| v2-t8-s90 | asr | 50/50 | 399/2953 (13.51%; 置換 215、挿入 21、削除 163) | 454/2876 (15.79%; 置換 286、挿入 19、削除 149) | 38/67 (56.72%) | 40/67 (59.70%) | 0 | 80/98 (81.63%) | 0.390 / 0.575 | 0 | 0.128 / 0.128 | 0.372 / 0.472 | 0.562 / 0.680 |
| v2-t16-s100 | asr | 50/50 | 424/2953 (14.36%; 置換 237、挿入 24、削除 163) | 468/2876 (16.27%; 置換 301、挿入 22、削除 145) | 40/67 (59.70%) | 41/67 (61.19%) | 0 | 80/98 (81.63%) | 0.406 / 0.680 | 0 | 0.129 / 0.129 | 0.384 / 0.525 | 0.585 / 0.710 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| v1-t16-s75 | asr | english_phrase | 10/10 | 175/437 (40.05%; 置換 78、挿入 84、削除 13) | 0/10 (0.00%) | — |
| v1-t16-s75 | asr | instruction_like | 11/11 | 192/512 (37.50%; 置換 53、挿入 132、削除 7) | 1/11 (9.09%) | 1 |
| v1-t16-s75 | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| v1-t16-s75 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| v1-t16-s75 | asr | self_correction | 8/8 | 230/391 (58.82%; 置換 36、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| v2-t16-s75 | asr | english_phrase | 10/10 | 192/437 (43.94%; 置換 93、挿入 85、削除 14) | 0/10 (0.00%) | — |
| v2-t16-s75 | asr | instruction_like | 11/11 | 200/512 (39.06%; 置換 63、挿入 130、削除 7) | 1/11 (9.09%) | 1 |
| v2-t16-s75 | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| v2-t16-s75 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| v2-t16-s75 | asr | self_correction | 8/8 | 251/391 (64.19%; 置換 57、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| v2-t8-s75 | asr | english_phrase | 10/10 | 186/437 (42.56%; 置換 92、挿入 80、削除 14) | 0/10 (0.00%) | — |
| v2-t8-s75 | asr | instruction_like | 11/11 | 200/512 (39.06%; 置換 63、挿入 130、削除 7) | 1/11 (9.09%) | 1 |
| v2-t8-s75 | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| v2-t8-s75 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| v2-t8-s75 | asr | self_correction | 8/8 | 262/391 (67.01%; 置換 64、挿入 191、削除 7) | 0/8 (0.00%)（言い直しの正答率） | — |
| v2-t16-s90 | asr | english_phrase | 10/10 | 197/437 (45.08%; 置換 103、挿入 80、削除 14) | 0/10 (0.00%) | — |
| v2-t16-s90 | asr | instruction_like | 11/11 | 200/512 (39.06%; 置換 63、挿入 130、削除 7) | 1/11 (9.09%) | 1 |
| v2-t16-s90 | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| v2-t16-s90 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| v2-t16-s90 | asr | self_correction | 8/8 | 255/391 (65.22%; 置換 66、挿入 186、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| v2-t8-s90 | asr | english_phrase | 10/10 | 186/437 (42.56%; 置換 92、挿入 80、削除 14) | 0/10 (0.00%) | — |
| v2-t8-s90 | asr | instruction_like | 11/11 | 200/512 (39.06%; 置換 63、挿入 130、削除 7) | 1/11 (9.09%) | 1 |
| v2-t8-s90 | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| v2-t8-s90 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| v2-t8-s90 | asr | self_correction | 8/8 | 266/391 (68.03%; 置換 73、挿入 186、削除 7) | 0/8 (0.00%)（言い直しの正答率） | — |
| v2-t16-s100 | asr | english_phrase | 10/10 | 197/437 (45.08%; 置換 103、挿入 80、削除 14) | 0/10 (0.00%) | — |
| v2-t16-s100 | asr | instruction_like | 11/11 | 200/512 (39.06%; 置換 63、挿入 130、削除 7) | 1/11 (9.09%) | 1 |
| v2-t16-s100 | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| v2-t16-s100 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| v2-t16-s100 | asr | self_correction | 8/8 | 255/391 (65.22%; 置換 66、挿入 186、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/metal-v2gloss/devuser-scripted.jsonl",
  "results": [
    {
      "run": "runs/v2gloss/asr-v1-t16-s75.jsonl",
      "system": "v1-t16-s75",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 412,
        "substitutions": 224,
        "insertions": 25,
        "deletions": 163,
        "reference_characters": 2953,
        "rate": 0.1395191330849983
      },
      "raw_cer": {
        "edit_errors": 380,
        "substitutions": 222,
        "insertions": 23,
        "deletions": 135,
        "reference_characters": 2876,
        "rate": 0.13212795549374132
      },
      "terms": {
        "correct": 44,
        "total": 67,
        "accuracy": 0.6567164179104478,
        "loose_correct": 45,
        "loose_accuracy": 0.6716417910447762
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 80,
        "manifest_count": 98,
        "residual_rate": 0.8163265306122449
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 175,
            "substitutions": 78,
            "insertions": 84,
            "deletions": 13,
            "reference_characters": 437,
            "rate": 0.40045766590389015
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 192,
            "substitutions": 53,
            "insertions": 132,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.375
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 175,
            "substitutions": 61,
            "insertions": 111,
            "deletions": 3,
            "reference_characters": 653,
            "rate": 0.2679938744257274
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 10,
            "substitutions": 2,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.026881720430107527
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 230,
            "substitutions": 36,
            "insertions": 191,
            "deletions": 3,
            "reference_characters": 391,
            "rate": 0.5882352941176471
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.23044756246963516,
          "p90_s": 0.33665632498450576
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.05553154204972088,
            "p90_s": 0.05553154204972088
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.19922164554009214,
            "p90_s": 0.27228868746897206
          },
          ">15s": {
            "count": 13,
            "median_s": 0.333643416990526,
            "p90_s": 0.4310699999565259
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
      "run": "runs/v2gloss/asr-v2-t16-s75.jsonl",
      "system": "v2-t16-s75",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 433,
        "substitutions": 243,
        "insertions": 29,
        "deletions": 161,
        "reference_characters": 2953,
        "rate": 0.1466305452082628
      },
      "raw_cer": {
        "edit_errors": 450,
        "substitutions": 291,
        "insertions": 23,
        "deletions": 136,
        "reference_characters": 2876,
        "rate": 0.1564673157162726
      },
      "terms": {
        "correct": 41,
        "total": 67,
        "accuracy": 0.6119402985074627,
        "loose_correct": 42,
        "loose_accuracy": 0.6268656716417911
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 80,
        "manifest_count": 98,
        "residual_rate": 0.8163265306122449
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 192,
            "substitutions": 93,
            "insertions": 85,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.43935926773455375
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 200,
            "substitutions": 63,
            "insertions": 130,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.390625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 175,
            "substitutions": 61,
            "insertions": 111,
            "deletions": 3,
            "reference_characters": 653,
            "rate": 0.2679938744257274
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 10,
            "substitutions": 2,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.026881720430107527
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 251,
            "substitutions": 57,
            "insertions": 191,
            "deletions": 3,
            "reference_characters": 391,
            "rate": 0.6419437340153452
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.4013608540408313,
          "p90_s": 0.624366366956383
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.13961808301974088,
            "p90_s": 0.13961808301974088
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.36509700008900836,
            "p90_s": 0.47460106248036027
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5946170419920236,
            "p90_s": 0.6802875334396958
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
      "run": "runs/v2gloss/asr-v2-t8-s75.jsonl",
      "system": "v2-t8-s75",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 410,
        "substitutions": 223,
        "insertions": 25,
        "deletions": 162,
        "reference_characters": 2953,
        "rate": 0.1388418557399255
      },
      "raw_cer": {
        "edit_errors": 445,
        "substitutions": 282,
        "insertions": 19,
        "deletions": 144,
        "reference_characters": 2876,
        "rate": 0.1547287899860918
      },
      "terms": {
        "correct": 38,
        "total": 67,
        "accuracy": 0.5671641791044776,
        "loose_correct": 40,
        "loose_accuracy": 0.5970149253731343
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 80,
        "manifest_count": 98,
        "residual_rate": 0.8163265306122449
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 186,
            "substitutions": 92,
            "insertions": 80,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.425629290617849
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 200,
            "substitutions": 63,
            "insertions": 130,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.390625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 175,
            "substitutions": 61,
            "insertions": 111,
            "deletions": 3,
            "reference_characters": 653,
            "rate": 0.2679938744257274
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 10,
            "substitutions": 2,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.026881720430107527
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 262,
            "substitutions": 64,
            "insertions": 191,
            "deletions": 7,
            "reference_characters": 391,
            "rate": 0.670076726342711
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.3903036040137522,
          "p90_s": 0.6552169797592796
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.13802866591140628,
            "p90_s": 0.13802866591140628
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.37311195849906653,
            "p90_s": 0.4805788745288737
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5894785840064287,
            "p90_s": 0.699246150162071
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
      "run": "runs/v2gloss/asr-v2-t16-s90.jsonl",
      "system": "v2-t16-s90",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 424,
        "substitutions": 237,
        "insertions": 24,
        "deletions": 163,
        "reference_characters": 2953,
        "rate": 0.14358279715543515
      },
      "raw_cer": {
        "edit_errors": 468,
        "substitutions": 301,
        "insertions": 22,
        "deletions": 145,
        "reference_characters": 2876,
        "rate": 0.1627260083449235
      },
      "terms": {
        "correct": 40,
        "total": 67,
        "accuracy": 0.5970149253731343,
        "loose_correct": 41,
        "loose_accuracy": 0.6119402985074627
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 80,
        "manifest_count": 98,
        "residual_rate": 0.8163265306122449
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 197,
            "substitutions": 103,
            "insertions": 80,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.45080091533180777
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 200,
            "substitutions": 63,
            "insertions": 130,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.390625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 175,
            "substitutions": 61,
            "insertions": 111,
            "deletions": 3,
            "reference_characters": 653,
            "rate": 0.2679938744257274
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 10,
            "substitutions": 2,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.026881720430107527
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 255,
            "substitutions": 66,
            "insertions": 186,
            "deletions": 3,
            "reference_characters": 391,
            "rate": 0.6521739130434783
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.3871169374906458,
          "p90_s": 0.5794951707241126
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.14333458291366696,
            "p90_s": 0.14333458291366696
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.36891108349664137,
            "p90_s": 0.47428268752992153
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5665681660175323,
            "p90_s": 0.6730782253900542
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
      "run": "runs/v2gloss/asr-v2-t8-s90.jsonl",
      "system": "v2-t8-s90",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 399,
        "substitutions": 215,
        "insertions": 21,
        "deletions": 163,
        "reference_characters": 2953,
        "rate": 0.13511683034202507
      },
      "raw_cer": {
        "edit_errors": 454,
        "substitutions": 286,
        "insertions": 19,
        "deletions": 149,
        "reference_characters": 2876,
        "rate": 0.15785813630041726
      },
      "terms": {
        "correct": 38,
        "total": 67,
        "accuracy": 0.5671641791044776,
        "loose_correct": 40,
        "loose_accuracy": 0.5970149253731343
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 80,
        "manifest_count": 98,
        "residual_rate": 0.8163265306122449
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 186,
            "substitutions": 92,
            "insertions": 80,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.425629290617849
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 200,
            "substitutions": 63,
            "insertions": 130,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.390625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 175,
            "substitutions": 61,
            "insertions": 111,
            "deletions": 3,
            "reference_characters": 653,
            "rate": 0.2679938744257274
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 10,
            "substitutions": 2,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.026881720430107527
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 266,
            "substitutions": 73,
            "insertions": 186,
            "deletions": 7,
            "reference_characters": 391,
            "rate": 0.680306905370844
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.3899058335227892,
          "p90_s": 0.5746385756297969
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.12828258401714265,
            "p90_s": 0.12828258401714265
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3717926669633016,
            "p90_s": 0.4724041250301525
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5619261249667034,
            "p90_s": 0.6796054160222411
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
      "run": "runs/v2gloss/asr-v2-t16-s100.jsonl",
      "system": "v2-t16-s100",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 424,
        "substitutions": 237,
        "insertions": 24,
        "deletions": 163,
        "reference_characters": 2953,
        "rate": 0.14358279715543515
      },
      "raw_cer": {
        "edit_errors": 468,
        "substitutions": 301,
        "insertions": 22,
        "deletions": 145,
        "reference_characters": 2876,
        "rate": 0.1627260083449235
      },
      "terms": {
        "correct": 40,
        "total": 67,
        "accuracy": 0.5970149253731343,
        "loose_correct": 41,
        "loose_accuracy": 0.6119402985074627
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 80,
        "manifest_count": 98,
        "residual_rate": 0.8163265306122449
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 197,
            "substitutions": 103,
            "insertions": 80,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.45080091533180777
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 200,
            "substitutions": 63,
            "insertions": 130,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.390625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 175,
            "substitutions": 61,
            "insertions": 111,
            "deletions": 3,
            "reference_characters": 653,
            "rate": 0.2679938744257274
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 10,
            "substitutions": 2,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.026881720430107527
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 255,
            "substitutions": 66,
            "insertions": 186,
            "deletions": 3,
            "reference_characters": 391,
            "rate": 0.6521739130434783
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.40608120849356055,
          "p90_s": 0.6799775414285251
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.12852604198269546,
            "p90_s": 0.12852604198269546
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3840721669839695,
            "p90_s": 0.5252452500280924
          },
          ">15s": {
            "count": 13,
            "median_s": 0.584858666989021,
            "p90_s": 0.7101936914492398
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
