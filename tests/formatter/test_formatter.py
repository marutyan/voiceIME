"""整形の部品（用語集の絞り込み、規則ベースの系、プロンプトの組み立て）の確認。mlxを使わない。"""

import importlib.util
import json
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from voiceime.formatter.glossary import (
    GlossaryIndex,
    GlossaryEntry,
    PRIORITY_INTERLEAVE_RATIO,
    _interleave_rankings,
    _kana_to_romaji,
    _romanized_runs,
    add_abbreviation_readings,
    entry_from_record,
    exclude_glossary,
    glossary_from_rows,
    load_glossary,
    load_term_list,
    select_glossary,
    select_glossary_with_priority,
    select_screen_glossary,
)
from voiceime.formatter.prompt import (
    SYSTEM_PROMPT,
    FormatterInput,
    format_input_for_prompt,
    render_prompt,
    render_training_pair,
)
from voiceime.formatter.rules import format_with_rules
from voiceime.formatter import run as formatter_run

TRAIN_DIR = Path(__file__).parents[2] / "train/formatter"
if str(TRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(TRAIN_DIR))
train_spec = importlib.util.spec_from_file_location("formatter_train_for_test", TRAIN_DIR / "train.py")
assert train_spec is not None and train_spec.loader is not None
formatter_train = importlib.util.module_from_spec(train_spec)
sys.modules[train_spec.name] = formatter_train
train_spec.loader.exec_module(formatter_train)

GLOSSARY = [
    GlossaryEntry("PyTorch", ("パイトーチ",)),
    GlossaryEntry("Dataset", ("データセット",)),
    GlossaryEntry("Kubernetes", ("クバネティス", "クーベネティス")),
    GlossaryEntry("uv", ("ユーブイ",)),
    GlossaryEntry("Slack", ("スラック",)),
]


def test_load_glossary_merges_several_files(tmp_path):
    # 学習用の用語集と本人用の用語集を並べて読み、同じ表記の読みはまとめる。
    train = tmp_path / "train.jsonl"
    user = tmp_path / "user.jsonl"
    train.write_text(json.dumps({"surface": "DETR", "readings": ["ディーイーティーアール"]}) + "\n", encoding="utf-8")
    user.write_text(
        json.dumps({"surface": "DETR", "readings": ["ディーター"], "split": "user"}) + "\n"
        + json.dumps({"surface": "Hungarian Matching", "readings": ["ハンガリアンマッチング"], "split": "user"}) + "\n",
        encoding="utf-8",
    )
    assert load_glossary(train, user) == [
        GlossaryEntry("DETR", ("ディーイーティーアール", "ディーター")),
        GlossaryEntry("Hungarian Matching", ("ハンガリアンマッチング",)),
    ]


def test_entry_accepts_reading_and_readings():
    assert entry_from_record({"surface": "A", "reading": "エー"}).readings == ("エー",)
    assert entry_from_record({"surface": "A", "readings": ["エー", "エイ"]}).readings == ("エー", "エイ")


def test_load_glossary_merges_aliases_from_several_files(tmp_path):
    """同じ表記の読みと別名をファイル順にまとめ、重複を省く。"""
    train = tmp_path / "train.jsonl"
    user = tmp_path / "user.jsonl"
    app = tmp_path / "app.jsonl"
    train.write_text('{"surface":"IJCAI","readings":["アイジェーシーエーアイ"]}\n', encoding="utf-8")
    user.write_text('{"surface":"IJCAI","readings":["イジカイ"],"aliases":["維持会"]}\n', encoding="utf-8")
    app.write_text('{"surface":"IJCAI","aliases":["維持会","いじかい","いじかい"]}\n', encoding="utf-8")

    assert load_glossary(train, user, app) == [
        GlossaryEntry("IJCAI", ("アイジェーシーエーアイ", "イジカイ"), aliases=("維持会", "いじかい")),
    ]


def test_aliases_match_exact_text_and_respect_word_boundaries():
    """ひらがなの前後は問わず、カタカナや英数字の語中と大文字小文字の違いは除く。"""
    entries = [
        GlossaryEntry("IJCAI", (), aliases=("維持会", "いじかい")),
        GlossaryEntry("ICLR", (), aliases=("アイクリア", "iClear")),
    ]
    index = GlossaryIndex(entries)
    assert index.replace_aliases("維持会に向けた。あのいじかいに出す") == (
        "IJCAIに向けた。あのIJCAIに出す", entries[:1]
    )
    assert index.replace_aliases("アイクリア・iClearを使う") == ("ICLR・ICLRを使う", entries[1:])
    text = "新アイクリアランスとニューアイクリア、miniClear、iClear2、IClear"
    assert index.replace_aliases(text) == (text, [])


