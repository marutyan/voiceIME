warning: runs/asr-tts/r3-audio-20261122/test-novel-include-novel-twopass.jsonl (haas-ja-v1.0-speechcpp-q8_0+twopass/asr): 音声長不明のため音声長別遅延集計から除外=500
warning: runs/asr-tts/r3-audio-20261122/test-novel-include-novel-plain.jsonl (haas-ja-v1.0-speechcpp-q8_0/asr): 音声長不明のため音声長別遅延集計から除外=500
warning: runs/test-novel-baseline/e2e-include-novel-twopass+sft2-qwen.jsonl (sft2-qwen+v2gloss/e2e): 音声長不明のため音声長別遅延集計から除外=500
| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 500/500 | 5334/31154 (17.12%; 置換 3461、挿入 398、削除 1475) | 6800/31154 (21.83%; 置換 4511、挿入 594、削除 1695) | 96/500 (19.20%) | 154/500 (30.80%) | 0 | 1185/1299 (91.22%) | 0.989 / 3.372 | 500 | — / — | — / — | — / — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | 500/500 | 3336/31154 (10.71%; 置換 1751、挿入 127、削除 1458) | 3753/31154 (12.05%; 置換 1945、挿入 131、削除 1677) | 1/500 (0.20%) | 157/500 (31.40%) | 0 | 1198/1299 (92.22%) | 0.484 / 1.856 | 500 | — / — | — / — | — / — |
| sft2-qwen+v2gloss | e2e | 500/500 | 4753/25921 (18.34%; 置換 1993、挿入 896、削除 1864) | — | 115/500 (23.00%) | — | 17 | 12/1299 (0.92%) | 1.441 / 3.835 | 500 | — / — | — / — | — / — |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | instruction_like | 58/58 | 967/3049 (31.72%; 置換 396、挿入 499、削除 72) | 1/58 (1.72%) | 1 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | list | 50/50 | 1206/3286 (36.70%; 置換 412、挿入 707、削除 87) | 0/50 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | self_correction | 111/111 | 3134/5626 (55.71%; 置換 1027、挿入 1981、削除 126) | 0/111 (0.00%)（言い直しの正答率） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | english_phrase | 62/62 | 1580/3567 (44.29%; 置換 797、挿入 625、削除 158) | 0/62 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | instruction_like | 58/58 | 1089/3049 (35.72%; 置換 513、挿入 469、削除 107) | 0/58 (0.00%) | 1 |
| haas-ja-v1.0-speechcpp-q8_0 | asr | list | 50/50 | 1171/3286 (35.64%; 置換 409、挿入 665、削除 97) | 0/50 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | self_correction | 111/111 | 3213/5626 (57.11%; 置換 1203、挿入 1871、削除 139) | 0/111 (0.00%)（言い直しの正答率） | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | english_phrase | 62/62 | 1702/3567 (47.72%; 置換 995、挿入 541、削除 166) | 0/62 (0.00%) | — |
| sft2-qwen+v2gloss | e2e | instruction_like | 58/58 | 461/3049 (15.12%; 置換 196、挿入 67、削除 198) | 11/58 (18.97%) | 0 |
| sft2-qwen+v2gloss | e2e | list | 50/50 | 738/3286 (22.46%; 置換 280、挿入 216、削除 242) | 3/50 (6.00%) | — |
| sft2-qwen+v2gloss | e2e | self_correction | 111/111 | 1386/5626 (24.64%; 置換 447、挿入 310、削除 629) | 6/111 (5.41%)（言い直しの正答率） | — |
| sft2-qwen+v2gloss | e2e | english_phrase | 62/62 | 599/3567 (16.79%; 置換 277、挿入 63、削除 259) | 4/62 (6.45%) | — |

