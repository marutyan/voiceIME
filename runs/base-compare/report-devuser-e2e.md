| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 50/50 | 722/2331 (30.97%; 置換 223、挿入 466、削除 33) | — | 44/67 (65.67%) | — | 14 | 80/98 (81.63%) | 0.227 / 0.329 | 0 | 0.056 / 0.056 | 0.205 / 0.271 | 0.326 / 0.419 |
| haas2p+sft2-qwen | e2e | 50/50 | 171/2331 (7.34%; 置換 59、挿入 67、削除 45) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.435 / 0.626 | 0 | 0.168 / 0.168 | 0.366 / 0.556 | 0.582 / 0.726 |
| haas2p+sft2-qwen-rerun | e2e | 50/50 | 147/2331 (6.31%; 置換 59、挿入 43、削除 45) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.433 / 0.607 | 0 | 0.170 / 0.170 | 0.367 / 0.558 | 0.582 / 0.727 |
| haas2p-excl(no-format) | e2e | 50/50 | 757/2331 (32.48%; 置換 273、挿入 448、削除 36) | — | 28/67 (41.79%) | — | 11 | 80/98 (81.63%) | 0.224 / 0.326 | 0 | 0.056 / 0.056 | 0.203 / 0.277 | 0.318 / 0.432 |
| haas2p-excl+sft2-qwen | e2e | 50/50 | 180/2331 (7.72%; 置換 59、挿入 47、削除 74) | — | 52/67 (77.61%) | — | 1 | 0/98 (0.00%) | 0.434 / 0.606 | 0 | 0.168 / 0.168 | 0.363 / 0.549 | 0.561 / 0.727 |

