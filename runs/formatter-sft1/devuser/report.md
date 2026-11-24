| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 50/50 | 722/2331 (30.97%; 置換 223、挿入 466、削除 33) | — | 44/67 (65.67%) | — | 14 | 80/98 (81.63%) | 0.227 / 0.329 | 0 | 0.056 / 0.056 | 0.205 / 0.271 | 0.326 / 0.419 |
| haas2p+sft1-qwen3.5-0.8b-full | e2e | 50/50 | 204/2331 (8.75%; 置換 82、挿入 75、削除 47) | — | 52/67 (77.61%) | — | 1 | 1/98 (1.02%) | 0.463 / 0.709 | 0 | 0.184 / 0.184 | 0.401 / 0.593 | 0.613 / 0.772 |
| haas2p+sft1-lfm2.5-1.2b-jp-full | e2e | 50/50 | 215/2331 (9.22%; 置換 94、挿入 64、削除 57) | — | 50/67 (74.63%) | — | 2 | 0/98 (0.00%) | 0.567 / 0.815 | 0 | 0.206 / 0.206 | 0.463 / 0.709 | 0.765 / 0.945 |
| haas2p+sft1-gemma-4-e2b-lora | e2e | 50/50 | 219/2331 (9.40%; 置換 68、挿入 42、削除 109) | — | 54/67 (80.60%) | — | 1 | 0/98 (0.00%) | 0.648 / 0.990 | 0 | 0.321 / 0.321 | 0.532 / 0.876 | 0.903 / 1.049 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | english_phrase | 10/10 | 175/437 (40.05%; 置換 78、挿入 84、削除 13) | 0/10 (0.00%) | — |
| haas2p(no-format) | e2e | instruction_like | 11/11 | 192/512 (37.50%; 置換 53、挿入 132、削除 7) | 1/11 (9.09%) | 1 |
| haas2p(no-format) | e2e | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| haas2p(no-format) | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p(no-format) | e2e | self_correction | 8/8 | 230/391 (58.82%; 置換 36、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas2p+sft1-qwen3.5-0.8b-full | e2e | english_phrase | 10/10 | 30/437 (6.86%; 置換 15、挿入 7、削除 8) | 1/10 (10.00%) | — |
| haas2p+sft1-qwen3.5-0.8b-full | e2e | instruction_like | 11/11 | 42/512 (8.20%; 置換 11、挿入 24、削除 7) | 2/11 (18.18%) | 0 |
| haas2p+sft1-qwen3.5-0.8b-full | e2e | list | 11/11 | 81/653 (12.40%; 置換 39、挿入 31、削除 11) | 3/11 (27.27%) | — |
| haas2p+sft1-qwen3.5-0.8b-full | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p+sft1-qwen3.5-0.8b-full | e2e | self_correction | 8/8 | 38/391 (9.72%; 置換 4、挿入 23、削除 11) | 1/8 (12.50%)（言い直しの正答率） | — |
| haas2p+sft1-lfm2.5-1.2b-jp-full | e2e | english_phrase | 10/10 | 24/437 (5.49%; 置換 11、挿入 6、削除 7) | 4/10 (40.00%) | — |
| haas2p+sft1-lfm2.5-1.2b-jp-full | e2e | instruction_like | 11/11 | 52/512 (10.16%; 置換 22、挿入 18、削除 12) | 1/11 (9.09%) | 0 |
| haas2p+sft1-lfm2.5-1.2b-jp-full | e2e | list | 11/11 | 67/653 (10.26%; 置換 36、挿入 12、削除 19) | 4/11 (36.36%) | — |
| haas2p+sft1-lfm2.5-1.2b-jp-full | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p+sft1-lfm2.5-1.2b-jp-full | e2e | self_correction | 8/8 | 72/391 (18.41%; 置換 25、挿入 35、削除 12) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas2p+sft1-gemma-4-e2b-lora | e2e | english_phrase | 10/10 | 40/437 (9.15%; 置換 16、挿入 5、削除 19) | 3/10 (30.00%) | — |
| haas2p+sft1-gemma-4-e2b-lora | e2e | instruction_like | 11/11 | 67/512 (13.09%; 置換 9、挿入 20、削除 38) | 2/11 (18.18%) | 0 |
| haas2p+sft1-gemma-4-e2b-lora | e2e | list | 11/11 | 71/653 (10.87%; 置換 32、挿入 3、削除 36) | 3/11 (27.27%) | — |
| haas2p+sft1-gemma-4-e2b-lora | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p+sft1-gemma-4-e2b-lora | e2e | self_correction | 8/8 | 56/391 (14.32%; 置換 7、挿入 17、削除 32) | 2/8 (25.00%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-scripted.jsonl",
  "results": [
    {
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-e2e/raw.jsonl",
      "system": "haas2p(no-format)",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 722,
        "substitutions": 223,
        "insertions": 466,
        "deletions": 33,
        "reference_characters": 2331,
        "rate": 0.30973830973830974
      },
      "raw_cer": null,
      "terms": {
        "correct": 44,
        "total": 67,
        "accuracy": 0.6567164179104478,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 14,
        "basis": "target_textのterms"
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
          "median_s": 0.22737404145300388,
          "p90_s": 0.32934632080141457
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.05593608401250094,
            "p90_s": 0.05593608401250094
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.20455439650686458,
            "p90_s": 0.2711112709948793
          },
          ">15s": {
            "count": 13,
            "median_s": 0.32560966606251895,
            "p90_s": 0.41871720820199704
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
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft1/devuser/sft1-qwen3.5-0.8b-full.jsonl",
      "system": "haas2p+sft1-qwen3.5-0.8b-full",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 204,
        "substitutions": 82,
        "insertions": 75,
        "deletions": 47,
        "reference_characters": 2331,
        "rate": 0.08751608751608751
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
            "edit_errors": 30,
            "substitutions": 15,
            "insertions": 7,
            "deletions": 8,
            "reference_characters": 437,
            "rate": 0.06864988558352403
          },
          "exact_matches": 1,
          "exact_match_rate": 0.1,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 42,
            "substitutions": 11,
            "insertions": 24,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.08203125
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 81,
            "substitutions": 39,
            "insertions": 31,
            "deletions": 11,
            "reference_characters": 653,
            "rate": 0.12404287901990811
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
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
            "edit_errors": 38,
            "substitutions": 4,
            "insertions": 23,
            "deletions": 11,
            "reference_characters": 391,
            "rate": 0.09718670076726342
          },
          "exact_matches": 1,
          "exact_match_rate": 0.125,
          "suspected_responses": null,
          "manifest_count": 8
        }
      },
      "latency": {
        "all": {
          "count": 50,
          "median_s": 0.46313581260619685,
          "p90_s": 0.7093061959254555
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.18358262605033815,
            "p90_s": 0.18358262605033815
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.40072389552369714,
            "p90_s": 0.5927180414437316
          },
          ">15s": {
            "count": 13,
            "median_s": 0.6133329579606652,
            "p90_s": 0.7720025750109926
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
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft1/devuser/sft1-lfm2.5-1.2b-jp-full.jsonl",
      "system": "haas2p+sft1-lfm2.5-1.2b-jp-full",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 215,
        "substitutions": 94,
        "insertions": 64,
        "deletions": 57,
        "reference_characters": 2331,
        "rate": 0.09223509223509224
      },
      "raw_cer": null,
      "terms": {
        "correct": 50,
        "total": 67,
        "accuracy": 0.746268656716418,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 2,
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
            "edit_errors": 24,
            "substitutions": 11,
            "insertions": 6,
            "deletions": 7,
            "reference_characters": 437,
            "rate": 0.05491990846681922
          },
          "exact_matches": 4,
          "exact_match_rate": 0.4,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 52,
            "substitutions": 22,
            "insertions": 18,
            "deletions": 12,
            "reference_characters": 512,
            "rate": 0.1015625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 67,
            "substitutions": 36,
            "insertions": 12,
            "deletions": 19,
            "reference_characters": 653,
            "rate": 0.10260336906584992
          },
          "exact_matches": 4,
          "exact_match_rate": 0.36363636363636365,
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
            "edit_errors": 72,
            "substitutions": 25,
            "insertions": 35,
            "deletions": 12,
            "reference_characters": 391,
            "rate": 0.18414322250639387
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
          "median_s": 0.5673683125060052,
          "p90_s": 0.8153340667835437
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.20605620893184096,
            "p90_s": 0.20605620893184096
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.462873479584232,
            "p90_s": 0.7087673539062962
          },
          ">15s": {
            "count": 13,
            "median_s": 0.7653624170925468,
            "p90_s": 0.9452313332352787
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
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft1/devuser/sft1-gemma-4-e2b-lora.jsonl",
      "system": "haas2p+sft1-gemma-4-e2b-lora",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 219,
        "substitutions": 68,
        "insertions": 42,
        "deletions": 109,
        "reference_characters": 2331,
        "rate": 0.09395109395109395
      },
      "raw_cer": null,
      "terms": {
        "correct": 54,
        "total": 67,
        "accuracy": 0.8059701492537313,
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
            "edit_errors": 40,
            "substitutions": 16,
            "insertions": 5,
            "deletions": 19,
            "reference_characters": 437,
            "rate": 0.09153318077803203
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 67,
            "substitutions": 9,
            "insertions": 20,
            "deletions": 38,
            "reference_characters": 512,
            "rate": 0.130859375
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 71,
            "substitutions": 32,
            "insertions": 3,
            "deletions": 36,
            "reference_characters": 653,
            "rate": 0.10872894333843798
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
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
            "edit_errors": 56,
            "substitutions": 7,
            "insertions": 17,
            "deletions": 32,
            "reference_characters": 391,
            "rate": 0.1432225063938619
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
          "median_s": 0.6481563549023122,
          "p90_s": 0.9902980675455183
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.32108470902312547,
            "p90_s": 0.32108470902312547
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.5315624165232293,
            "p90_s": 0.8756035420228727
          },
          ">15s": {
            "count": 13,
            "median_s": 0.9033602910349146,
            "p90_s": 1.0491432081907988
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