JSON:
```json
{
  "manifest": "runs/asr-tts/r3-audio-20261122/test-novel-source.jsonl",
  "results": [
    {
      "run": "runs/asr-tts/r3-audio-20261122/test-novel-include-novel-twopass.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 500,
        "evaluated": 500,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 5334,
        "substitutions": 3461,
        "insertions": 398,
        "deletions": 1475,
        "reference_characters": 31154,
        "rate": 0.17121396931373178
      },
      "raw_cer": {
        "edit_errors": 6800,
        "substitutions": 4511,
        "insertions": 594,
        "deletions": 1695,
        "reference_characters": 31154,
        "rate": 0.21827052705912564
      },
      "terms": {
        "correct": 96,
        "total": 500,
        "accuracy": 0.192,
        "loose_correct": 154,
        "loose_accuracy": 0.308
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 1185,
        "manifest_count": 1299,
        "residual_rate": 0.9122401847575058
      },
      "tags": {
        "instruction_like": {
          "count": 58,
          "cer": {
            "edit_errors": 967,
            "substitutions": 396,
            "insertions": 499,
            "deletions": 72,
            "reference_characters": 3049,
            "rate": 0.317153164972122
          },
          "exact_matches": 1,
          "exact_match_rate": 0.017241379310344827,
          "suspected_responses": 1,
          "manifest_count": 58
        },
        "list": {
          "count": 50,
          "cer": {
            "edit_errors": 1206,
            "substitutions": 412,
            "insertions": 707,
            "deletions": 87,
            "reference_characters": 3286,
            "rate": 0.3670115642118077
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 50
        },
        "self_correction": {
          "count": 111,
          "cer": {
            "edit_errors": 3134,
            "substitutions": 1027,
            "insertions": 1981,
            "deletions": 126,
            "reference_characters": 5626,
            "rate": 0.5570565232847494
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 111
        },
        "english_phrase": {
          "count": 62,
          "cer": {
            "edit_errors": 1580,
            "substitutions": 797,
            "insertions": 625,
            "deletions": 158,
            "reference_characters": 3567,
            "rate": 0.4429492570787777
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 62
        }
      },
      "latency": {
        "all": {
          "count": 500,
          "median_s": 0.9894754454726353,
          "p90_s": 3.371951399696991
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
        "unknown_duration_rows": 500,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/asr-tts/r3-audio-20261122/test-novel-include-novel-plain.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0",
      "stage": "asr",
      "utterances": {
        "manifest": 500,
        "evaluated": 500,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 3336,
        "substitutions": 1751,
        "insertions": 127,
        "deletions": 1458,
        "reference_characters": 31154,
        "rate": 0.1070809526866534
      },
      "raw_cer": {
        "edit_errors": 3753,
        "substitutions": 1945,
        "insertions": 131,
        "deletions": 1677,
        "reference_characters": 31154,
        "rate": 0.12046607177248507
      },
      "terms": {
        "correct": 1,
        "total": 500,
        "accuracy": 0.002,
        "loose_correct": 157,
        "loose_accuracy": 0.314
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 1198,
        "manifest_count": 1299,
        "residual_rate": 0.922247882986913
      },
      "tags": {
        "instruction_like": {
          "count": 58,
          "cer": {
            "edit_errors": 1089,
            "substitutions": 513,
            "insertions": 469,
            "deletions": 107,
            "reference_characters": 3049,
            "rate": 0.35716628402755
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": 1,
          "manifest_count": 58
        },
        "list": {
          "count": 50,
          "cer": {
            "edit_errors": 1171,
            "substitutions": 409,
            "insertions": 665,
            "deletions": 97,
            "reference_characters": 3286,
            "rate": 0.3563603164942179
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 50
        },
        "self_correction": {
          "count": 111,
          "cer": {
            "edit_errors": 3213,
            "substitutions": 1203,
            "insertions": 1871,
            "deletions": 139,
            "reference_characters": 5626,
            "rate": 0.5710984713828653
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 111
        },
        "english_phrase": {
          "count": 62,
          "cer": {
            "edit_errors": 1702,
            "substitutions": 995,
            "insertions": 541,
            "deletions": 166,
            "reference_characters": 3567,
            "rate": 0.4771516680684048
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 62
        }
      },
      "latency": {
        "all": {
          "count": 500,
          "median_s": 0.48418129852507263,
          "p90_s": 1.85589120532386
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
        "unknown_duration_rows": 500,
        "invalid_latency_rows": 0
      },
      "warnings": {
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "runs/test-novel-baseline/e2e-include-novel-twopass+sft2-qwen.jsonl",
      "system": "sft2-qwen+v2gloss",
      "stage": "e2e",
      "utterances": {
        "manifest": 500,
        "evaluated": 500,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 4753,
        "substitutions": 1993,
        "insertions": 896,
        "deletions": 1864,
        "reference_characters": 25921,
        "rate": 0.1833648393194707
      },
      "raw_cer": null,
      "terms": {
        "correct": 115,
        "total": 500,
        "accuracy": 0.23,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 17,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 12,
        "manifest_count": 1299,
        "residual_rate": 0.009237875288683603
      },
      "tags": {
        "instruction_like": {
          "count": 58,
          "cer": {
            "edit_errors": 461,
            "substitutions": 196,
            "insertions": 67,
            "deletions": 198,
            "reference_characters": 3049,
            "rate": 0.15119711380780584
          },
          "exact_matches": 11,
          "exact_match_rate": 0.1896551724137931,
          "suspected_responses": 0,
          "manifest_count": 58
        },
        "list": {
          "count": 50,
          "cer": {
            "edit_errors": 738,
            "substitutions": 280,
            "insertions": 216,
            "deletions": 242,
            "reference_characters": 3286,
            "rate": 0.2245891661594644
          },
          "exact_matches": 3,
          "exact_match_rate": 0.06,
          "suspected_responses": null,
          "manifest_count": 50
        },
        "self_correction": {
          "count": 111,
          "cer": {
            "edit_errors": 1386,
            "substitutions": 447,
            "insertions": 310,
            "deletions": 629,
            "reference_characters": 5626,
            "rate": 0.24635620334162817
          },
          "exact_matches": 6,
          "exact_match_rate": 0.05405405405405406,
          "suspected_responses": null,
          "manifest_count": 111
        },
        "english_phrase": {
          "count": 62,
          "cer": {
            "edit_errors": 599,
            "substitutions": 277,
            "insertions": 63,
            "deletions": 259,
            "reference_characters": 3567,
            "rate": 0.167928231006448
          },
          "exact_matches": 4,
          "exact_match_rate": 0.06451612903225806,
          "suspected_responses": null,
          "manifest_count": 62
        }
      },
      "latency": {
        "all": {
          "count": 500,
          "median_s": 1.440925722650718,
          "p90_s": 3.834583524998743
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
        "unknown_duration_rows": 500,
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
