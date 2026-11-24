| 系統 | stage | 件数 | CER（ASRは読み揃え、E2Eはtarget） | 読み揃え前CER（ASR） | 用語正答率 | 緩い正答率（ASR） | 話していない用語の挿入数 | フィラー残存率 | 遅延中央値 / p90 (秒) | 長さ不明で音声長別遅延から除外 | ≤5秒 中央値 / p90 | 5–15秒 中央値 / p90 | >15秒 中央値 / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0 | asr | 50/50 | 376/2953 (12.73%; 置換 198、挿入 19、削除 159) | 580/2876 (20.17%; 置換 378、挿入 19、削除 183) | 0/67 (0.00%) | 18/67 (26.87%) | 0 | 80/98 (81.63%) | 0.110 / 0.168 | 0 | 0.053 / 0.053 | 0.103 / 0.135 | 0.159 / 0.208 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | 50/50 | 412/2953 (13.95%; 置換 224、挿入 25、削除 163) | 380/2876 (13.21%; 置換 222、挿入 23、削除 135) | 44/67 (65.67%) | 45/67 (67.16%) | 14 | 80/98 (81.63%) | 0.227 / 0.329 | 0 | 0.056 / 0.056 | 0.205 / 0.271 | 0.326 / 0.419 |
| qwen3-asr-1.7b-8bit | asr | 50/50 | 335/2953 (11.34%; 置換 186、挿入 22、削除 127) | 546/2876 (18.98%; 置換 373、挿入 23、削除 150) | 21/67 (31.34%) | 39/67 (58.21%) | 5 | 95/98 (96.94%) | 0.832 / 1.298 | 0 | 0.465 / 0.465 | 0.691 / 1.087 | 1.195 / 1.458 |
| qwen3-asr-1.7b-8bit+twopass | asr | 50/50 | 359/2953 (12.16%; 置換 200、挿入 24、削除 135) | 431/2876 (14.99%; 置換 289、挿入 21、削除 121) | 32/67 (47.76%) | 42/67 (62.69%) | 5 | 93/98 (94.90%) | 1.658 / 2.492 | 0 | 0.496 / 0.496 | 1.337 / 2.273 | 2.478 / 2.800 |
| whisper-large-v3-turbo.greedy | asr | 50/50 | 410/2953 (13.88%; 置換 100、挿入 30、削除 280) | 510/2876 (17.73%; 置換 189、挿入 26、削除 295) | 35/67 (52.24%) | 47/67 (70.15%) | 4 | 61/98 (62.24%) | 0.751 / 0.852 | 0 | 0.704 / 0.704 | 0.741 / 0.823 | 0.844 / 0.887 |
| whisper-large-v3-turbo.greedy+twopass | asr | 50/50 | 443/2953 (15.00%; 置換 117、挿入 39、削除 287) | 392/2876 (13.63%; 置換 94、挿入 35、削除 263) | 47/67 (70.15%) | 48/67 (71.64%) | 7 | 54/98 (55.10%) | 1.488 / 1.716 | 0 | 0.712 / 0.712 | 1.457 / 1.663 | 1.685 / 1.761 |

