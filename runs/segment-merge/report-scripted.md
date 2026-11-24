warning: runs/segment-merge/e2e-current+sft2-qwen.jsonl: manifestにないid=50, hyp欠落=0
warning: runs/segment-merge/e2e-segmerge+sft2-qwen.jsonl: manifestにないid=50, hyp欠落=0
| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current+sft2-qwen | e2e | 50/50 | 127/2330 (5.45%; 置換 58、挿入 34、削除 35) | — | 56/67 (83.58%) | — | 1 | 0/98 (0.00%) | 0.436 / 0.615 | 0 | 0.163 / 0.163 | 0.374 / 0.561 | 0.594 / 0.735 |
| segmerge+sft2-qwen | e2e | 50/50 | 84/2330 (3.61%; 置換 25、挿入 23、削除 36) | — | 58/67 (86.57%) | — | 1 | 0/98 (0.00%) | 0.449 / 0.633 | 0 | 0.170 / 0.170 | 0.365 / 0.571 | 0.615 / 0.734 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| current+sft2-qwen | e2e | english_phrase | 10/10 | 30/440 (6.82%; 置換 13、挿入 5、削除 12) | 3/10 (30.00%) | — |
| current+sft2-qwen | e2e | instruction_like | 11/11 | 36/510 (7.06%; 置換 10、挿入 21、削除 5) | 3/11 (27.27%) | 0 |
| current+sft2-qwen | e2e | list | 10/10 | 39/601 (6.49%; 置換 25、挿入 3、削除 11) | 3/10 (30.00%) | — |
| current+sft2-qwen | e2e | no_change | 8/8 | 1/367 (0.27%; 置換 0、挿入 1、削除 0) | 7/8 (87.50%)（無変更の保持） | — |
| current+sft2-qwen | e2e | self_correction | 8/8 | 25/390 (6.41%; 置換 2、挿入 18、削除 5) | 2/8 (25.00%)（言い直しの正答率） | — |
| segmerge+sft2-qwen | e2e | english_phrase | 10/10 | 15/440 (3.41%; 置換 1、挿入 3、削除 11) | 4/10 (40.00%) | — |
| segmerge+sft2-qwen | e2e | instruction_like | 11/11 | 36/510 (7.06%; 置換 12、挿入 16、削除 8) | 3/11 (27.27%) | 0 |
| segmerge+sft2-qwen | e2e | list | 10/10 | 15/601 (2.50%; 置換 2、挿入 3、削除 10) | 3/10 (30.00%) | — |
| segmerge+sft2-qwen | e2e | no_change | 8/8 | 1/367 (0.27%; 置換 0、挿入 1、削除 0) | 7/8 (87.50%)（無変更の保持） | — |
| segmerge+sft2-qwen | e2e | self_correction | 8/8 | 21/390 (5.38%; 置換 2、挿入 14、削除 5) | 3/8 (37.50%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/devuser-scripted-after.jsonl",
  "results": [
    {
      "run": "runs/segment-merge/e2e-current+sft2-qwen.jsonl",
      "system": "current+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 127,
        "substitutions": 58,
        "insertions": 34,
        "deletions": 35,
        "reference_characters": 2330,
        "rate": 0.054506437768240344
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
            "edit_errors": 30,
            "substitutions": 13,
            "insertions": 5,
            "deletions": 12,
            "reference_characters": 440,
            "rate": 0.06818181818181818
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 36,
            "substitutions": 10,
            "insertions": 21,
            "deletions": 5,
            "reference_characters": 510,
            "rate": 0.07058823529411765
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 10,
          "cer": {
            "edit_errors": 39,
            "substitutions": 25,
            "insertions": 3,
            "deletions": 11,
            "reference_characters": 601,
            "rate": 0.064891846921797
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 1,
            "substitutions": 0,
            "insertions": 1,
            "deletions": 0,
            "reference_characters": 367,
            "rate": 0.0027247956403269754
          },
          "exact_matches": 7,
          "exact_match_rate": 0.875,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 25,
            "substitutions": 2,
            "insertions": 18,
            "deletions": 5,
            "reference_characters": 390,
            "rate": 0.0641025641025641
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
          "median_s": 0.43600527103990316,
          "p90_s": 0.614903708093334
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.16271375108044595,
            "p90_s": 0.16271375108044595
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3735045420471579,
            "p90_s": 0.5606448334874585
          },
          ">15s": {
            "count": 13,
            "median_s": 0.5943100838921964,
            "p90_s": 0.7347869073972106
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
      "run": "runs/segment-merge/e2e-segmerge+sft2-qwen.jsonl",
      "system": "segmerge+sft2-qwen",
      "stage": "e2e",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 84,
        "substitutions": 25,
        "insertions": 23,
        "deletions": 36,
        "reference_characters": 2330,
        "rate": 0.036051502145922745
      },
      "raw_cer": null,
      "terms": {
        "correct": 58,
        "total": 67,
        "accuracy": 0.8656716417910447,
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
            "edit_errors": 15,
            "substitutions": 1,
            "insertions": 3,
            "deletions": 11,
            "reference_characters": 440,
            "rate": 0.03409090909090909
          },
          "exact_matches": 4,
          "exact_match_rate": 0.4,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 36,
            "substitutions": 12,
            "insertions": 16,
            "deletions": 8,
            "reference_characters": 510,
            "rate": 0.07058823529411765
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": 0,
          "manifest_count": 11
        },
        "list": {
          "count": 10,
          "cer": {
            "edit_errors": 15,
            "substitutions": 2,
            "insertions": 3,
            "deletions": 10,
            "reference_characters": 601,
            "rate": 0.024958402662229616
          },
          "exact_matches": 3,
          "exact_match_rate": 0.3,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 1,
            "substitutions": 0,
            "insertions": 1,
            "deletions": 0,
            "reference_characters": 367,
            "rate": 0.0027247956403269754
          },
          "exact_matches": 7,
          "exact_match_rate": 0.875,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 21,
            "substitutions": 2,
            "insertions": 14,
            "deletions": 5,
            "reference_characters": 390,
            "rate": 0.05384615384615385
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
          "median_s": 0.4486480209743604,
          "p90_s": 0.6327367673395202
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.16977333405520767,
            "p90_s": 0.16977333405520767
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.3648195420973934,
            "p90_s": 0.5709855624591
          },
          ">15s": {
            "count": 13,
            "median_s": 0.6151147920172662,
            "p90_s": 0.7337402747943997
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
