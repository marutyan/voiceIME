"""評価指標の正規化、集計、境界条件を手計算の値で確認する。"""

import json
import wave

import pytest

from voiceime.eval.report import (
    _evaluate_run,
    _load_manifest,
    _markdown_table,
    main as report_main,
)
from voiceime.eval.metrics import (
    calculate_cer,
    calculate_filler_metrics,
    calculate_tag_metrics,
    calculate_term_accuracy,
    calculate_term_accuracy_split,
    count_fillers,
    count_inserted_terms,
    count_residual_fillers,
    normalize_for_cer,
    summarize_latency,
)
from voiceime.eval.term_trace import analyze_term_trace
from voiceime.formatter.glossary import GlossaryEntry


def test_normalize_nfkc_case_punctuation_symbol_and_space() -> None:
    """全角英数字をASCII化し、句読点・記号・空白を除く。"""
    assert normalize_for_cer("ＰｙＴｏｒｃｈ！ ABC，漢字 + １２３　") == "pytorchabc漢字123"
    assert normalize_for_cer("15パーセント") == normalize_for_cer("15%") == "15"
    assert normalize_for_cer("使うとき") == normalize_for_cer("使う時")


def test_cer_is_micro_averaged_across_japanese_and_english() -> None:
    """各発話を平均せず、正解文字数5に対する誤り1で集計する。"""
    result = calculate_cer(["ＡＢＣ！", "話す"], ["abc?", "話"])

    assert result == {
        "edit_errors": 1,
        "substitutions": 0,
        "insertions": 0,
        "deletions": 1,
        "reference_characters": 5,
        "rate": 0.2,
    }


def test_cer_breaks_errors_into_substitutions_insertions_and_deletions() -> None:
    """置換1、挿入2、削除3を合算し、正解12文字に対するCERを出す。"""
    result = calculate_cer(
        ["猫犬", "API", "feature"],
        ["猫虎", "APIIx", "feat"],
    )

    assert result == {
        "edit_errors": 6,
        "substitutions": 1,
        "insertions": 2,
        "deletions": 3,
        "reference_characters": 12,
        "rate": 0.5,
    }


def test_term_accuracy_counts_repeated_reference_terms_by_occurrence() -> None:
    """正解に2回あるDatasetを出力が1回だけ含むため、1回分だけ数える。"""
    result = calculate_term_accuracy(
        ["PyTorch", "Dataset", "Dataset"],
        [
            {"surface": "PyTorch", "readings": ["パイトーチ"]},
            {"surface": "Dataset", "readings": ["データセット"]},
        ],
        "パイトーチ Dataset",
    )

    assert result == {
        "correct": 1,
        "total": 3,
        "accuracy": 1 / 3,
        "loose_correct": 2,
        "loose_accuracy": 2 / 3,
    }


def test_term_accuracy_ignores_singular_reading_field() -> None:
    """旧reading単数形は使わず、正確なsurfaceだけを正答にする。"""
    result = calculate_term_accuracy(
        ["Torch"], [{"surface": "Torch", "reading": "トーチ"}], "トーチ"
    )

    assert result == {
        "correct": 0,
        "total": 1,
        "accuracy": 0.0,
        "loose_correct": 0,
        "loose_accuracy": 0.0,
    }


def test_term_accuracy_accepts_each_reading_in_plural_list() -> None:
    """surfaceに対応するreadingsの2つ目も緩い一致として認める。"""
    result = calculate_term_accuracy(
        ["Torch"],
        [{"surface": "Torch", "readings": ["トーチ", "トルチ"]}],
        "トルチ",
    )

    assert result == {
        "correct": 0,
        "total": 1,
        "accuracy": 0.0,
        "loose_correct": 1,
        "loose_accuracy": 1.0,
    }


def test_count_inserted_terms_counts_only_excess_glossary_surfaces() -> None:
    """正解で1回のDatasetが出力に2回あるため、余分な1回を数える。"""
    assert count_inserted_terms(
        ["PyTorch", "Dataset"],
        [
            {"surface": "PyTorch", "readings": ["パイトーチ"]},
            {"surface": "Dataset", "readings": ["データセット"]},
            {"surface": "Dataset", "readings": ["データセット"]},
        ],
        "PyTorch Dataset Dataset",
    ) == 1


