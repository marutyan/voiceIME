| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p+sft2-qwen | e2e | 50/50 | 171/2331 (7.34%; 置換 59、挿入 67、削除 45) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.435 / 0.626 | 50 | — / — | — / — | — / — |
| devuser-haas2p+sft2-gemma-bf16 | e2e | 50/50 | 210/2331 (9.01%; 置換 57、挿入 68、削除 85) | — | 54/67 (80.60%) | — | 1 | 0/98 (0.00%) | 0.591 / 0.693 | 50 | — / — | — / — | — / — |
| haas2p-excl+sft2-qwen | e2e | 50/50 | 180/2331 (7.72%; 置換 59、挿入 47、削除 74) | — | 52/67 (77.61%) | — | 1 | 0/98 (0.00%) | 0.434 / 0.606 | 50 | — / — | — / — | — / — |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | 50/50 | 193/2331 (8.28%; 置換 55、挿入 50、削除 88) | — | 50/67 (74.63%) | — | 1 | 0/98 (0.00%) | 0.410 / 0.512 | 50 | — / — | — / — | — / — |

用語正答率（見えない用語 / それ以外）
| 系統 | stage | 全体 | 見えない用語 | それ以外 | 緩い正答率：見えない用語（ASR） | 緩い正答率：それ以外（ASR） |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p+sft2-qwen | e2e | 56/67 (83.58%) | 18/20 (90.00%) | 38/47 (80.85%) | — | — |
| devuser-haas2p+sft2-gemma-bf16 | e2e | 54/67 (80.60%) | 16/20 (80.00%) | 38/47 (80.85%) | — | — |
| haas2p-excl+sft2-qwen | e2e | 52/67 (77.61%) | 14/20 (70.00%) | 38/47 (80.85%) | — | — |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | 50/67 (74.63%) | 12/20 (60.00%) | 38/47 (80.85%) | — | — |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p+sft2-qwen | e2e | english_phrase | 10/10 | 33/437 (7.55%; 置換 13、挿入 8、削除 12) | 3/10 (30.00%) | — |
| haas2p+sft2-qwen | e2e | instruction_like | 11/11 | 39/512 (7.62%; 置換 11、挿入 21、削除 7) | 2/11 (18.18%) | 0 |
| haas2p+sft2-qwen | e2e | list | 11/11 | 81/653 (12.40%; 置換 34、挿入 34、削除 13) | 3/11 (27.27%) | — |
| haas2p+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| haas2p+sft2-qwen | e2e | self_correction | 8/8 | 27/391 (6.91%; 置換 3、挿入 18、削除 6) | 2/8 (25.00%)（言い直しの正答率） | — |
| devuser-haas2p+sft2-gemma-bf16 | e2e | english_phrase | 10/10 | 34/437 (7.78%; 置換 16、挿入 4、削除 14) | 3/10 (30.00%) | — |
| devuser-haas2p+sft2-gemma-bf16 | e2e | instruction_like | 11/11 | 70/512 (13.67%; 置換 13、挿入 41、削除 16) | 2/11 (18.18%) | 0 |
| devuser-haas2p+sft2-gemma-bf16 | e2e | list | 11/11 | 52/653 (7.96%; 置換 18、挿入 12、削除 22) | 5/11 (45.45%) | — |
| devuser-haas2p+sft2-gemma-bf16 | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| devuser-haas2p+sft2-gemma-bf16 | e2e | self_correction | 8/8 | 84/391 (21.48%; 置換 16、挿入 35、削除 33) | 1/8 (12.50%)（言い直しの正答率） | — |
| haas2p-excl+sft2-qwen | e2e | english_phrase | 10/10 | 34/437 (7.78%; 置換 12、挿入 8、削除 14) | 2/10 (20.00%) | — |
| haas2p-excl+sft2-qwen | e2e | instruction_like | 11/11 | 51/512 (9.96%; 置換 10、挿入 21、削除 20) | 2/11 (18.18%) | 0 |
| haas2p-excl+sft2-qwen | e2e | list | 11/11 | 57/653 (8.73%; 置換 34、挿入 10、削除 13) | 3/11 (27.27%) | — |
| haas2p-excl+sft2-qwen | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| haas2p-excl+sft2-qwen | e2e | self_correction | 8/8 | 48/391 (12.28%; 置換 5、挿入 22、削除 21) | 1/8 (12.50%)（言い直しの正答率） | — |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | english_phrase | 10/10 | 25/437 (5.72%; 置換 8、挿入 4、削除 13) | 3/10 (30.00%) | — |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | instruction_like | 11/11 | 62/512 (12.11%; 置換 21、挿入 23、削除 18) | 3/11 (27.27%) | 0 |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | list | 11/11 | 52/653 (7.96%; 置換 18、挿入 12、削除 22) | 5/11 (45.45%) | — |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | no_change | 8/8 | 6/372 (1.61%; 置換 0、挿入 1、削除 5) | 6/8 (75.00%)（無変更の保持） | — |
| devuser-haas2p-excl+sft2-gemma-bf16 | e2e | self_correction | 8/8 | 74/391 (18.93%; 置換 17、挿入 17、削除 40) | 1/8 (12.50%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "runs/formatter-sft2-gemma/manifest-devuser-no-audio.jsonl",
  "results": [
    {
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft2/devuser-haas2p+sft2-qwen.jsonl",
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
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          "5-15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          ">15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          }
        },
        "unknown_duration_rows": 50,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/formatter-sft2-gemma/devuser-haas2p+sft2-gemma-bf16.jsonl",
      "system": "devuser-haas2p+sft2-gemma-bf16",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 210,
        "substitutions": 57,
        "insertions": 68,
        "deletions": 85,
        "reference_characters": 2331,
        "rate": 0.09009009009009009
      },
      "raw_cer": null,
      "terms": {
        "correct": 54,
        "total": 67,
        "accuracy": 0.8059701492537313,
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
            "substitutions": 16,
            "insertions": 4,
            "deletions": 14,
            "reference_characters": 437,
            "rate": 0.07780320366132723
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 70,
            "substitutions": 13,
            "insertions": 41,
            "deletions": 16,
            "reference_characters": 512,
            "rate": 0.13671875
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 52,
            "substitutions": 18,
            "insertions": 12,
            "deletions": 22,
            "reference_characters": 653,
            "rate": 0.07963246554364471
          },
          "exact_matches": 5,
          "exact_match_rate": 0.45454545454545453,
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
            "edit_errors": 84,
            "substitutions": 16,
            "insertions": 35,
            "deletions": 33,
            "reference_characters": 391,
            "rate": 0.21483375959079284
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
          "median_s": 0.5914794425945729,
          "p90_s": 0.6934517219429835
        },
        "duration_groups": {
          "<=5s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          "5-15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          ">15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          }
        },
        "unknown_duration_rows": 50,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/base-compare/devuser-haas2p-excl+sft2-qwen.jsonl",
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
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          "5-15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          ">15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          }
        },
        "unknown_duration_rows": 50,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/formatter-sft2-gemma/devuser-haas2p-excl+sft2-gemma-bf16.jsonl",
      "system": "devuser-haas2p-excl+sft2-gemma-bf16",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 193,
        "substitutions": 55,
        "insertions": 50,
        "deletions": 88,
        "reference_characters": 2331,
        "rate": 0.0827970827970828
      },
      "raw_cer": null,
      "terms": {
        "correct": 50,
        "total": 67,
        "accuracy": 0.746268656716418,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 12,
          "total": 20,
          "accuracy": 0.6,
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
            "edit_errors": 25,
            "substitutions": 8,
            "insertions": 4,
            "deletions": 13,
            "reference_characters": 437,
            "rate": 0.057208237986270026
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 62,
            "substitutions": 21,
            "insertions": 23,
            "deletions": 18,
            "reference_characters": 512,
            "rate": 0.12109375
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 52,
            "substitutions": 18,
            "insertions": 12,
            "deletions": 22,
            "reference_characters": 653,
            "rate": 0.07963246554364471
          },
          "exact_matches": 5,
          "exact_match_rate": 0.45454545454545453,
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
            "edit_errors": 74,
            "substitutions": 17,
            "insertions": 17,
            "deletions": 40,
            "reference_characters": 391,
            "rate": 0.18925831202046037
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
          "median_s": 0.41010980418417603,
          "p90_s": 0.5123207623348571
        },
        "duration_groups": {
          "<=5s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          "5-15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          },
          ">15s": {
            "count": 0,
            "median_s": null,
            "p90_s": null
          }
        },
        "unknown_duration_rows": 50,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    }
  ],
  "unseen_terms": "/Users/marutyan/PrivateDev/voiceIME/data/eval/unseen-terms-devuser.txt"
}
```
