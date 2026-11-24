| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas2p+sft2-qwen | e2e | 1000/1000 | 2551/47482 (5.37%; 置換 779、挿入 935、削除 837) | — | 1286/1427 (90.12%) | — | 42 | 6/1608 (0.37%) | 0.559 / 0.882 | 1000 | — / — | — / — | — / — |
| val-haas2p+sft2-gemma-bf16 | e2e | 1000/1000 | 2468/47482 (5.20%; 置換 753、挿入 849、削除 866) | — | 1275/1427 (89.35%) | — | 38 | 5/1608 (0.31%) | 0.648 / 1.037 | 1000 | — / — | — / — | — / — |
| haas2p-excl+sft2-qwen | e2e | 1000/1000 | 2890/47482 (6.09%; 置換 1027、挿入 930、削除 933) | — | 1212/1427 (84.93%) | — | 44 | 5/1608 (0.31%) | 0.550 / 0.890 | 1000 | — / — | — / — | — / — |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | 1000/1000 | 2909/47482 (6.13%; 置換 998、挿入 876、削除 1035) | — | 1190/1427 (83.39%) | — | 38 | 5/1608 (0.31%) | 0.404 / 0.637 | 1000 | — / — | — / — | — / — |

用語正答率（見えない用語 / それ以外）
| 系統 | stage | 全体 | 見えない用語 | それ以外 | 緩い正答率：見えない用語（ASR） | 緩い正答率：それ以外（ASR） |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p+sft2-qwen | e2e | 1286/1427 (90.12%) | 375/433 (86.61%) | 911/994 (91.65%) | — | — |
| val-haas2p+sft2-gemma-bf16 | e2e | 1275/1427 (89.35%) | 370/433 (85.45%) | 905/994 (91.05%) | — | — |
| haas2p-excl+sft2-qwen | e2e | 1212/1427 (84.93%) | 300/433 (69.28%) | 912/994 (91.75%) | — | — |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | 1190/1427 (83.39%) | 290/433 (66.97%) | 900/994 (90.54%) | — | — |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas2p+sft2-qwen | e2e | self_correction | 203/203 | 827/7784 (10.62%; 置換 169、挿入 427、削除 231) | 108/203 (53.20%)（言い直しの正答率） | — |
| haas2p+sft2-qwen | e2e | english_phrase | 95/95 | 293/4948 (5.92%; 置換 82、挿入 107、削除 104) | 52/95 (54.74%) | — |
| haas2p+sft2-qwen | e2e | instruction_like | 123/123 | 349/6303 (5.54%; 置換 77、挿入 149、削除 123) | 79/123 (64.23%) | 1 |
| haas2p+sft2-qwen | e2e | no_change | 99/99 | 93/4325 (2.15%; 置換 48、挿入 8、削除 37) | 78/99 (78.79%)（無変更の保持） | — |
| haas2p+sft2-qwen | e2e | list | 84/84 | 407/4894 (8.32%; 置換 104、挿入 194、削除 109) | 31/84 (36.90%) | — |
| val-haas2p+sft2-gemma-bf16 | e2e | self_correction | 203/203 | 842/7784 (10.82%; 置換 174、挿入 400、削除 268) | 100/203 (49.26%)（言い直しの正答率） | — |
| val-haas2p+sft2-gemma-bf16 | e2e | english_phrase | 95/95 | 240/4948 (4.85%; 置換 61、挿入 99、削除 80) | 58/95 (61.05%) | — |
| val-haas2p+sft2-gemma-bf16 | e2e | instruction_like | 123/123 | 338/6303 (5.36%; 置換 102、挿入 144、削除 92) | 79/123 (64.23%) | 0 |
| val-haas2p+sft2-gemma-bf16 | e2e | no_change | 99/99 | 96/4325 (2.22%; 置換 36、挿入 11、削除 49) | 79/99 (79.80%)（無変更の保持） | — |
| val-haas2p+sft2-gemma-bf16 | e2e | list | 84/84 | 363/4894 (7.42%; 置換 91、挿入 164、削除 108) | 38/84 (45.24%) | — |
| haas2p-excl+sft2-qwen | e2e | self_correction | 203/203 | 841/7784 (10.80%; 置換 187、挿入 426、削除 228) | 103/203 (50.74%)（言い直しの正答率） | — |
| haas2p-excl+sft2-qwen | e2e | english_phrase | 95/95 | 321/4948 (6.49%; 置換 96、挿入 109、削除 116) | 45/95 (47.37%) | — |
| haas2p-excl+sft2-qwen | e2e | instruction_like | 123/123 | 392/6303 (6.22%; 置換 112、挿入 160、削除 120) | 71/123 (57.72%) | 1 |
| haas2p-excl+sft2-qwen | e2e | no_change | 99/99 | 105/4325 (2.43%; 置換 56、挿入 13、削除 36) | 79/99 (79.80%)（無変更の保持） | — |
| haas2p-excl+sft2-qwen | e2e | list | 84/84 | 415/4894 (8.48%; 置換 115、挿入 172、削除 128) | 29/84 (34.52%) | — |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | self_correction | 203/203 | 919/7784 (11.81%; 置換 226、挿入 403、削除 290) | 90/203 (44.33%)（言い直しの正答率） | — |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | english_phrase | 95/95 | 296/4948 (5.98%; 置換 88、挿入 101、削除 107) | 51/95 (53.68%) | — |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | instruction_like | 123/123 | 407/6303 (6.46%; 置換 128、挿入 146、削除 133) | 71/123 (57.72%) | 0 |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | no_change | 99/99 | 129/4325 (2.98%; 置換 58、挿入 20、削除 51) | 76/99 (76.77%)（無変更の保持） | — |
| val-haas2p-excl+sft2-gemma-bf16 | e2e | list | 84/84 | 408/4894 (8.34%; 置換 129、挿入 142、削除 137) | 34/84 (40.48%) | — |

