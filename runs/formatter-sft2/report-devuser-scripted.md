| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 50/50 | 722/2331 (30.97%; 置換 223、挿入 466、削除 33) | — | 44/67 (65.67%) | — | 14 | 80/98 (81.63%) | 0.227 / 0.329 | 0 | 0.056 / 0.056 | 0.205 / 0.271 | 0.326 / 0.419 |
| haas2p+sft1-qwen | e2e | 50/50 | 204/2331 (8.75%; 置換 82、挿入 75、削除 47) | — | 52/67 (77.61%) | — | 1 | 1/98 (1.02%) | 0.482 / 0.710 | 0 | 0.203 / 0.203 | 0.407 / 0.624 | 0.641 / 0.805 |
| haas2p+sft2-qwen | e2e | 50/50 | 171/2331 (7.34%; 置換 59、挿入 67、削除 45) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.435 / 0.626 | 0 | 0.168 / 0.168 | 0.366 / 0.556 | 0.582 / 0.726 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | english_phrase | 10/10 | 175/437 (40.05%; 置換 78、挿入 84、削除 13) | 0/10 (0.00%) | — |
| haas2p(no-format) | e2e | instruction_like | 11/11 | 192/512 (37.50%; 置換 53、挿入 132、削除 7) | 1/11 (9.09%) | 1 |
| haas2p(no-format) | e2e | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| haas2p(no-format) | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p(no-format) | e2e | self_correction | 8/8 | 230/391 (58.82%; 置換 36、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas2p+sft1-qwen | e2e | english_phrase | 10/10 | 30/437 (6.86%; 置換 15、挿入 7、削除 8) | 1/10 (10.00%) | — |
| haas2p+sft1-qwen | e2e | instruction_like | 11/11 | 42/512 (8.20%; 置換 11、挿入 24、削除 7) | 2/11 (18.18%) | 0 |
| haas2p+sft1-qwen | e2e | list | 11/11 | 81/653 (12.40%; 置換 39、挿入 31、削除 11) | 3/11 (27.27%) | — |
| haas2p+sft1-qwen | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p+sft1-qwen | e2e | self_correction | 8/8 | 38/391 (9.72%; 置換 4、挿入 23、削除 11) | 1/8 (12.50%)（言い直しの正答率） | — |
| haas2p+sft2-qwen | e2e | english_phrase | 10/10 | 33/437 (7.55%; 置換 13、挿入 8、削除 12) | 3/10 (30.00%) | — |
| haas2p+sft2-qwen | e2e | instruction_like | 11/11 | 39/512 (7.62%; 置換 11、挿入 21、削除 7) | 2/11 (18.18%) | 0 |
| haas2p+sft2-qwen | e2e | list | 11/11 | 81/653 (12.40%; 置換 34、挿入 34、削除 13) | 3/11 (27.27%) | — |
| haas2p+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| haas2p+sft2-qwen | e2e | self_correction | 8/8 | 27/391 (6.91%; 置換 3、挿入 18、削除 6) | 2/8 (25.00%)（言い直しの正答率） | — |

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
      "run": "runs/formatter-sft2/devuser-haas2p+sft1-qwen.jsonl",
      "system": "haas2p+sft1-qwen",
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
          "median_s": 0.4817496044561267,
          "p90_s": 0.7097305749775842
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.20316904201172292,
            "p90_s": 0.20316904201172292
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.4072832295205444,
            "p90_s": 0.6237052494543605
          },
          ">15s": {
            "count": 13,
            "median_s": 0.6413379999576136,
            "p90_s": 0.8048261674121022
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
      "run": "runs/formatter-sft2/devuser-haas2p+sft2-qwen.jsonl",
      "system": "haas2p+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 171,
        "substitutions": 59,
        "insertions": 67,
        "deletions": 45,
        "reference_characters": 2331,
        "rate": 0.07335907335907337
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
            "edit_errors": 81,
            "substitutions": 34,
            "insertions": 34,
            "deletions": 13,
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
          "median_s": 0.4349756874726154,
          "p90_s": 0.6258876876323485
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.16791395901236683,
            "p90_s": 0.16791395901236683
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.36596550000831485,
            "p90_s": 0.5555379579309374
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5816850000992417,
            "p90_s": 0.7262065087677911
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