def test_count_inserted_terms_uses_spoken_surface_or_reading_occurrences() -> None:
    """ASRではspoken_text内のsurfaceとreadingを基準に余剰数を差し引く。"""
    glossary = [{"surface": "SDK", "readings": ["エスディーケー"]}]

    assert count_inserted_terms(
        ["SDK"], glossary, "SDK SDK SDK SDK", spoken_text="SDKの、SDKの"
    ) == 2
    assert count_inserted_terms(
        ["SDK"],
        glossary,
        "SDK SDK SDK SDK",
        spoken_text="エスディーケーの、SDKの、エスディーケー",
    ) == 1


def test_filler_count_avoids_overlap_and_english_substrings() -> None:
    """長い日本語語形を優先し、英語語形を部分一致で数えない。"""
    counts = count_fillers("えーと、えーっと、えっと、あー、そのー、んー、UH like uh summer")

    assert counts["えーと"] == 1
    assert counts["えーっと"] == 1
    assert counts["えっと"] == 1
    assert counts["えー"] == 0
    assert counts["あー"] == 1
    assert counts["そのー"] == 1
    assert counts["んー"] == 1
    assert counts["uh"] == 2
    assert "like" not in counts


def test_residual_fillers_subtracts_correct_text_occurrences() -> None:
    """正解文の「その」「まあ」は残存扱いせず、余分な3語だけ数える。"""
    assert count_residual_fillers(
        "その理由はまあ良い。", "その理由はまあ、まあ、えーと、その"
    ) == 3


def test_filler_zero_rows_do_not_add_to_rate_denominator() -> None:
    """フィラー0件の行は分母に加えず、2件のmanifest数だけを使う。"""
    result = calculate_filler_metrics(
        ["", "その理由"],
        ["えー", "その、その、えー"],
        [0, 2],
    )

    assert result == {
        "residual_count": 3,
        "manifest_count": 2,
        "residual_rate": 1.5,
    }


def test_tag_metrics_report_exact_match_and_instruction_like_suspicion() -> None:
    """no_changeは1/2一致、言い直しは1/1一致、長い応答は1件と数える。"""
    result = calculate_tag_metrics(
        [
            {"target_text": "ＡＢＣ！", "hyp": "abc", "tags": ["no_change"]},
            {"target_text": "残す", "hyp": "削る", "tags": ["no_change"]},
            {"target_text": "直す", "hyp": "直す", "tags": ["self_correction"]},
            {"target_text": "猫", "hyp": "猫返答", "tags": ["instruction_like"]},
        ]
    )

    assert result["no_change"]["count"] == 2
    assert result["no_change"]["exact_matches"] == 1
    assert result["no_change"]["exact_match_rate"] == 0.5
    assert result["no_change"]["cer"] == {
        "edit_errors": 2,
        "substitutions": 2,
        "insertions": 0,
        "deletions": 0,
        "reference_characters": 5,
        "rate": 0.4,
    }
    assert result["self_correction"]["exact_match_rate"] == 1.0
    assert result["instruction_like"]["count"] == 1
    assert result["instruction_like"]["cer"]["insertions"] == 2
    assert result["instruction_like"]["suspected_responses"] == 1


def test_latency_summary_uses_median_and_linear_p90() -> None:
    """1〜5秒の5値なら中央値3秒、線形補間p90は4.6秒になる。"""
    assert summarize_latency([1, 2, 3, 4, 5]) == {
        "count": 5,
        "median_s": 3.0,
        "p90_s": 4.6,
    }


def test_empty_reference_and_empty_latency_are_reported_as_undefined() -> None:
    """CERと率の分母が0の場合、数値でなく未定義として扱う。"""
    assert calculate_cer(["。"], [""]) == {
        "edit_errors": 0,
        "substitutions": 0,
        "insertions": 0,
        "deletions": 0,
        "reference_characters": 0,
        "rate": None,
    }
    assert summarize_latency([]) == {
        "count": 0,
        "median_s": None,
        "p90_s": None,
    }


