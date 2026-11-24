warning: runs/test-novel-baseline/e2e-include-novel-twopass+sft2-qwen.jsonl (sft2-qwen+v2gloss/e2e): 音声長不明のため音声長別遅延集計から除外=500
warning: runs/test-novel-baseline/e2e-include-novel-segmerge080+sft2-qwen.jsonl (segmerge080+sft2-qwen+v2gloss/e2e): 音声長不明のため音声長別遅延集計から除外=500
| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sft2-qwen+v2gloss | e2e | 500/500 | 4753/25921 (18.34%; 置換 1993、挿入 896、削除 1864) | — | 115/500 (23.00%) | — | 17 | 12/1299 (0.92%) | 1.441 / 3.835 | 500 | — / — | — / — | — / — |
| segmerge080+sft2-qwen+v2gloss | e2e | 500/500 | 4010/25921 (15.47%; 置換 1558、挿入 789、削除 1663) | — | 109/500 (21.80%) | — | 19 | 8/1299 (0.62%) | 1.466 / 3.842 | 500 | — / — | — / — | — / — |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| sft2-qwen+v2gloss | e2e | instruction_like | 58/58 | 461/3049 (15.12%; 置換 196、挿入 67、削除 198) | 11/58 (18.97%) | 0 |
| sft2-qwen+v2gloss | e2e | list | 50/50 | 738/3286 (22.46%; 置換 280、挿入 216、削除 242) | 3/50 (6.00%) | — |
| sft2-qwen+v2gloss | e2e | self_correction | 111/111 | 1386/5626 (24.64%; 置換 447、挿入 310、削除 629) | 6/111 (5.41%)（言い直しの正答率） | — |
| sft2-qwen+v2gloss | e2e | english_phrase | 62/62 | 599/3567 (16.79%; 置換 277、挿入 63、削除 259) | 4/62 (6.45%) | — |
| segmerge080+sft2-qwen+v2gloss | e2e | instruction_like | 58/58 | 378/3049 (12.40%; 置換 161、挿入 55、削除 162) | 12/58 (20.69%) | 0 |
| segmerge080+sft2-qwen+v2gloss | e2e | list | 50/50 | 710/3286 (21.61%; 置換 210、挿入 233、削除 267) | 5/50 (10.00%) | — |
| segmerge080+sft2-qwen+v2gloss | e2e | self_correction | 111/111 | 1236/5626 (21.97%; 置換 364、挿入 279、削除 593) | 10/111 (9.01%)（言い直しの正答率） | — |
| segmerge080+sft2-qwen+v2gloss | e2e | english_phrase | 62/62 | 433/3567 (12.14%; 置換 175、挿入 52、削除 206) | 7/62 (11.29%) | — |

JSON:
```json
{
  "manifest": "runs/asr-tts/r3-audio-20261122/test-novel-source.jsonl",
  "results": [
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
    },
    {
      "run": "runs/test-novel-baseline/e2e-include-novel-segmerge080+sft2-qwen.jsonl",
      "system": "segmerge080+sft2-qwen+v2gloss",
      "stage": "e2e",
      "utterances": {
        "manifest": 500,
        "evaluated": 500,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 4010,
        "substitutions": 1558,
        "insertions": 789,
        "deletions": 1663,
        "reference_characters": 25921,
        "rate": 0.1547008217275568
      },
      "raw_cer": null,
      "terms": {
        "correct": 109,
        "total": 500,
        "accuracy": 0.218,
        "loose_correct": null,
        "loose_accuracy": null
      },
      "inserted_terms": {
        "count": 19,
        "basis": "target_textのterms"
      },
      "fillers": {
        "residual_count": 8,
        "manifest_count": 1299,
        "residual_rate": 0.006158583525789068
      },
      "tags": {
        "instruction_like": {
          "count": 58,
          "cer": {
            "edit_errors": 378,
            "substitutions": 161,
            "insertions": 55,
            "deletions": 162,
            "reference_characters": 3049,
            "rate": 0.12397507379468678
          },
          "exact_matches": 12,
          "exact_match_rate": 0.20689655172413793,
          "suspected_responses": 0,
          "manifest_count": 58
        },
        "list": {
          "count": 50,
          "cer": {
            "edit_errors": 710,
            "substitutions": 210,
            "insertions": 233,
            "deletions": 267,
            "reference_characters": 3286,
            "rate": 0.21606816798539258
          },
          "exact_matches": 5,
          "exact_match_rate": 0.1,
          "suspected_responses": null,
          "manifest_count": 50
        },
        "self_correction": {
          "count": 111,
          "cer": {
            "edit_errors": 1236,
            "substitutions": 364,
            "insertions": 279,
            "deletions": 593,
            "reference_characters": 5626,
            "rate": 0.21969427657305368
          },
          "exact_matches": 10,
          "exact_match_rate": 0.09009009009009009,
          "suspected_responses": null,
          "manifest_count": 111
        },
        "english_phrase": {
          "count": 62,
          "cer": {
            "edit_errors": 433,
            "substitutions": 175,
            "insertions": 52,
            "deletions": 206,
            "reference_characters": 3567,
            "rate": 0.12139052425007009
          },
          "exact_matches": 7,
          "exact_match_rate": 0.11290322580645161,
          "suspected_responses": null,
          "manifest_count": 62
        }
      },
      "latency": {
        "all": {
          "count": 500,
          "median_s": 1.466286280483473,
          "p90_s": 3.841657088359354
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