用語正答率（見えない用語 / それ以外）
| 系統 | stage | 全体 | 見えない用語 | それ以外 | 緩い正答率：見えない用語（ASR） | 緩い正答率：それ以外（ASR） |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | 44/67 (65.67%) | 16/20 (80.00%) | 28/47 (59.57%) | — | — |
| haas2p+sft2-qwen | e2e | 56/67 (83.58%) | 18/20 (90.00%) | 38/47 (80.85%) | — | — |
| haas2p+sft2-qwen-rerun | e2e | 56/67 (83.58%) | 18/20 (90.00%) | 38/47 (80.85%) | — | — |
| haas2p-excl(no-format) | e2e | 28/67 (41.79%) | 0/20 (0.00%) | 28/47 (59.57%) | — | — |
| haas2p-excl+sft2-qwen | e2e | 52/67 (77.61%) | 14/20 (70.00%) | 38/47 (80.85%) | — | — |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p(no-format) | e2e | english_phrase | 10/10 | 175/437 (40.05%; 置換 78、挿入 84、削除 13) | 0/10 (0.00%) | — |
| haas2p(no-format) | e2e | instruction_like | 11/11 | 192/512 (37.50%; 置換 53、挿入 132、削除 7) | 1/11 (9.09%) | 1 |
| haas2p(no-format) | e2e | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| haas2p(no-format) | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p(no-format) | e2e | self_correction | 8/8 | 230/391 (58.82%; 置換 36、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas2p+sft2-qwen | e2e | english_phrase | 10/10 | 33/437 (7.55%; 置換 13、挿入 8、削除 12) | 3/10 (30.00%) | — |
| haas2p+sft2-qwen | e2e | instruction_like | 11/11 | 39/512 (7.62%; 置換 11、挿入 21、削除 7) | 2/11 (18.18%) | 0 |
| haas2p+sft2-qwen | e2e | list | 11/11 | 81/653 (12.40%; 置換 34、挿入 34、削除 13) | 3/11 (27.27%) | — |
| haas2p+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| haas2p+sft2-qwen | e2e | self_correction | 8/8 | 27/391 (6.91%; 置換 3、挿入 18、削除 6) | 2/8 (25.00%)（言い直しの正答率） | — |
| haas2p+sft2-qwen-rerun | e2e | english_phrase | 10/10 | 33/437 (7.55%; 置換 13、挿入 8、削除 12) | 3/10 (30.00%) | — |
| haas2p+sft2-qwen-rerun | e2e | instruction_like | 11/11 | 39/512 (7.62%; 置換 11、挿入 21、削除 7) | 2/11 (18.18%) | 0 |
| haas2p+sft2-qwen-rerun | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| haas2p+sft2-qwen-rerun | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| haas2p+sft2-qwen-rerun | e2e | self_correction | 8/8 | 27/391 (6.91%; 置換 3、挿入 18、削除 6) | 2/8 (25.00%)（言い直しの正答率） | — |
| haas2p-excl(no-format) | e2e | english_phrase | 10/10 | 186/437 (42.56%; 置換 93、挿入 80、削除 13) | 0/10 (0.00%) | — |
| haas2p-excl(no-format) | e2e | instruction_like | 11/11 | 205/512 (40.04%; 置換 73、挿入 125、削除 7) | 1/11 (9.09%) | 1 |
| haas2p-excl(no-format) | e2e | list | 11/11 | 186/653 (28.48%; 置換 69、挿入 111、削除 6) | 1/11 (9.09%) | — |
| haas2p-excl(no-format) | e2e | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas2p-excl(no-format) | e2e | self_correction | 8/8 | 244/391 (62.40%; 置換 61、挿入 180、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas2p-excl+sft2-qwen | e2e | english_phrase | 10/10 | 34/437 (7.78%; 置換 12、挿入 8、削除 14) | 2/10 (20.00%) | — |
| haas2p-excl+sft2-qwen | e2e | instruction_like | 11/11 | 51/512 (9.96%; 置換 10、挿入 21、削除 20) | 2/11 (18.18%) | 0 |
| haas2p-excl+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| haas2p-excl+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| haas2p-excl+sft2-qwen | e2e | self_correction | 8/8 | 48/391 (12.28%; 置換 5、挿入 22、削除 21) | 1/8 (12.50%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/metal-eval/devuser-scripted.jsonl",
  "results": [
    {
      "run": "runs/base-compare/devuser-haas2p-noformat.jsonl",
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
        "loose_accuracy": null,
        "unseen": {
          "correct": 16,
          "total": 20,
          "accuracy": 0.8,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 28,
          "total": 47,
          "accuracy": 0.5957446808510638,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
        "loose_accuracy": null,
        "unseen": {
          "correct": 18,
          "total": 20,
          "accuracy": 0.9,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 38,
          "total": 47,
          "accuracy": 0.8085106382978723,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
    },
    {
      "run": "runs/base-compare/devuser-haas2p+sft2-qwen-rerun.jsonl",
      "system": "haas2p+sft2-qwen-rerun",
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
        "loose_accuracy": null,
        "unseen": {
          "correct": 18,
          "total": 20,
          "accuracy": 0.9,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 38,
          "total": 47,
          "accuracy": 0.8085106382978723,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
          "median_s": 0.4329924794146791,
          "p90_s": 0.6066592505318112
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.16994341800455004,
            "p90_s": 0.16994341800455004
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3668344165198505,
            "p90_s": 0.5581083959550597
          },
          ">15s": {
            "count": 13,
            "median_s": 0.581830624025315,
            "p90_s": 0.7272181411972269
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
      "run": "runs/base-compare/devuser-haas2p-excl-noformat.jsonl",
      "system": "haas2p-excl(no-format)",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 757,
        "substitutions": 273,
        "insertions": 448,
        "deletions": 36,
        "reference_characters": 2331,
        "rate": 0.32475332475332475
      },
      "raw_cer": null,
      "terms": {
        "correct": 28,
        "total": 67,
        "accuracy": 0.417910447761194,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 0,
          "total": 20,
          "accuracy": 0.0,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 28,
          "total": 47,
          "accuracy": 0.5957446808510638,
          "loose_correct": null,
          "loose_accuracy": null
        }
      },
      "inserted_terms": {
        "count": 11,
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
            "edit_errors": 186,
            "substitutions": 93,
            "insertions": 80,
            "deletions": 13,
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
            "edit_errors": 205,
            "substitutions": 73,
            "insertions": 125,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.400390625
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 186,
            "substitutions": 69,
            "insertions": 111,
            "deletions": 6,
            "reference_characters": 653,
            "rate": 0.28483920367534454
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
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
            "edit_errors": 244,
            "substitutions": 61,
            "insertions": 180,
            "deletions": 3,
            "reference_characters": 391,
            "rate": 0.6240409207161125
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
          "median_s": 0.2236853960203007,
          "p90_s": 0.3258963541709818
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.05596641602460295,
            "p90_s": 0.05596641602460295
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.20310189598239958,
            "p90_s": 0.2774518330115825
          },
          ">15s": {
            "count": 13,
            "median_s": 0.31786033406388015,
            "p90_s": 0.4318326836219058
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
      "run": "runs/base-compare/devuser-haas2p-excl+sft2-qwen.jsonl",
      "system": "haas2p-excl+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 180,
        "substitutions": 59,
        "insertions": 47,
        "deletions": 74,
        "reference_characters": 2331,
        "rate": 0.07722007722007722
      },
      "raw_cer": null,
      "terms": {
        "correct": 52,
        "total": 67,
        "accuracy": 0.7761194029850746,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 14,
          "total": 20,
          "accuracy": 0.7,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 38,
          "total": 47,
          "accuracy": 0.8085106382978723,
          "loose_correct": null,
          "loose_accuracy": null
        }
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
            "edit_errors": 34,
            "substitutions": 12,
            "insertions": 8,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.07780320366132723
          },
          "exact_matches": 2,
          "exact_match_rate": 0.2,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 51,
            "substitutions": 10,
            "insertions": 21,
            "deletions": 20,
            "reference_characters": 512,
            "rate": 0.099609375
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
            "edit_errors": 48,
            "substitutions": 5,
            "insertions": 22,
            "deletions": 21,
            "reference_characters": 391,
            "rate": 0.12276214833759591
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
          "median_s": 0.4335317285149358,
          "p90_s": 0.6057173462235369
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.16792829101905227,
            "p90_s": 0.16792829101905227
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3632070415187627,
            "p90_s": 0.5494803125038743
          },
          ">15s": {
            "count": 13,
            "median_s": 0.561312000034377,
            "p90_s": 0.7272977999411524
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
  "unseen_terms": "data/eval/unseen-terms-devuser.txt"
}
```