JSON:
```json
{
  "manifest": "runs/formatter-sft2-gemma/manifest-val-no-audio.jsonl",
  "results": [
    {
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/formatter-sft2/val-haas2p+sft2-qwen.jsonl",
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
        "unknown_duration_rows": 1000,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/formatter-sft2-gemma/val-haas2p+sft2-gemma-bf16.jsonl",
      "system": "val-haas2p+sft2-gemma-bf16",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 2468,
        "substitutions": 753,
        "insertions": 849,
        "deletions": 866,
        "reference_characters": 47482,
        "rate": 0.051977591508361065
      },
      "raw_cer": null,
      "terms": {
        "correct": 1275,
        "total": 1427,
        "accuracy": 0.8934828311142257,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 370,
          "total": 433,
          "accuracy": 0.8545034642032333,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 905,
          "total": 994,
          "accuracy": 0.9104627766599598,
          "loose_correct": null,
          "loose_accuracy": null
        }
      },
      "inserted_terms": {
        "count": 38,
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
            "edit_errors": 842,
            "substitutions": 174,
            "insertions": 400,
            "deletions": 268,
            "reference_characters": 7784,
            "rate": 0.10817060637204522
          },
          "exact_matches": 100,
          "exact_match_rate": 0.49261083743842365,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 240,
            "substitutions": 61,
            "insertions": 99,
            "deletions": 80,
            "reference_characters": 4948,
            "rate": 0.04850444624090541
          },
          "exact_matches": 58,
          "exact_match_rate": 0.6105263157894737,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 338,
            "substitutions": 102,
            "insertions": 144,
            "deletions": 92,
            "reference_characters": 6303,
            "rate": 0.05362525781373949
          },
          "exact_matches": 79,
          "exact_match_rate": 0.6422764227642277,
          "suspected_responses": 0,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 96,
            "substitutions": 36,
            "insertions": 11,
            "deletions": 49,
            "reference_characters": 4325,
            "rate": 0.022196531791907514
          },
          "exact_matches": 79,
          "exact_match_rate": 0.797979797979798,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 363,
            "substitutions": 91,
            "insertions": 164,
            "deletions": 108,
            "reference_characters": 4894,
            "rate": 0.0741724560686555
          },
          "exact_matches": 38,
          "exact_match_rate": 0.4523809523809524,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.6477725761506008,
          "p90_s": 1.0368589888777933
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
        "unknown_duration_rows": 1000,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "/Users/marutyan/PrivateDev/voiceIME/runs/base-compare/val-haas2p-excl+sft2-qwen.jsonl",
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
        "unknown_duration_rows": 1000,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/formatter-sft2-gemma/val-haas2p-excl+sft2-gemma-bf16.jsonl",
      "system": "val-haas2p-excl+sft2-gemma-bf16",
      "stage": "e2e",
      "utterances": {
        "manifest": 1000,
        "evaluated": 1000,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 2909,
        "substitutions": 998,
        "insertions": 876,
        "deletions": 1035,
        "reference_characters": 47482,
        "rate": 0.061265321595552
      },
      "raw_cer": null,
      "terms": {
        "correct": 1190,
        "total": 1427,
        "accuracy": 0.833917309039944,
        "loose_correct": null,
        "loose_accuracy": null,
        "unseen": {
          "correct": 290,
          "total": 433,
          "accuracy": 0.6697459584295612,
          "loose_correct": null,
          "loose_accuracy": null
        },
        "seen": {
          "correct": 900,
          "total": 994,
          "accuracy": 0.9054325955734407,
          "loose_correct": null,
          "loose_accuracy": null
        }
      },
      "inserted_terms": {
        "count": 38,
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
            "edit_errors": 919,
            "substitutions": 226,
            "insertions": 403,
            "deletions": 290,
            "reference_characters": 7784,
            "rate": 0.11806269270298048
          },
          "exact_matches": 90,
          "exact_match_rate": 0.4433497536945813,
          "suspected_responses": null,
          "manifest_count": 203
        },
        "english_phrase": {
          "count": 95,
          "cer": {
            "edit_errors": 296,
            "substitutions": 88,
            "insertions": 101,
            "deletions": 107,
            "reference_characters": 4948,
            "rate": 0.05982215036378335
          },
          "exact_matches": 51,
          "exact_match_rate": 0.5368421052631579,
          "suspected_responses": null,
          "manifest_count": 95
        },
        "instruction_like": {
          "count": 123,
          "cer": {
            "edit_errors": 407,
            "substitutions": 128,
            "insertions": 146,
            "deletions": 133,
            "reference_characters": 6303,
            "rate": 0.06457242582897033
          },
          "exact_matches": 71,
          "exact_match_rate": 0.5772357723577236,
          "suspected_responses": 0,
          "manifest_count": 123
        },
        "no_change": {
          "count": 99,
          "cer": {
            "edit_errors": 129,
            "substitutions": 58,
            "insertions": 20,
            "deletions": 51,
            "reference_characters": 4325,
            "rate": 0.02982658959537572
          },
          "exact_matches": 76,
          "exact_match_rate": 0.7676767676767676,
          "suspected_responses": null,
          "manifest_count": 99
        },
        "list": {
          "count": 84,
          "cer": {
            "edit_errors": 408,
            "substitutions": 129,
            "insertions": 142,
            "deletions": 137,
            "reference_characters": 4894,
            "rate": 0.08336738863914998
          },
          "exact_matches": 34,
          "exact_match_rate": 0.40476190476190477,
          "suspected_responses": null,
          "manifest_count": 84
        }
      },
      "latency": {
        "all": {
          "count": 1000,
          "median_s": 0.4035574384743086,
          "p90_s": 0.6373684234615211
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
        "unknown_duration_rows": 1000,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    }
  ],
  "unseen_terms": "/Users/marutyan/PrivateDev/voiceIME/data/eval/unseen-terms-val.txt"
}
```