def test_aliases_prefer_longer_overlaps_without_replacing_inserted_surfaces():
    """開始位置が後でも長い別名を採り、置換先の用語表記は同じ処理中に再置換しない。"""
    short = GlossaryEntry("IJCAI", (), aliases=("維持会", "合同"))
    long = GlossaryEntry("合同", (), aliases=("会議室予約",))
    other = GlossaryEntry("学会", (), aliases=("合同",))
    index = GlossaryIndex([short, long, other])
    assert index.replace_aliases("維持会議室予約。合同") == ("維持合同。合同", [long])
    assert GlossaryIndex([short, long]).replace_aliases("会議室予約") == ("合同", [long])


def test_abbreviation_readings_are_optional_and_use_general_letter_names(tmp_path):
    """読み追加は引数で切り替え、個別語の慣用読みを足さずに一字読みだけを補う。"""
    path = tmp_path / "glossary.jsonl"
    path.write_text(
        json.dumps({"surface": "DDoS", "readings": ["ディーディオス"]}, ensure_ascii=False)
        + "\n"
        + json.dumps({"surface": "PCIe", "readings": []}, ensure_ascii=False)
        + "\n"
        + json.dumps(
            {"surface": "PCIe Gen4", "readings": ["ピーシーアイイージェンフォー"]},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {
                "surface": "Cloud Natural Language API",
                "readings": ["クラウドナチュラルランゲージエーピーアイ"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    original = path.read_text(encoding="utf-8")

    unchanged = load_glossary(path)
    expanded = load_glossary(path, expand_abbreviation_readings=True)

    assert unchanged[0].readings == ("ディーディオス",)
    assert expanded[0].readings == ("ディーディオス", "ディーディーオーエス")
    assert "ディードス" not in expanded[0].readings
    assert expanded[1].readings == ("ピーシーアイイー",)
    assert expanded[2].readings == (
        "ピーシーアイイージェンフォー",
        "ピーシーアイイージーイーエヌフォー",
    )
    assert expanded[3] == unchanged[3]
    assert path.read_text(encoding="utf-8") == original


def test_abbreviation_reading_helper_can_be_disabled():
    """関数を直接呼ぶ場合もenabled=Falseなら読みと項目を変えない。"""
    entry = GlossaryEntry("PCIe", ())

    assert add_abbreviation_readings([entry], enabled=False) == [entry]


def test_select_matches_katakana_and_latin():
    """読みはカタカナ区間、surfaceは英字区間で用語集へ一致する。"""
    selected = select_glossary("パイトーチのデータセトと、kubernetes", GLOSSARY)
    assert {e.surface for e in selected} == {"PyTorch", "Dataset", "Kubernetes"}


def test_select_does_not_convert_hiragana_text_to_katakana():
    """ひらがなで書かれた読みをカタカナ読み一致として選ばない。"""
    assert select_glossary("ぱいとーち", GLOSSARY[:1]) == []


def test_select_respects_max_entries():
    assert len(select_glossary("パイトーチとデータセットとスラック", GLOSSARY, max_entries=2)) == 2


def test_select_caps_score_when_a_long_reading_only_matches_partly():
    """短い一般語の一致で、長い読みを持つ候補が正解語より先に来ない。"""
    entries = [
        GlossaryEntry("Memory Search Service", ("メモリ検索サービス",)),
        GlossaryEntry("Memory", ("メモリ",)),
    ]

    assert [entry.surface for entry in select_glossary("メモリを使います", entries, max_entries=1)] == [
        "Memory"
    ]


def test_selection_index_matches_normalized_latin_and_katakana_romaji():
    """表記記号を除いた英字と、カタカナをローマ字へそろえた混在語を照合する。"""
    entries = [
        GlossaryEntry("Google Public DNS", ("グーグルパブリックDNS",)),
        GlossaryEntry("pd.to_datetime", ()),
        GlossaryEntry("DGX H100", ()),
        GlossaryEntry("rvalue reference", ("アールバリューリファレンス",)),
    ]
    index = GlossaryIndex(entries)

    for text, expected in [
        ("googlepablicdns", "Google Public DNS"),
        ("pd to datetime", "pd.to_datetime"),
        ("dgx h 100", "DGX H100"),
        ("rバリュリファレンス", "rvalue reference"),
    ]:
        assert expected in {entry.surface for entry in select_glossary(text, index)}

    assert _kana_to_romaji("アールバリュリファレンス") in _romanized_runs(
        "rバリュリファレンス"
    )
    assert "dgxh100" in _romanized_runs("dgx h 100")


def test_short_readings_require_katakana_or_latin_run_boundaries():
    """短い読みと英字表記は、文字種区間の内側だけでは一致させない。"""
    entries = [
        GlossaryEntry("Ruff", ("ラフ",)),
        GlossaryEntry("Dell", ("デル",)),
        GlossaryEntry("RAG", ("ラグ",)),
        GlossaryEntry("None", ("ナン",)),
    ]
    index = GlossaryIndex(entries)

    for text, surface in [
        ("グラフを描く", "Ruff"),
        ("モデルを使う", "Dell"),
        ("プラグインを使う", "RAG"),
        ("なんだけど", "None"),
    ]:
        assert surface not in {entry.surface for entry in select_glossary(text, index)}

    assert "Ruff" in {entry.surface for entry in select_glossary("ラフを描く", index)}
    assert "RAG" in {entry.surface for entry in select_glossary("プRAGイン", index)}
    assert "RAG" in {entry.surface for entry in select_glossary("RAGを使う", index)}


def test_selection_index_interleaves_priority_and_score_order():
    """既定の2:1順位で、本人用・第1版と得点順を交互にたどる。"""
    entries = [
        GlossaryEntry("PriorityTerm", ("パイオリティ",)),
        GlossaryEntry("PriorityTerm2", ("パイオリティー",)),
        GlossaryEntry("PriorityTerm3", ("パイオリティ",)),
        GlossaryEntry("ExpandedTerm", ("パイオリテ",), priority=False),
    ]
    index = GlossaryIndex(entries)

    assert [entry.surface for entry in select_glossary("パイオリテ", index, max_entries=4)] == [
        "PriorityTerm",
        "PriorityTerm2",
        "ExpandedTerm",
        "PriorityTerm3",
    ]


def test_interleave_rankings_honor_one_to_one_and_two_to_one_quotas():
    """重複項目を飛ばして、各順位から指定数の未選択語を補う。"""
    priority = [0, 1, 2, 3, 4, 5]
    score = [6, 7, 0, 1, 2, 3, 4, 5]

    assert _interleave_rankings(priority, score, 1, 1, 8) == [
        0, 6, 1, 7, 2, 3, 4, 5
    ]
    assert _interleave_rankings(priority, score, 2, 1, 8) == [
        0, 1, 6, 2, 3, 7, 4, 5
    ]
    assert PRIORITY_INTERLEAVE_RATIO == (2, 1)


def test_load_glossary_marks_v2_entries_as_lower_priority(tmp_path):
    """用語集v1と本人用の語をv2の拡張候補より先に扱う。"""
    v1 = tmp_path / "glossary.jsonl"
    v2 = tmp_path / "glossary-v2.jsonl"
    v1.write_text(json.dumps({"surface": "Base", "readings": ["ベース"]}) + "\n", encoding="utf-8")
    v2.write_text(json.dumps({"surface": "Expanded", "readings": ["エクスパンデッド"]}) + "\n", encoding="utf-8")

    entries = load_glossary(v1, v2)

    assert [entry.priority for entry in entries] == [True, False]


def test_alt_readings_only_change_selection(tmp_path):
    """追加読みで選べるようになっても、元の読みと置換・優先度は保持する。"""
    main = tmp_path / "glossary-v2.jsonl"
    main.write_text(
        '{"surface":"containerd","readings":["コンテナディー"],"replace_from":["コンテナディー"]}\n'
    )
    alt = tmp_path / "glossary-alt-readings.jsonl"
    alt.write_text(
        '{"surface":"containerd","readings":["コンテナード"]}\n'
        '{"surface":"containerd","readings":["コンテナード"]}\n'
        '{"surface":"unlisted","readings":["アンリステッド"]}\n'
    )
    base = load_glossary(main)
    augmented = load_glossary(main, alt_readings_path=alt)

    assert augmented == [
        GlossaryEntry("containerd", ("コンテナディー",), ("コンテナディー",), False, ("コンテナード",)),
    ]
    assert not select_glossary("コンテナードを起動", base, min_score=99)
    assert select_glossary("コンテナードを起動", augmented, min_score=99) == augmented
    assert load_glossary(main, exclude_terms={"containerd"}, alt_readings_path=alt) == []


def test_short_alt_readings_require_a_whole_run():
    """短い別読みは区間の内側や曖昧一致で候補に入れない。"""
    entry = GlossaryEntry("example", ("エグザンプル",), alt_readings=("カースト",))
    index = GlossaryIndex([entry])
    assert select_glossary("カーストを使う", index) == [entry]
    assert select_glossary("ミニカーストを使う", index) == []
    assert select_glossary("カーズトを使う", index) == []


def test_alt_readings_file_rejects_an_invalid_readings_field(tmp_path):
    """誤った配列の形式を1文字ずつの読みと解釈しない。"""
    main = tmp_path / "glossary.jsonl"
    main.write_text('{"surface":"Example","readings":["エグザンプル"]}\n')
    alt = tmp_path / "alt.jsonl"
    alt.write_text('{"surface":"Example","readings":"イグザンプル"}\n')
    with pytest.raises(ValueError, match="追加読み"):
        load_glossary(main, alt_readings_path=alt)


def test_build_readings_has_written_rule_and_teacher_correspondence(tmp_path):
    """規則で語尾・数字・略語を補い、教師候補は表記との対応を検査する。"""
    scripts = Path(__file__).parents[2] / "runs/alt-readings"
    build = runpy.run_path(str(scripts / "build_readings.py"))
    allow = build["check_teacher_reading"]
    assert "コンテナード" in build["rule_variants"]("containerd", ("コンテナディー",))
    assert "フォーディー" in build["rule_variants"]("4D", ("ヨンディー",))
    assert "アールエージー" in build["rule_variants"]("RAG", ("ラグ",))
    assert allow("Kubernetes", ("クバネティス",), "クベルネティス")
    assert not allow("Kubernetes", ("クバネティス",), "データベース")
    assert not allow("Python 3", ("パイソンスリー",), "パイソンフォー")

    main = tmp_path / "glossary.jsonl"
    main.write_text(
        '{"surface":"Kubernetes","readings":["クバネティス"]}\n'
        '{"surface":"Python 3","readings":["パイソンスリー"]}\n'
    )
    requests = tmp_path / "requests.jsonl"
    requests.write_text('{"id":"0","surfaces":["Kubernetes","Python 3"]}\n')
    responses = tmp_path / "responses.jsonl"
    responses.write_text(json.dumps({
        "id": "0", "finish_reason": "stop", "text": "1:クベルネティス\n2:パイソンフォー",
    }) + "\n")
    output, report = tmp_path / "alt.jsonl", tmp_path / "report.json"
    build["build"]([main], requests, responses, output, report)
    by_surface = {entry.surface: entry.alt_readings for entry in load_glossary(main, alt_readings_path=output)}
    assert "クベルネティス" in by_surface["Kubernetes"]
    assert "パイソンフォー" not in by_surface["Python 3"]
    assert json.loads(report.read_text())["teacher_accepted_readings"] == 1


def test_select_screen_glossary_is_case_insensitive_and_respects_english_boundaries():
    """英字用語の大文字小文字を無視し、別の英字語に含まれる部分は選ばない。"""
    entries = [
        GlossaryEntry("Git", ("ギット",)),
        GlossaryEntry("GitHub", ("ギットハブ",)),
        GlossaryEntry("Dataset", ("データセット",)),
        GlossaryEntry("音声認識", ()),
    ]

    selected = select_screen_glossary(
        "Using GITHUBとGitHub2, DatasetBuilder and dataset、音声認識の設定", entries
    )

    assert [entry.surface for entry in selected] == ["GitHub", "Dataset", "音声認識"]


def test_priority_glossary_prefers_screen_related_entries_within_limit():
    """画面優先語を先に並べ、通常候補を補って指定上限を守る。"""
    entries = [GlossaryEntry("PyTorch", ()), GlossaryEntry("GitHub", ()), GlossaryEntry("Docker", ())]
    selected = select_glossary_with_priority("PyTorch GitHub Docker", entries, [entries[2]], max_entries=2)

    assert selected == [entries[2], entries[0]]


def test_rules_remove_fillers_and_replace_terms():
    assert format_with_rules("えーと、パイトーチのその、データセットを使います", GLOSSARY) == "PyTorchのDatasetを使います。"


def test_rules_replace_only_exact_katakana_readings():
    """実際の2区間文ではGitHubだけを置き換え、近い読みのDockerやMATHへ誤置換しない。"""
    glossary = [
        GlossaryEntry("GitHub", ("ギットハブ",)),
        GlossaryEntry("Docker", ("ドッカー",)),
        GlossaryEntry("MATH", ("マス",)),
    ]
    spoken = "ギットハブにプッシュしました。ロッカーを再起動します。"

    assert format_with_rules(spoken, glossary) == "GitHubにプッシュしました。ロッカーを再起動します。"
    assert {entry.surface for entry in select_glossary(spoken, glossary)} == {"GitHub", "Docker"}


def test_rules_do_not_replace_fuzzy_mish_reading():
    """曖昧検索が拾うMishの読みでも、規則整形ではプッシュを置き換えない。"""
    glossary = [GlossaryEntry("Mish", ("ミッシュ",))]

    assert select_glossary("プッシュしました", glossary) == glossary
    assert format_with_rules("プッシュしました", glossary) == "プッシュしました。"


def test_short_reading_replaces_only_an_exact_katakana_run():
    """2文字以下の読みは、カタカナ区間全体が同じ場合だけ置換する。"""
    glossary = [GlossaryEntry("MATH", ("マス",))]

    assert format_with_rules("マスです", glossary) == "MATHです。"
    assert format_with_rules("します", glossary) == "します。"


def test_rules_keep_demonstrative_without_comma():
    assert format_with_rules("あの本を読みます", []) == "あの本を読みます。"


class _TrainingTokenizer:
    """学習プロンプトの本文を記録する最小tokenizer。"""

    bos_token = "<s>"
    eos_token = "</s>"

    def __init__(self):
        self.inputs = []

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, **kwargs):
        text = self.bos_token + "".join(f"<{item['role']}>\n{item['content']}\n" for item in messages)
        return text + ("<assistant>" if add_generation_prompt else "")

    def __call__(self, text, add_special_tokens):
        self.inputs.append(text)
        return {"input_ids": [ord(char) for char in text]}


def test_training_fixed_row_glossary_does_not_restore_an_omitted_term():
    """glossary_fixed行は行の辞書だけを学習プロンプトへ渡し、旧経路は再選択する。"""
    pool = [
        GlossaryEntry("AlphaNet", ("アルファネット",)),
        GlossaryEntry("DecoyNet", ("デコイネット",)),
    ]
    args = SimpleNamespace(
        nohint_prob=0.0,
        asr_noise_prob=0.0,
        user_punct_prob=0.0,
        max_glossary=20,
        glossary_drop_prob=0.0,
        max_distractors=0,
        max_length=2048,
    )

    for fixed, expected_omitted_term in [(True, False), (False, True)]:
        tokenizer = _TrainingTokenizer()
        row = {
            "glossary_fixed": fixed,
            "glossary": [{"surface": "DecoyNet", "readings": ["デコイネット"]}],
            "spoken_text": "アルファネットで確認します",
            "spoken_text_kana": "アルファネットで確認します",
            "target_text": "アルファネットで確認します。",
            "omitted_terms": [{"surface": "AlphaNet", "readings": ["アルファネット"]}],
        }
        dataset = formatter_train.FormatterDataset(
            [row], [row["spoken_text"]], pool, tokenizer, args, train=True
        )
        dataset[0]
        prompt = tokenizer.inputs[0]
        assert ("AlphaNet" in prompt) is expected_omitted_term
        if fixed:
            assert "DecoyNet" in prompt


def test_multiasr_prompt_names_each_source_and_includes_qwen_hypothesis():
    prompt = format_input_for_prompt(
        FormatterInput(
            first_pass="Haasの1回目",
            combined_text="segment-merge後",
            qwen_hypothesis="Qwen仮説",
        )
    )

    assert "1回目（ヒントなし）:\nHaasの1回目" in prompt
    assert "結合文（2回目の採否を区間ごとに判断）:\nsegment-merge後" in prompt
    assert "Qwen3-ASR 0.6Bの仮説:\nQwen仮説" in prompt


def test_multiasr_training_uses_selected_glossary_and_all_asr_sources():
    tokenizer = _TrainingTokenizer()
    args = SimpleNamespace(
        input_passes="multiasr",
        asr_noise_prob=0.0,
        user_punct_prob=0.0,
        max_glossary=20,
        glossary_drop_prob=0.0,
        max_distractors=0,
        max_length=2048,
    )
    row = {
        "glossary_fixed": True,
        "glossary": [{"surface": "AlphaNet", "readings": ["アルファネット"]}],
        "spoken_text": "アルファネットで確認します",
        "spoken_text_kana": "アルファネットで確認します",
        "target_text": "AlphaNetで確認します。",
    }
    dataset = formatter_train.FormatterDataset(
        [row],
        ["segment-merge後"],
        [GlossaryEntry("AlphaNet", ("アルファネット",))],
        tokenizer,
        args,
        train=True,
        nohint_hyps=["Haasの1回目"],
        combined_hyps=["segment-merge後"],
        qwen_hyps=["Qwen仮説"],
        selected_glossaries=[[GlossaryEntry("SelectedTerm", ("セレクテッドターム",))]],
    )

    dataset[0]

    prompt = tokenizer.inputs[0]
    assert "Haasの1回目" in prompt
    assert "segment-merge後" in prompt
    assert "Qwen仮説" in prompt
    assert "SelectedTerm" in prompt

    eval_dataset = formatter_train.FormatterDataset(
        [row],
        ["segment-merge後"],
        [GlossaryEntry("AlphaNet", ("アルファネット",))],
        tokenizer,
        args,
        train=False,
        nohint_hyps=["Haasの1回目"],
        combined_hyps=["segment-merge後"],
        qwen_hyps=["Qwen仮説"],
        selected_glossaries=[[GlossaryEntry("SelectedTerm", ("セレクテッドターム",))]],
    )

    eval_dataset[0]

    eval_prompt = tokenizer.inputs[-2]
    assert "Qwen仮説" in eval_prompt
    assert "SelectedTerm" in eval_prompt


def test_combined_first_uses_asr_noise_for_rows_without_real_asr(monkeypatch):
    """C条件では実ASRが無い行に、1回目と2回目相当の既存ノイズ加工を使う。"""
    tokenizer = _TrainingTokenizer()
    args = SimpleNamespace(
        input_passes="combined_first",
        asr_noise_prob=1.0,
        user_punct_prob=0.0,
        max_glossary=20,
        glossary_drop_prob=0.0,
        max_distractors=0,
        max_length=2048,
    )
    row = {
        "glossary_fixed": True,
        "glossary": [],
        "spoken_marked": "読み上げた文",
        "spoken_text": "読み上げた文",
        "target_text": "正解文。",
    }
    profiles = []

    def fake_noise(text, _rng, profile, _hinted, **_kwargs):
        profiles.append(profile)
        return f"noise-{len(profiles)}:{text}"

    monkeypatch.setattr(formatter_train, "simulate_asr_noise", fake_noise)
    dataset = formatter_train.FormatterDataset([row], [row["spoken_text"]], [], tokenizer, args, train=True)

    dataset[0]

    assert profiles == [formatter_train.HAAS_NOHINT, formatter_train.HAAS_TWOPASS]
    assert "noise-1:読み上げた文" in tokenizer.inputs[0]
    assert "noise-2:読み上げた文" in tokenizer.inputs[0]


def test_combined_first_preserves_real_asr_inputs(monkeypatch):
    """C条件の実ASR行では1回目と採否後文を加工せずに使う。"""
    tokenizer = _TrainingTokenizer()
    args = SimpleNamespace(
        input_passes="combined_first",
        asr_noise_prob=1.0,
        user_punct_prob=0.0,
        max_glossary=20,
        glossary_drop_prob=0.0,
        max_distractors=0,
        max_length=2048,
    )
    row = {
        "glossary_fixed": True,
        "glossary": [],
        "spoken_marked": "読み上げた文",
        "spoken_text": "読み上げた文",
        "target_text": "正解文。",
    }
    monkeypatch.setattr(
        formatter_train,
        "simulate_asr_noise",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("実ASRを加工した")),
    )
    dataset = formatter_train.FormatterDataset(
        [row], [row["spoken_text"]], [], tokenizer, args, train=True,
        nohint_hyps=["first-pass"], combined_hyps=["accepted-second-pass"],
    )

    dataset[0]

    assert "first-pass" in tokenizer.inputs[0]
    assert "accepted-second-pass" in tokenizer.inputs[0]


class _SystemIgnoringTokenizer:
    """system役の内容を固定文に差し替えるtemplate（llm-jp-3と同じ挙動）を真似る。"""

    bos_token = "<s>"
    eos_token = "</s>"

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, **kwargs):
        text = "<s>"
        for m in messages:
            if m["role"] == "system":
                text += "固定の指示"
            elif m["role"] == "user":
                text += "\n### 指示:\n" + m["content"]
            else:
                text += "\n### 応答:\n" + m["content"] + "</s>"
        return text + ("\n### 応答:\n" if add_generation_prompt else "")


def test_prompt_moves_instruction_when_template_drops_system():
    tokenizer = _SystemIgnoringTokenizer()
    assert SYSTEM_PROMPT in render_prompt(tokenizer, "テスト", GLOSSARY[:1])
    prompt, completion = render_training_pair(tokenizer, "テスト", GLOSSARY[:1], "正解。")
    assert SYSTEM_PROMPT in prompt and completion == "正解。</s>"


def test_generation_stops_on_new_repetition_and_records_reason(monkeypatch):
    """Metalを使わない偽MLXで、異常反復の直後に生成を止めたことを確かめる。"""
    mlx = ModuleType("mlx")
    mlx.__path__ = []
    mx = ModuleType("mlx.core")
    mx.array = lambda value: value
    mx.get_peak_memory = lambda: 0
    mlx.core = mx

    mlx_lm = ModuleType("mlx_lm")
    mlx_lm.__path__ = []
    mlx_lm.load = lambda _path: None
    mlx_lm.stream_generate = None
    mlx_lm_models = ModuleType("mlx_lm.models")
    mlx_lm_models.__path__ = []
    mlx_lm_cache = ModuleType("mlx_lm.models.cache")
    mlx_lm_cache.make_prompt_cache = lambda _model: []
    monkeypatch.setitem(sys.modules, "mlx", mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    monkeypatch.setitem(sys.modules, "mlx_lm", mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.models", mlx_lm_models)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", mlx_lm_cache)

    module_name = "voiceime.formatter._test_engine"
    engine_path = Path(__file__).parents[2] / "src/voiceime/formatter/engine.py"
    spec = importlib.util.spec_from_file_location(module_name, engine_path)
    assert spec is not None and spec.loader is not None
    formatter_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, formatter_module)
    spec.loader.exec_module(formatter_module)

    chunks = []
    yielded = []
    generation_options = {}

    def fake_stream_generate(*_args, **options):
        """生成chunkを順に返し、消費された数と上限を記録する。"""
        generation_options.update(options)
        for index, chunk in enumerate(chunks, start=1):
            yielded.append(chunk)
            yield SimpleNamespace(
                text=chunk,
                generation_tokens=index,
                prompt_tps=5.0,
                generation_tps=10.0,
                finish_reason=None,
            )

    formatter_module.render_prompt = lambda _tokenizer, _text, _glossary: "prompt"
    formatter_module.stream_generate = fake_stream_generate
    formatter = object.__new__(formatter_module.MlxFormatter)
    formatter.model = object()
    formatter.tokenizer = SimpleNamespace(encode=lambda _text, add_special_tokens=False: [0] * 100)
    formatter._prefix_tokens = []
    formatter._prefix_cache = None
    formatter._encode = lambda _text: [1, 2, 3]

    for raw_text, repetition in [
        ("HellaSwagのクエリを照合します。", "、、、、、"),
        ("Core i7のフラッシュです。", "その、" * 4),
    ]:
        chunks = [raw_text, repetition, "この応答は読まれない"]
        yielded = []
        generation_options = {}

        result = formatter.format(raw_text, [])

        assert yielded == chunks[:2]
        assert result.text == raw_text + repetition
        assert result.finish_reason == "repetition"
        assert generation_options["max_tokens"] == 150


def test_load_term_list_and_exclude_from_glossary(tmp_path):
    """1行1語の一覧（記号付き語や空行を含む）を読み、用語集読み込みから確実に除く。"""
    exclude_path = tmp_path / "exclude.txt"
    exclude_path.write_text("Dataset\n\n  C#  \n", encoding="utf-8")
    excluded = load_term_list(exclude_path)
    assert excluded == {"Dataset", "C#"}

    g1 = tmp_path / "g1.jsonl"
    g2 = tmp_path / "g2.jsonl"
    g1.write_text(
        json.dumps({"surface": "PyTorch", "readings": ["パイトーチ"]}) + "\n"
        + json.dumps({"surface": "Dataset", "readings": ["データセット"]}) + "\n"
        + json.dumps({"surface": "C#", "readings": ["シーシャープ"]}) + "\n",
        encoding="utf-8",
    )
    g2.write_text(
        json.dumps({"surface": "PyTorch", "readings": ["パイ・トーチ"]}) + "\n"
        + json.dumps({"surface": "Dataset", "readings": ["データ・セット"]}) + "\n",
        encoding="utf-8",
    )

    assert load_glossary(g1, g2, exclude_terms=excluded) == [
        GlossaryEntry("PyTorch", ("パイトーチ", "パイ・トーチ")),
    ]
    rows = [
        {
            "glossary": [
                {"surface": "PyTorch", "readings": ["パイトーチ"]},
                {"surface": "Dataset", "readings": ["データセット"]},
            ]
        }
    ]
    assert glossary_from_rows(rows, exclude_terms=excluded) == [
        GlossaryEntry("PyTorch", ("パイトーチ",)),
    ]
    assert exclude_glossary(GLOSSARY, ["Dataset", "Slack"]) == [
        GLOSSARY[0],
        GLOSSARY[2],
        GLOSSARY[3],
    ]


def test_formatter_run_exclude_terms_hides_terms_in_select_and_row_modes(tmp_path):
    """voiceime.formatter.runの--exclude-termsがselectとrowの両方で効き、summaryも保存できる。"""
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "id": "u1",
                "spoken_text": "パイトーチのデータセットを使います",
                "glossary": [
                    {"surface": "PyTorch", "readings": ["パイトーチ"]},
                    {"surface": "Dataset", "readings": ["データセット"]},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    glossary_file = tmp_path / "glossary.jsonl"
    glossary_file.write_text(
        json.dumps({"surface": "PyTorch", "readings": ["パイトーチ"]}, ensure_ascii=False) + "\n"
        + json.dumps({"surface": "Dataset", "readings": ["データセット"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    exclude_file = tmp_path / "exclude.txt"
    exclude_file.write_text("Dataset\n", encoding="utf-8")

    for mode, extra_args in [
        ("select", ["--glossary", str(glossary_file)]),
        ("select", []),
        ("row", []),
    ]:
        out = tmp_path / f"out-{mode}-{len(extra_args)}.jsonl"
        formatter_run.main(
            [
                "--manifest",
                str(manifest),
                "--model",
                "rules",
                "--glossary-mode",
                mode,
                "--exclude-terms",
                str(exclude_file),
                "--out",
                str(out),
                *extra_args,
            ]
        )
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["glossary"] == ["PyTorch"]
        assert rows[0]["hyp"] == "PyTorchのデータセットを使います。"
        summary = json.loads(out.with_suffix(".summary.json").read_text(encoding="utf-8"))
        assert summary["glossary_size"] == 1
        assert summary["args"]["exclude_terms"] == str(exclude_file)


def test_formatter_run_exclude_terms_omits_excluded_terms_from_llm_calls(tmp_path, monkeypatch):
    """LLM整形でもwarm-up・本番ともに除外語を参考用語へ渡さない。"""
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "id": "u1",
                "spoken_text": "パイトーチのデータセット",
                "glossary": [
                    {"surface": "PyTorch", "readings": ["パイトーチ"]},
                    {"surface": "Dataset", "readings": ["データセット"]},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    exclude_file = tmp_path / "exclude.txt"
    exclude_file.write_text("Dataset\n", encoding="utf-8")

    seen_glossaries: list[list[str]] = []

    class _FakeMlxFormatter:
        def __init__(self, _model: str, use_prefix_cache: bool = False):
            self.use_prefix_cache = use_prefix_cache

        def format(self, raw_text: str, glossary: list[GlossaryEntry]):
            seen_glossaries.append([entry.surface for entry in glossary])
            return SimpleNamespace(
                text=raw_text,
                prompt_tokens=10,
                cached_tokens=0,
                generation_tokens=5,
                generation_tps=50.0,
                finish_reason="stop",
            )

    fake_engine = ModuleType("voiceime.formatter.engine")
    fake_engine.MlxFormatter = _FakeMlxFormatter
    fake_mlx = ModuleType("mlx")
    fake_mlx.__path__ = []
    fake_mx = ModuleType("mlx.core")
    fake_mx.get_peak_memory = lambda: 0
    fake_mlx.core = fake_mx
    monkeypatch.setitem(sys.modules, "voiceime.formatter.engine", fake_engine)
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mx)

    out = tmp_path / "llm.jsonl"
    formatter_run.main(
        [
            "--manifest",
            str(manifest),
            "--model",
            "fake-model",
            "--exclude-terms",
            str(exclude_file),
            "--out",
            str(out),
        ]
    )

    # warm-upと本番の2回ともPyTorchだけが渡り、Datasetは渡らない。
    assert seen_glossaries == [["PyTorch"], ["PyTorch"]]


def test_apply_output_style_writes_percent_sign_after_numbers():
    from voiceime.formatter.style import apply_output_style

    assert apply_output_style("効率が15パーセントくらい良くなる") == "効率が15%くらい良くなる"
    assert apply_output_style("何パーセントか") == "何パーセントか"


def test_restore_listed_readings_replaces_long_reading_only() -> None:
    """一覧の語の長い読みだけを表記へ戻し、短い読みと表記が既にある語は変えない。"""
    from voiceime.formatter.glossary import GlossaryEntry
    from voiceime.formatter.restore import restore_listed_readings

    entries = [
        GlossaryEntry("Apache Beam", ("アパッチビーム",), aliases=("アパッチ賞",)),
        GlossaryEntry("Batch", ("バッチ",)),
        GlossaryEntry("PyTorch", ("パイトーチ",)),
    ]
    assert (
        restore_listed_readings("アパッチビームのバッチ処理を直す。", entries)
        == "Apache Beamのバッチ処理を直す。"
    )
    # 表記が既に文にある語は、読みが残っていても触らない。
    assert (
        restore_listed_readings("Apache Beam（アパッチビーム）を使う。", entries)
        == "Apache Beam（アパッチビーム）を使う。"
    )
    assert restore_listed_readings("アパッチ賞の話。", entries) == "アパッチ賞の話。"
