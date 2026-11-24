| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数（ASR: spoken_textのsurface/readings、E2E: target_textのterms基準） | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 50/50 | 412/2953 (13.95%; 置換 224、挿入 25、削除 163) | 380/2876 (13.21%; 置換 222、挿入 23、削除 135) | 44/67 (65.67%) | 45/67 (67.16%) | 0 | 80/98 (81.63%) | 0.227 / 0.329 | 0 | 0.056 / 0.056 | 0.205 / 0.271 | 0.326 / 0.419 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 50/50 | 416/2953 (14.09%; 置換 229、挿入 22、削除 165) | 455/2876 (15.82%; 置換 282、挿入 20、削除 153) | 28/67 (41.79%) | 33/67 (49.25%) | 0 | 80/98 (81.63%) | 0.224 / 0.326 | 0 | 0.056 / 0.056 | 0.203 / 0.277 | 0.318 / 0.432 |
| qwen3-asr-1.7b-8bit+twopass | asr | 50/50 | 359/2953 (12.16%; 置換 200、挿入 24、削除 135) | 431/2876 (14.99%; 置換 289、挿入 21、削除 121) | 32/67 (47.76%) | 42/67 (62.69%) | 0 | 93/98 (94.90%) | 1.658 / 2.492 | 0 | 0.496 / 0.496 | 1.337 / 2.273 | 2.478 / 2.800 |
| qwen3-asr-1.7b-8bit+twopass | asr | 50/50 | 363/2953 (12.29%; 置換 205、挿入 21、削除 137) | 459/2876 (15.96%; 置換 305、挿入 22、削除 132) | 30/67 (44.78%) | 41/67 (61.19%) | 0 | 92/98 (93.88%) | 1.678 / 2.525 | 0 | 0.448 / 0.448 | 1.320 / 2.234 | 2.422 / 2.936 |
| whisper-large-v3-turbo.greedy+twopass | asr | 50/50 | 443/2953 (15.00%; 置換 117、挿入 39、削除 287) | 392/2876 (13.63%; 置換 94、挿入 35、削除 263) | 47/67 (70.15%) | 48/67 (71.64%) | 0 | 54/98 (55.10%) | 1.488 / 1.716 | 0 | 0.712 / 0.712 | 1.457 / 1.663 | 1.685 / 1.761 |
| whisper-large-v3-turbo.greedy+twopass | asr | 50/50 | 449/2953 (15.20%; 置換 139、挿入 47、削除 263) | 417/2876 (14.50%; 置換 113、挿入 41、削除 263) | 47/67 (70.15%) | 49/67 (73.13%) | 0 | 55/98 (56.12%) | 1.509 / 1.712 | 0 | 0.694 / 0.694 | 1.448 / 1.649 | 1.651 / 1.742 |