タグ別集計
| 系統 | stage | tag | 件数（評価/manifest） | CER | 正規化後完全一致率 | 応答の疑い |
| --- | --- | --- | --- | --- | --- | --- |
| haas-ja-v1.0-speechcpp-q8_0 | asr | english_phrase | 10/10 | 209/437 (47.83%; 置換 116、挿入 78、削除 15) | 0/10 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | instruction_like | 11/11 | 235/512 (45.90%; 置換 102、挿入 121、削除 12) | 0/11 (0.00%) | 1 |
| haas-ja-v1.0-speechcpp-q8_0 | asr | list | 11/11 | 189/653 (28.94%; 置換 64、挿入 112、削除 13) | 0/11 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas-ja-v1.0-speechcpp-q8_0 | asr | self_correction | 8/8 | 278/391 (71.10%; 置換 99、挿入 171、削除 8) | 0/8 (0.00%)（言い直しの正答率） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | english_phrase | 10/10 | 175/437 (40.05%; 置換 78、挿入 84、削除 13) | 0/10 (0.00%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | instruction_like | 11/11 | 192/512 (37.50%; 置換 53、挿入 132、削除 7) | 1/11 (9.09%) | 1 |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | list | 11/11 | 175/653 (26.80%; 置換 61、挿入 111、削除 3) | 2/11 (18.18%) | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | no_change | 8/8 | 10/372 (2.69%; 置換 2、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| haas-ja-v1.0-speechcpp-q8_0+twopass | asr | self_correction | 8/8 | 230/391 (58.82%; 置換 36、挿入 191、削除 3) | 0/8 (0.00%)（言い直しの正答率） | — |
| qwen3-asr-1.7b-8bit | asr | english_phrase | 10/10 | 222/437 (50.80%; 置換 113、挿入 94、削除 15) | 0/10 (0.00%) | — |
| qwen3-asr-1.7b-8bit | asr | instruction_like | 11/11 | 243/512 (47.46%; 置換 116、挿入 115、削除 12) | 0/11 (0.00%) | 1 |
| qwen3-asr-1.7b-8bit | asr | list | 11/11 | 204/653 (31.24%; 置換 68、挿入 123、削除 13) | 0/11 (0.00%) | — |
| qwen3-asr-1.7b-8bit | asr | no_change | 8/8 | 14/372 (3.76%; 置換 5、挿入 2、削除 7) | 4/8 (50.00%)（無変更の保持） | — |
| qwen3-asr-1.7b-8bit | asr | self_correction | 8/8 | 280/391 (71.61%; 置換 92、挿入 181、削除 7) | 0/8 (0.00%)（言い直しの正答率） | — |
| qwen3-asr-1.7b-8bit+twopass | asr | english_phrase | 10/10 | 201/437 (46.00%; 置換 97、挿入 89、削除 15) | 0/10 (0.00%) | — |
| qwen3-asr-1.7b-8bit+twopass | asr | instruction_like | 11/11 | 205/512 (40.04%; 置換 61、挿入 136、削除 8) | 0/11 (0.00%) | 1 |
| qwen3-asr-1.7b-8bit+twopass | asr | list | 11/11 | 176/653 (26.95%; 置換 42、挿入 126、削除 8) | 0/11 (0.00%) | — |
| qwen3-asr-1.7b-8bit+twopass | asr | no_change | 8/8 | 14/372 (3.76%; 置換 5、挿入 2、削除 7) | 4/8 (50.00%)（無変更の保持） | — |
| qwen3-asr-1.7b-8bit+twopass | asr | self_correction | 8/8 | 269/391 (68.80%; 置換 66、挿入 195、削除 8) | 0/8 (0.00%)（言い直しの正答率） | — |
| whisper-large-v3-turbo.greedy | asr | english_phrase | 10/10 | 115/437 (26.32%; 置換 54、挿入 52、削除 9) | 1/10 (10.00%) | — |
| whisper-large-v3-turbo.greedy | asr | instruction_like | 11/11 | 158/512 (30.86%; 置換 61、挿入 90、削除 7) | 0/11 (0.00%) | 1 |
| whisper-large-v3-turbo.greedy | asr | list | 11/11 | 102/653 (15.62%; 置換 38、挿入 58、削除 6) | 1/11 (9.09%) | — |
| whisper-large-v3-turbo.greedy | asr | no_change | 8/8 | 11/372 (2.96%; 置換 3、挿入 1、削除 7) | 5/8 (62.50%)（無変更の保持） | — |
| whisper-large-v3-turbo.greedy | asr | self_correction | 8/8 | 188/391 (48.08%; 置換 44、挿入 138、削除 6) | 0/8 (0.00%)（言い直しの正答率） | — |
| whisper-large-v3-turbo.greedy+twopass | asr | english_phrase | 10/10 | 99/437 (22.65%; 置換 33、挿入 64、削除 2) | 1/10 (10.00%) | — |
| whisper-large-v3-turbo.greedy+twopass | asr | instruction_like | 11/11 | 129/512 (25.20%; 置換 17、挿入 109、削除 3) | 2/11 (18.18%) | 1 |
| whisper-large-v3-turbo.greedy+twopass | asr | list | 11/11 | 70/653 (10.72%; 置換 12、挿入 57、削除 1) | 3/11 (27.27%) | — |
| whisper-large-v3-turbo.greedy+twopass | asr | no_change | 8/8 | 13/372 (3.49%; 置換 4、挿入 3、削除 6) | 5/8 (62.50%)（無変更の保持） | — |
| whisper-large-v3-turbo.greedy+twopass | asr | self_correction | 8/8 | 185/391 (47.31%; 置換 17、挿入 162、削除 6) | 0/8 (0.00%)（言い直しの正答率） | — |

JSON:
```json
{
  "manifest": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/scripted.jsonl",
  "results": [
    {
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/haas-ja-v1.0-speechcpp-q8_0.jsonl",
      "system": "haas-ja-v1.0-speechcpp-q8_0",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 376,
        "substitutions": 198,
        "insertions": 19,
        "deletions": 159,
        "reference_characters": 2953,
        "rate": 0.12732814087368777
      },
      "raw_cer": {
        "edit_errors": 580,
        "substitutions": 378,
        "insertions": 19,
        "deletions": 183,
        "reference_characters": 2876,
        "rate": 0.20166898470097358
      },
      "terms": {
        "correct": 0,
        "total": 67,
        "accuracy": 0.0,
        "loose_correct": 18,
        "loose_accuracy": 0.26865671641791045
      },
      "inserted_terms": {
        "count": 0
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
            "edit_errors": 209,
            "substitutions": 116,
            "insertions": 78,
            "deletions": 15,
            "reference_characters": 437,
            "rate": 0.4782608695652174
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 235,
            "substitutions": 102,
            "insertions": 121,
            "deletions": 12,
            "reference_characters": 512,
            "rate": 0.458984375
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 189,
            "substitutions": 64,
            "insertions": 112,
            "deletions": 13,
            "reference_characters": 653,
            "rate": 0.2894333843797856
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
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
            "edit_errors": 278,
            "substitutions": 99,
            "insertions": 171,
            "deletions": 8,
            "reference_characters": 391,
            "rate": 0.710997442455243
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
          "median_s": 0.10952018795069307,
          "p90_s": 0.16750249589094895
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.05279104202054441,
            "p90_s": 0.05279104202054441
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.10321118746651337,
            "p90_s": 0.13505808351328596
          },
          ">15s": {
            "count": 13,
            "median_s": 0.15918279206380248,
            "p90_s": 0.20783024141564968
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
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/haas-ja-v1.0-speechcpp-q8_0+twopass.jsonl",
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
        "loose_accuracy": 0.6716417910447762
      },
      "inserted_terms": {
        "count": 14
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
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/qwen3-asr-1.7b-8bit.jsonl",
      "system": "qwen3-asr-1.7b-8bit",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 335,
        "substitutions": 186,
        "insertions": 22,
        "deletions": 127,
        "reference_characters": 2953,
        "rate": 0.11344395529969523
      },
      "raw_cer": {
        "edit_errors": 546,
        "substitutions": 373,
        "insertions": 23,
        "deletions": 150,
        "reference_characters": 2876,
        "rate": 0.1898470097357441
      },
      "terms": {
        "correct": 21,
        "total": 67,
        "accuracy": 0.31343283582089554,
        "loose_correct": 39,
        "loose_accuracy": 0.582089552238806
      },
      "inserted_terms": {
        "count": 5
      },
      "fillers": {
        "residual_count": 95,
        "manifest_count": 98,
        "residual_rate": 0.9693877551020408
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 222,
            "substitutions": 113,
            "insertions": 94,
            "deletions": 15,
            "reference_characters": 437,
            "rate": 0.5080091533180778
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 243,
            "substitutions": 116,
            "insertions": 115,
            "deletions": 12,
            "reference_characters": 512,
            "rate": 0.474609375
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 204,
            "substitutions": 68,
            "insertions": 123,
            "deletions": 13,
            "reference_characters": 653,
            "rate": 0.3124042879019908
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
            "edit_errors": 280,
            "substitutions": 92,
            "insertions": 181,
            "deletions": 7,
            "reference_characters": 391,
            "rate": 0.7161125319693095
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
          "median_s": 0.8316482079681009,
          "p90_s": 1.2978510997025297
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.4654393750242889,
            "p90_s": 0.4654393750242889
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.6905748964636587,
            "p90_s": 1.0871210415498354
          },
          ">15s": {
            "count": 13,
            "median_s": 1.1946262080455199,
            "p90_s": 1.458140608528629
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
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/qwen3-asr-1.7b-8bit+twopass.jsonl",
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
        "loose_accuracy": 0.6268656716417911
      },
      "inserted_terms": {
        "count": 5
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
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    },
    {
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/whisper-large-v3-turbo.greedy.jsonl",
      "system": "whisper-large-v3-turbo.greedy",
      "stage": "asr",
      "utterances": {
        "manifest": 50,
        "evaluated": 50,
        "missing_predictions": 0
      },
      "cer": {
        "edit_errors": 410,
        "substitutions": 100,
        "insertions": 30,
        "deletions": 280,
        "reference_characters": 2953,
        "rate": 0.1388418557399255
      },
      "raw_cer": {
        "edit_errors": 510,
        "substitutions": 189,
        "insertions": 26,
        "deletions": 295,
        "reference_characters": 2876,
        "rate": 0.17732962447844228
      },
      "terms": {
        "correct": 35,
        "total": 67,
        "accuracy": 0.5223880597014925,
        "loose_correct": 47,
        "loose_accuracy": 0.7014925373134329
      },
      "inserted_terms": {
        "count": 4
      },
      "fillers": {
        "residual_count": 61,
        "manifest_count": 98,
        "residual_rate": 0.6224489795918368
      },
      "tags": {
        "english_phrase": {
          "count": 10,
          "cer": {
            "edit_errors": 115,
            "substitutions": 54,
            "insertions": 52,
            "deletions": 9,
            "reference_characters": 437,
            "rate": 0.2631578947368421
          },
          "exact_matches": 1,
          "exact_match_rate": 0.1,
          "suspected_responses": null,
          "manifest_count": 10
        },
        "instruction_like": {
          "count": 11,
          "cer": {
            "edit_errors": 158,
            "substitutions": 61,
            "insertions": 90,
            "deletions": 7,
            "reference_characters": 512,
            "rate": 0.30859375
          },
          "exact_matches": 0,
          "exact_match_rate": 0.0,
          "suspected_responses": 1,
          "manifest_count": 11
        },
        "list": {
          "count": 11,
          "cer": {
            "edit_errors": 102,
            "substitutions": 38,
            "insertions": 58,
            "deletions": 6,
            "reference_characters": 653,
            "rate": 0.1562021439509954
          },
          "exact_matches": 1,
          "exact_match_rate": 0.09090909090909091,
          "suspected_responses": null,
          "manifest_count": 11
        },
        "no_change": {
          "count": 8,
          "cer": {
            "edit_errors": 11,
            "substitutions": 3,
            "insertions": 1,
            "deletions": 7,
            "reference_characters": 372,
            "rate": 0.02956989247311828
          },
          "exact_matches": 5,
          "exact_match_rate": 0.625,
          "suspected_responses": null,
          "manifest_count": 8
        },
        "self_correction": {
          "count": 8,
          "cer": {
            "edit_errors": 188,
            "substitutions": 44,
            "insertions": 138,
            "deletions": 6,
            "reference_characters": 391,
            "rate": 0.48081841432225064
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
          "median_s": 0.7514081664849073,
          "p90_s": 0.8515716955531388
        },
        "duration_groups": {
          "<=5s": {
            "count": 1,
            "median_s": 0.7036736250156537,
            "p90_s": 0.7036736250156537
          },
          "5-15s": {
            "count": 36,
            "median_s": 0.7413256045547314,
            "p90_s": 0.8230617294902913
          },
          ">15s": {
            "count": 13,
            "median_s": 0.8437014169758186,
            "p90_s": 0.8869396663969383
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
      "run": "/private/tmp/claude-501/-Users-marutyan-PrivateDev-voiceIME/3732b70c-6c15-4d0c-9def-cf3935cef9e5/scratchpad/asr/devuser/whisper-large-v3-turbo.greedy+twopass.jsonl",
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
        "loose_accuracy": 0.7164179104477612
      },
      "inserted_terms": {
        "count": 7
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
        "unknown_ids": 0,
        "missing_hyp": 0,
        "duplicate_ids": 0
      }
    }
  ]
}
```