def test_term_trace_counts_each_occurrence_and_reports_each_stage():
    """手計算で、距離0、候補あり、2回目1件、整形2件を確認する。"""
    row = {
        "id": "scripted-1",
        "terms": ["API", "API"],
        "glossary": [{"surface": "API", "readings": ["エーピーアイ"]}],
    }
    first = {"scripted-1": {"hyp": "エーピーアイ"}}
    second = {"scripted-1": {"hyp": "API"}}
    formatted = {
        "scripted-1": {"hyp": "API API", "input_text": "API"}
    }

    trace_rows, summary = analyze_term_trace(
        [row],
        first,
        second,
        formatted,
        [GlossaryEntry("API", ("エーピーアイ",))],
        [GlossaryEntry("API", ("エーピーアイ",))],
        "surface-reading",
    )

    assert len(trace_rows) == 2
    assert [item["closest_reading_distance"] for item in trace_rows] == [0, 0]
    assert [item["gold_candidate_selected"] for item in trace_rows] == [True, True]
    assert [item["two_pass_exact"] for item in trace_rows] == [True, False]
    assert all(item["formatted_exact"] for item in trace_rows)
    assert summary["stage_counts"]["first_pass_exact"] == 0
    assert summary["stage_counts"]["two_pass_exact"] == 1
    assert summary["stage_counts"]["formatted_exact"] == 2