用語正答率（見えない用語 / それ以外）
| 系統 | stage | 全体 | 見えない用語 | それ以外 | 緩い正答率：見えない用語（ASR） | 緩い正答率：それ以外（ASR） |
| --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 44/67 (65.67%) | 16/20 (80.00%) | 28/47 (59.57%) | 17/20 (85.00%) | 28/47 (59.57%) |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 28/67 (41.79%) | 0/20 (0.00%) | 28/47 (59.57%) | 5/20 (25.00%) | 28/47 (59.57%) |
| qwen3-asr-1.7b-8bit+twopass | asr | 32/67 (47.76%) | 10/20 (50.00%) | 22/47 (46.81%) | 12/20 (60.00%) | 30/47 (63.83%) |
| qwen3-asr-1.7b-8bit+twopass | asr | 30/67 (44.78%) | 7/20 (35.00%) | 23/47 (48.94%) | 10/20 (50.00%) | 31/47 (65.96%) |
| whisper-large-v3-turbo.greedy+twopass | asr | 47/67 (70.15%) | 12/20 (60.00%) | 35/47 (74.47%) | 12/20 (60.00%) | 36/47 (76.60%) |
| whisper-large-v3-turbo.greedy+twopass | asr | 47/67 (70.15%) | 11/20 (55.00%) | 36/47 (76.60%) | 12/20 (60.00%) | 37/47 (78.72%) |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | english_phrase | 10/10 | 175/437 (40.05%; 置換 78、挿入 84、削除 13) | 0/10 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | instruction_like | 11/11 | 192/512 (37.50%; 置換 53、挿入 132、削除 7) | 1/11 (9.09%) | 1 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | self_correction | 8/8 | 230/391 (58.82%; 置換 36、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | english_phrase | 10/10 | 186/437 (42.56%; 置換 93、挿入 80、削除 13) | 0/10 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | instruction_like | 11/11 | 205/512 (40.04%; 置換 73、挿入 125、削除 7) | 1/11 (9.09%) | 1 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | list | 11/11 | 186/653 (28.48%; 置換 69、挿入 111、削除 6) | 1/11 (9.09%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | self_correction | 8/8 | 244/391 (62.40%; 置換 61、挿入 180、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| qwen3-asr-1.7b-8bit+twopass | asr | english_phrase | 10/10 | 201/437 (46.00%; 置換 97、挿入 89、削除 15) | 0/10 (0.00%) | — |
| qwen3-asr-1.7b-8bit+twopass | asr | instruction_like | 11/11 | 205/512 (40.04%; 置換 61、挿入 136、削除 8) | 0/11 (0.00%) | 1 |
| qwen3-asr-1.7b-8bit+twopass | asr | list | 11/11 | 176/653 (26.95%; 置換 42、挿入 126、削除 8) | 0/11 (0.00%) | — |
| qwen3-asr-1.7b-8bit+twopass | asr | no_change | 8/8 | 14/372 (3.76%; 置換 5、挿入 2、削除 7) | 4/8 (50.00%)（無変更の保持） | — |
| qwen3-asr-1.7b-8bit+twopass | asr | self_correction | 8/8 | 269/391 (68.80%; 置換 66、挿入 195、削除 8) | 0/8 (0.00%)（言い直しの正答率） | — |
| qwen3-asr-1.7b-8bit+twopass | asr | english_phrase | 10/10 | 206/437 (47.14%; 置換 101、挿入 90、削除 15) | 0/10 (0.00%) | — |
| qwen3-asr-1.7b-8bit+twopass | asr | instruction_like | 11/11 | 205/512 (40.04%; 置換 71、挿入 125、削除 9) | 0/11 (0.00%) | 1 |
| qwen3-asr-1.7b-8bit+twopass | asr | list | 11/11 | 176/653 (26.95%; 置換 42、挿入 126、削除 8) | 0/11 (0.00%) | — |
| qwen3-asr-1.7b-8bit+twopass | asr | no_change | 8/8 | 14/372 (3.76%; 置換 5、挿入 2、削除 7) | 4/8 (50.00%)（無変更の保持） | — |
| qwen3-asr-1.7b-8bit+twopass | asr | self_correction | 8/8 | 269/391 (68.80%; 置換 77、挿入 184、削除 8) | 0/8 (0.00%)（言い直しの正答率） | — |
| whisper-large-v3-turbo.greedy+twopass | asr | english_phrase | 10/10 | 99/437 (22.65%; 置換 33、挿入 64、削除 2) | 1/10 (10.00%) | — |
| whisper-large-v3-turbo.greedy+twopass | asr | instruction_like | 11/11 | 129/512 (25.20%; 置換 17、挿入 109、削除 3) | 2/11 (18.18%) | 1 |
| whisper-large-v3-turbo.greedy+twopass | asr | list | 11/11 | 70/653 (10.72%; 置換 12、挿入 57、削除 1) | 3/11 (27.27%) | — |
| whisper-large-v3-turbo.greedy+twopass | asr | no_change | 8/8 | 13/372 (3.49%; 置換 4、挿入 3、削除 6) | 5/8 (62.50%)（無変更の保持） | — |
| whisper-large-v3-turbo.greedy+twopass | asr | self_correction | 8/8 | 185/391 (47.31%; 置換 17、挿入 162、削除 6) | 0/8 (0.00%)（言い直しの正答率） | — |
| whisper-large-v3-turbo.greedy+twopass | asr | english_phrase | 10/10 | 114/437 (26.09%; 置換 49、挿入 63、削除 2) | 1/10 (10.00%) | — |
| whisper-large-v3-turbo.greedy+twopass | asr | instruction_like | 11/11 | 152/512 (29.69%; 置換 29、挿入 120、削除 3) | 2/11 (18.18%) | 1 |
| whisper-large-v3-turbo.greedy+twopass | asr | list | 11/11 | 65/653 (9.95%; 置換 13、挿入 52、削除 0) | 3/11 (27.27%) | — |
| whisper-large-v3-turbo.greedy+twopass | asr | no_change | 8/8 | 13/372 (3.49%; 置換 4、挿入 3、削除 6) | 5/8 (62.50%)（無変更の保持） | — |
| whisper-large-v3-turbo.greedy+twopass | asr | self_correction | 8/8 | 181/391 (46.29%; 置換 20、挿入 155、削除 6) | 0/8 (0.00%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/metal-eval/devuser-scripted.jsonl",
  "results": [
    {
      "run": "runs/asr-dev-user/haas-ja-v1.0-speechcpp-q8_0+twopass.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0+twopass",
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
        "loose_accuracy": 0.6716417910447762,
        "unseen": {
          "correct": 16,
          "total": 20,
          "accuracy": 0.8,
          "loose_correct": 17,
          "loose_accuracy": 0.85
        },
        "seen": {
          "correct": 28,
          "total": 47,
          "accuracy": 0.5957446808510638,
          "loose_correct": 28,
          "loose_accuracy": 0.5957446808510638
        }
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
      "run": "runs/base-compare/devuser-haas2p-excl.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 416,
        "substitutions": 229,
        "insertions": 22,
        "deletions": 165,
        "reference_characters": 2953,
        "rate": 0.14087368777514392
      },
      "raw_cer": {
        "edit_errors": 455,
        "substitutions": 282,
        "insertions": 20,
        "deletions": 153,
        "reference_characters": 2876,
        "rate": 0.15820584144645342
      },
      "terms": {
        "correct": 28,
        "total": 67,
        "accuracy": 0.417910447761194,
        "loose_correct": 33,
        "loose_accuracy": 0.4925373134328358,
        "unseen": {
          "correct": 0,
          "total": 20,
          "accuracy": 0.0,
          "loose_correct": 5,
          "loose_accuracy": 0.25
        },
        "seen": {
          "correct": 28,
          "total": 47,
          "accuracy": 0.5957446808510638,
          "loose_correct": 28,
          "loose_accuracy": 0.5957446808510638
        }
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
      "run": "runs/asr-dev-user/qwen3-asr-1.7b-8bit+twopass.jsonl",
      "system": "qwen3-asr-1.7b-8bit+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 359,
        "substitutions": 200,
        "insertions": 24,
        "deletions": 135,
        "reference_characters": 2953,
        "rate": 0.12157128344056892
      },
      "raw_cer": {
        "edit_errors": 431,
        "substitutions": 289,
        "insertions": 21,
        "deletions": 121,
        "reference_characters": 2876,
        "rate": 0.14986091794158554
      },
      "terms": {
        "correct": 32,
        "total": 67,
        "accuracy": 0.47761194029850745,
        "loose_correct": 42,
        "loose_accuracy": 0.6268656716417911,
        "unseen": {
          "correct": 10,
          "total": 20,
          "accuracy": 0.5,
          "loose_correct": 12,
          "loose_accuracy": 0.6
        },
        "seen": {
          "correct": 22,
          "total": 47,
          "accuracy": 0.46808510638297873,
          "loose_correct": 30,
          "loose_accuracy": 0.6382978723404256
        }
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 93,
        "manifest_count": 98,
        "residual_rate": 0.9489795918367347
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 201,
            "substitutions": 97,
            "insertions": 89,
            "deletions": 15,
            "reference_characters": 437,
            "rate": 0.459954233409611
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
            "substitutions": 61,
            "insertions": 136,
            "deletions": 8,
            "reference_characters": 512,
            "rate": 0.400390625
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 176,
            "substitutions": 42,
            "insertions": 126,
            "deletions": 8,
            "reference_characters": 653,
            "rate": 0.26952526799387444
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 14,
            "substitutions": 5,
            "insertions": 2,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.03763440860215054
          },
          "exact_matches": 4,
          "exact_match_rate": 0.5,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 269,
            "substitutions": 66,
            "insertions": 195,
            "deletions": 8,
            "reference_characters": 391,
            "rate": 0.6879795396419437
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
          "median_s": 1.6582822084310465,
          "p90_s": 2.4915857500047425
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.4962948750471696,
            "p90_s": 0.4962948750471696
          },
          "5-15s": {
            "count": 36,
            "median_s": 1.3367846040637232,
            "p90_s": 2.273380979488138
          },
          ">15s": {
            "count": 13,
            "median_s": 2.4779629580443725,
            "p90_s": 2.7996500921901317
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
      "run": "runs/base-compare/devuser-qwen3asr1.7b-8bit-2p-excl.jsonl",
      "system": "qwen3-asr-1.7b-8bit+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 363,
        "substitutions": 205,
        "insertions": 21,
        "deletions": 137,
        "reference_characters": 2953,
        "rate": 0.12292583813071453
      },
      "raw_cer": {
        "edit_errors": 459,
        "substitutions": 305,
        "insertions": 22,
        "deletions": 132,
        "reference_characters": 2876,
        "rate": 0.15959666203059805
      },
      "terms": {
        "correct": 30,
        "total": 67,
        "accuracy": 0.44776119402985076,
        "loose_correct": 41,
        "loose_accuracy": 0.6119402985074627,
        "unseen": {
          "correct": 7,
          "total": 20,
          "accuracy": 0.35,
          "loose_correct": 10,
          "loose_accuracy": 0.5
        },
        "seen": {
          "correct": 23,
          "total": 47,
          "accuracy": 0.48936170212765956,
          "loose_correct": 31,
          "loose_accuracy": 0.6595744680851063
        }
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 92,
        "manifest_count": 98,
        "residual_rate": 0.9387755102040817
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 206,
            "substitutions": 101,
            "insertions": 90,
            "deletions": 15,
            "reference_characters": 437,
            "rate": 0.47139588100686497
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
            "substitutions": 71,
            "insertions": 125,
            "deletions": 9,
            "reference_characters": 512,
            "rate": 0.400390625
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 176,
            "substitutions": 42,
            "insertions": 126,
            "deletions": 8,
            "reference_characters": 653,
            "rate": 0.26952526799387444
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 14,
            "substitutions": 5,
            "insertions": 2,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.03763440860215054
          },
          "exact_matches": 4,
          "exact_match_rate": 0.5,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 269,
            "substitutions": 77,
            "insertions": 184,
            "deletions": 8,
            "reference_characters": 391,
            "rate": 0.6879795396419437
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
          "median_s": 1.6778113335021771,
          "p90_s": 2.5252465792000294
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.44806345796678215,
            "p90_s": 0.44806345796678215
          },
          "5-15s": {
            "count": 36,
            "median_s": 1.3203538545640185,
            "p90_s": 2.2342196039971896
          },
          ">15s": {
            "count": 13,
            "median_s": 2.4215465830639005,
            "p90_s": 2.935805925005116
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
      "run": "runs/asr-dev-user/whisper-large-v3-turbo.greedy+twopass.jsonl",
      "system": "whisper-large-v3-turbo.greedy+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 443,
        "substitutions": 117,
        "insertions": 39,
        "deletions": 287,
        "reference_characters": 2953,
        "rate": 0.1500169319336268
      },
      "raw_cer": {
        "edit_errors": 392,
        "substitutions": 94,
        "insertions": 35,
        "deletions": 263,
        "reference_characters": 2876,
        "rate": 0.13630041724617525
      },
      "terms": {
        "correct": 47,
        "total": 67,
        "accuracy": 0.7014925373134329,
        "loose_correct": 48,
        "loose_accuracy": 0.7164179104477612,
        "unseen": {
          "correct": 12,
          "total": 20,
          "accuracy": 0.6,
          "loose_correct": 12,
          "loose_accuracy": 0.6
        },
        "seen": {
          "correct": 35,
          "total": 47,
          "accuracy": 0.7446808510638298,
          "loose_correct": 36,
          "loose_accuracy": 0.7659574468085106
        }
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 54,
        "manifest_count": 98,
        "residual_rate": 0.5510204081632653
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 99,
            "substitutions": 33,
            "insertions": 64,
            "deletions": 2,
            "reference_characters": 437,
            "rate": 0.22654462242562928
          },
          "exact_matches": 1,
          "exact_match_rate": 0.1,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 129,
            "substitutions": 17,
            "insertions": 109,
            "deletions": 3,
            "reference_characters": 512,
            "rate": 0.251953125
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 70,
            "substitutions": 12,
            "insertions": 57,
            "deletions": 1,
            "reference_characters": 653,
            "rate": 0.10719754977029096
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 13,
            "substitutions": 4,
            "insertions": 3,
            "deletions": 6,
            "reference_characters": 372,
            "rate": 0.03494623655913978
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 185,
            "substitutions": 17,
            "insertions": 162,
            "deletions": 6,
            "reference_characters": 391,
            "rate": 0.4731457800511509
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
          "median_s": 1.488207146001514,
          "p90_s": 1.7160753375501372
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.7124674589140341,
            "p90_s": 0.7124674589140341
          },
          "5-15s": {
            "count": 36,
            "median_s": 1.457157916505821,
            "p90_s": 1.6627896670252085
          },
          ">15s": {
            "count": 13,
            "median_s": 1.685340499971062,
            "p90_s": 1.7609360500471667
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
      "run": "runs/base-compare/devuser-whisperturbo-greedy-2p-excl.jsonl",
      "system": "whisper-large-v3-turbo.greedy+twopass",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 449,
        "substitutions": 139,
        "insertions": 47,
        "deletions": 263,
        "reference_characters": 2953,
        "rate": 0.15204876396884523
      },
      "raw_cer": {
        "edit_errors": 417,
        "substitutions": 113,
        "insertions": 41,
        "deletions": 263,
        "reference_characters": 2876,
        "rate": 0.1449930458970793
      },
      "terms": {
        "correct": 47,
        "total": 67,
        "accuracy": 0.7014925373134329,
        "loose_correct": 49,
        "loose_accuracy": 0.7313432835820896,
        "unseen": {
          "correct": 11,
          "total": 20,
          "accuracy": 0.55,
          "loose_correct": 12,
          "loose_accuracy": 0.6
        },
        "seen": {
          "correct": 36,
          "total": 47,
          "accuracy": 0.7659574468085106,
          "loose_correct": 37,
          "loose_accuracy": 0.7872340425531915
        }
      },
      "inserted_terms": {
        "count": 0,
        "basis": "spoken_textに含まれるglossaryのsurface/readings"
      },
      "fillers": {
        "residual_count": 55,
        "manifest_count": 98,
        "residual_rate": 0.5612244897959183
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 114,
            "substitutions": 49,
            "insertions": 63,
            "deletions": 2,
            "reference_characters": 437,
            "rate": 0.2608695652173913
          },
          "exact_matches": 1,
          "exact_match_rate": 0.1,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 152,
            "substitutions": 29,
            "insertions": 120,
            "deletions": 3,
            "reference_characters": 512,
            "rate": 0.296875
          },
          "exact_matches": 2,
          "exact_match_rate": 0.18181818181818182,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 65,
            "substitutions": 13,
            "insertions": 52,
            "deletions": 0,
            "reference_characters": 653,
            "rate": 0.0995405819295559
          },
          "exact_matches": 3,
          "exact_match_rate": 0.2727272727272727,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 13,
            "substitutions": 4,
            "insertions": 3,
            "deletions": 6,
            "reference_characters": 372,
            "rate": 0.03494623655913978
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 181,
            "substitutions": 20,
            "insertions": 155,
            "deletions": 6,
            "reference_characters": 391,
            "rate": 0.4629156010230179
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
          "median_s": 1.508777896000538,
          "p90_s": 1.7122018583468162
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.6943400000454858,
            "p90_s": 0.6943400000454858
          },
          "5-15s": {
            "count": 36,
            "median_s": 1.448412312020082,
            "p90_s": 1.6493216244853102
          },
          ">15s": {
            "count": 13,
            "median_s": 1.6507557498989627,
            "p90_s": 1.7416213090298698
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