def test_asr_report_aligns_glossary_readings_and_accepts_extra_run_fields(
    tmp_path,
) -> None:
    """長いsurfaceを先に読みへ揃え、任意の推論欄を含む行を評価する。"""
    manifest_row = {
        "id": "sample-asr",
        "spoken_text": "OpenAIとAI",
        "target_text": "OpenAIとAI",
        "terms": ["OpenAI", "AI"],
        "glossary": [
            {"surface": "AI", "readings": ["あい"]},
            {"surface": "OpenAI", "readings": ["おーぷんあい"]},
        ],
        "fillers": 0,
        "tags": [],
    }
    run_path = tmp_path / "asr.jsonl"
    run_path.write_text(
        json.dumps(
            {
                "id": "sample-asr",
                "system": "test",
                "stage": "asr",
                "hyp": "おーぷんあいとai",
                "latency_s": 0.5,
                "details": {"engine": "local"},
                "format_latency_s": 0.1,
                "input_text": "optional field",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = _evaluate_run(run_path, [manifest_row], {"sample-asr": 4.0})[0]

    assert result["utterances"]["evaluated"] == 1
    assert result["cer"] == {
        "edit_errors": 0,
        "substitutions": 0,
        "insertions": 0,
        "deletions": 0,
        "reference_characters": 9,
        "rate": 0.0,
    }
    assert result["raw_cer"] == {
        "edit_errors": 6,
        "substitutions": 6,
        "insertions": 0,
        "deletions": 0,
        "reference_characters": 9,
        "rate": 6 / 9,
    }
    table = _markdown_table([result])
    assert "0/9 (0.00%" in table
    assert "6/9 (66.67%" in table


def test_e2e_report_keeps_target_text_as_reference(tmp_path) -> None:
    """E2EのCERは読み揃えせずtarget_textだけを正解に使う。"""
    manifest_row = {
        "id": "sample-e2e",
        "spoken_text": "犬",
        "target_text": "猫",
        "terms": [],
        "glossary": [],
        "fillers": 0,
        "tags": [],
    }
    run_path = tmp_path / "e2e.jsonl"
    run_path.write_text(
        json.dumps(
            {
                "id": "sample-e2e",
                "system": "test",
                "stage": "e2e",
                "hyp": "猫",
                "latency_s": 0.5,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = _evaluate_run(run_path, [manifest_row], {"sample-e2e": 4.0})[0]

    assert result["cer"] == {
        "edit_errors": 0,
        "substitutions": 0,
        "insertions": 0,
        "deletions": 0,
        "reference_characters": 1,
        "rate": 0.0,
    }
    assert result["raw_cer"] is None


def test_inserted_term_reference_depends_on_stage(tmp_path) -> None:
    """ASRはspoken_textの2回、E2Eはtermsの1回を基準にする。"""
    manifest_row = {
        "id": "sample-stage-reference",
        "spoken_text": "SDKの、SDKの",
        "target_text": "SDK",
        "terms": ["SDK"],
        "glossary": [{"surface": "SDK", "readings": ["エスディーケー"]}],
        "fillers": 0,
        "tags": [],
    }
    results = []
    for stage in ("asr", "e2e"):
        run_path = tmp_path / f"{stage}.jsonl"
        run_path.write_text(
            json.dumps(
                {
                    "id": manifest_row["id"],
                    "system": "test",
                    "stage": stage,
                    "hyp": "SDK SDK SDK",
                    "latency_s": 0.5,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        results.append(
            _evaluate_run(run_path, [manifest_row], {manifest_row["id"]: 4.0})[0]
        )

    asr_result, e2e_result = results
    assert asr_result["inserted_terms"] == {
        "count": 1,
        "basis": "spoken_textに含まれるglossaryのsurface/readings",
    }
    assert e2e_result["inserted_terms"] == {
        "count": 2,
        "basis": "target_textのterms",
    }
    assert "spoken_textのsurface/readings" in _markdown_table(results)
    assert "target_textのterms基準" in _markdown_table(results)
    json_result = json.loads(json.dumps({"results": results}, ensure_ascii=False))
    assert json_result["results"][0]["inserted_terms"]["basis"] == (
        "spoken_textに含まれるglossaryのsurface/readings"
    )


def test_text_only_manifest_rows_are_evaluated_without_duration_groups(
    tmp_path, capsys
) -> None:
    """音声なし行も通常指標へ含め、音声長別遅延からの除外数を出す。"""
    audio_path = tmp_path / "audio.wav"
    with wave.open(str(audio_path), "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(8000)
        audio_file.writeframes(bytes(16000))

    manifest_rows = [
        {
            "id": "text-only",
            "target_text": "えー猫 AI",
            "terms": ["AI"],
            "glossary": [{"surface": "AI", "readings": ["エーアイ"]}],
            "fillers": 1,
            "tags": ["no_change"],
        },
        {
            "id": "with-audio",
            "target_text": "犬",
            "audio_path": "audio.wav",
            "terms": [],
            "glossary": [],
            "fillers": 0,
            "tags": ["self_correction"],
        },
    ]
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    run_path = tmp_path / "run.jsonl"
    run_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in [
                {
                    "id": "text-only",
                    "system": "test",
                    "stage": "e2e",
                    "hyp": "えー犬 AI えー",
                    "latency_s": 2.0,
                },
                {
                    "id": "with-audio",
                    "system": "test",
                    "stage": "e2e",
                    "hyp": "犬",
                    "latency_s": 4.0,
                },
            ]
        ),
        encoding="utf-8",
    )

    loaded_rows, durations = _load_manifest(manifest_path)
    result = _evaluate_run(run_path, loaded_rows, durations)[0]

    assert durations == {"with-audio": 1.0}
    assert result["utterances"] == {
        "manifest": 2,
        "evaluated": 2,
        "missing_predictions": 0,
    }
    assert result["cer"] == {
        "edit_errors": 3,
        "substitutions": 1,
        "insertions": 2,
        "deletions": 0,
        "reference_characters": 6,
        "rate": 0.5,
    }
    assert result["terms"] == {
        "correct": 1,
        "total": 1,
        "accuracy": 1.0,
        "loose_correct": None,
        "loose_accuracy": None,
    }
    assert result["fillers"] == {
        "residual_count": 1,
        "manifest_count": 1,
        "residual_rate": 1.0,
    }
    assert result["tags"]["no_change"]["count"] == 1
    assert result["tags"]["self_correction"]["exact_matches"] == 1
    assert result["latency"]["all"] == {
        "count": 2,
        "median_s": 3.0,
        "p90_s": 3.8,
    }
    assert result["latency"]["duration_groups"]["<=5s"] == {
        "count": 1,
        "median_s": 4.0,
        "p90_s": 4.0,
    }
    assert result["latency"]["unknown_duration_rows"] == 1
    assert json.loads(json.dumps(result))["latency"]["unknown_duration_rows"] == 1

    warning = capsys.readouterr().err
    assert "音声長不明のため音声長別遅延集計から除外=1" in warning
    table = _markdown_table([result])
    assert "長さ不明で音声長別遅延から除外" in table
    result_cells = [cell.strip() for cell in table.splitlines()[2].split("|")[1:-1]]
    assert result_cells[10] == "1"


def test_manifest_audio_path_to_missing_file_still_fails(tmp_path) -> None:
    """audio_pathがある行は音声ファイルが存在しない場合に引き続き失敗する。"""
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "missing-audio",
                "target_text": "猫",
                "audio_path": "missing.wav",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):
        _load_manifest(manifest_path)


def test_term_accuracy_split_separates_unseen_and_seen_terms() -> None:
    """見えない用語3出現（厳密2・緩い3）とそれ以外2出現（厳密1・緩い2）に分ける。"""
    result = calculate_term_accuracy_split(
        ["PyTorch", "Dataset", "Dataset", "Docker", "C#"],
        [
            {"surface": "PyTorch", "readings": ["パイトーチ"]},
            {"surface": "Dataset", "readings": ["データセット"]},
            {"surface": "Docker", "readings": ["ドッカー"]},
            {"surface": "C#", "readings": ["シーシャープ"]},
        ],
        "PyTorch データセット Dataset ドッカー C#",
        {"Dataset", "C#"},
    )

    assert result == {
        "unseen": {
            "correct": 2,
            "total": 3,
            "accuracy": 2 / 3,
            "loose_correct": 3,
            "loose_accuracy": 1.0,
        },
        "seen": {
            "correct": 1,
            "total": 2,
            "accuracy": 0.5,
            "loose_correct": 2,
            "loose_accuracy": 1.0,
        },
    }


def test_report_cli_with_unseen_terms_splits_table_and_json(tmp_path, capsys) -> None:
    """--unseen-terms指定時にE2EとASRの両方で見えない用語とそれ以外を表とJSONに出す。"""
    manifest_rows = [
        {
            "id": "u1",
            "spoken_text": "パイトーチとデータセット",
            "target_text": "PyTorchとDataset",
            "terms": ["PyTorch", "Dataset"],
            "glossary": [
                {"surface": "PyTorch", "readings": ["パイトーチ"]},
                {"surface": "Dataset", "readings": ["データセット"]},
            ],
            "fillers": 0,
            "tags": [],
        },
        {
            "id": "u2",
            "spoken_text": "ドッカーとデータセットとシーシャープ",
            "target_text": "DockerとDatasetとC#",
            "terms": ["Docker", "Dataset", "C#"],
            "glossary": [
                {"surface": "Docker", "readings": ["ドッカー"]},
                {"surface": "Dataset", "readings": ["データセット"]},
                {"surface": "C#", "readings": ["シーシャープ"]},
            ],
            "fillers": 0,
            "tags": [],
        },
    ]
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    unseen_path = tmp_path / "unseen.txt"
    unseen_path.write_text("  Dataset  \n\nC#\n", encoding="utf-8")

    e2e_path = tmp_path / "e2e.jsonl"
    e2e_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in [
                {
                    "id": "u1",
                    "system": "sys-e2e",
                    "stage": "e2e",
                    "hyp": "PyTorchとデータセット",
                    "latency_s": 0.4,
                },
                {
                    "id": "u2",
                    "system": "sys-e2e",
                    "stage": "e2e",
                    "hyp": "ドッカーとDatasetとシーシャープ",
                    "latency_s": 0.6,
                },
            ]
        ),
        encoding="utf-8",
    )
    asr_path = tmp_path / "asr.jsonl"
    asr_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in [
                {
                    "id": "u1",
                    "system": "sys-asr",
                    "stage": "asr",
                    "hyp": "パイトーチとDataset",
                    "latency_s": 0.2,
                },
                {
                    "id": "u2",
                    "system": "sys-asr",
                    "stage": "asr",
                    "hyp": "DockerとデータセットとC#",
                    "latency_s": 0.3,
                },
            ]
        ),
        encoding="utf-8",
    )

    exit_code = report_main(
        [
            "--manifest",
            str(manifest_path),
            "--runs",
            str(e2e_path),
            str(asr_path),
            "--unseen-terms",
            str(unseen_path),
        ]
    )
    assert exit_code == 0

    output = capsys.readouterr().out
    assert "用語正答率（見えない用語 / それ以外）" in output
    # E2E: unseen=1/3 (33.33%), seen=1/2 (50.00%)
    assert "| sys-e2e | e2e | 2/5 (40.00%) | 1/3 (33.33%) | 1/2 (50.00%) | — | — |" in output
    # ASR: unseen=2/3 (66.67%) / loose 3/3 (100.00%), seen=1/2 (50.00%) / loose 2/2 (100.00%)
    assert (
        "| sys-asr | asr | 3/5 (60.00%) | 2/3 (66.67%) | 1/2 (50.00%) | 3/3 (100.00%) | 2/2 (100.00%) |"
        in output
    )

    json_block = output.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    report = json.loads(json_block)
    assert report["unseen_terms"] == str(unseen_path)
    e2e_terms, asr_terms = (item["terms"] for item in report["results"])
    assert e2e_terms == {
        "correct": 2,
        "total": 5,
        "accuracy": 0.4,
        "loose_correct": None,
        "loose_accuracy": None,
        "unseen": {
            "correct": 1,
            "total": 3,
            "accuracy": 1 / 3,
            "loose_correct": None,
            "loose_accuracy": None,
        },
        "seen": {
            "correct": 1,
            "total": 2,
            "accuracy": 0.5,
            "loose_correct": None,
            "loose_accuracy": None,
        },
    }
    assert asr_terms == {
        "correct": 3,
        "total": 5,
        "accuracy": 0.6,
        "loose_correct": 5,
        "loose_accuracy": 1.0,
        "unseen": {
            "correct": 2,
            "total": 3,
            "accuracy": 2 / 3,
            "loose_correct": 3,
            "loose_accuracy": 1.0,
        },
        "seen": {
            "correct": 1,
            "total": 2,
            "accuracy": 0.5,
            "loose_correct": 2,
            "loose_accuracy": 1.0,
        },
    }


def test_report_with_empty_unseen_terms_marks_unseen_undefined(tmp_path) -> None:
    """見えない用語に該当する出現が0件でも、未定義（None）として正しく集計する。"""
    manifest_row = {
        "id": "u1",
        "target_text": "PyTorch",
        "terms": ["PyTorch"],
        "glossary": [{"surface": "PyTorch", "readings": ["パイトーチ"]}],
        "fillers": 0,
        "tags": [],
    }
    run_path = tmp_path / "e2e.jsonl"
    run_path.write_text(
        json.dumps(
            {"id": "u1", "system": "test", "stage": "e2e", "hyp": "PyTorch", "latency_s": 0.5},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = _evaluate_run(run_path, [manifest_row], {}, unseen_terms=set())[0]

    assert result["terms"]["unseen"] == {
        "correct": 0,
        "total": 0,
        "accuracy": None,
        "loose_correct": None,
        "loose_accuracy": None,
    }
    assert result["terms"]["seen"] == {
        "correct": 1,
        "total": 1,
        "accuracy": 1.0,
        "loose_correct": None,
        "loose_accuracy": None,
    }
    table = _markdown_table([result])
    assert "| test | e2e | 1/1 (100.00%) | — | 1/1 (100.00%) | — | — |" in table
