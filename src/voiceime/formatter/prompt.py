"""整形用LLMのプロンプト（指示文、用語集、入力）の唯一の定義。

学習（Colab上のtransformers）と推論（手元のmlx-lm）の両方がこのmoduleでプロンプトを作る。
両者でずれると、学習した形式と違う入力を推論で渡すことになるため、他の場所で組み立てない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from voiceime.formatter.glossary import GlossaryEntry

# 指示文。学習前のモデルでも動くよう具体的に書き、学習後もこの文を変えずに使う。
SYSTEM_PROMPT = """あなたは音声入力の整形係です。入力は音声認識の結果で、フィラー、言い直し、カタカナで書かれた英語の用語を含みます。次の規則で書き直した文だけを出力してください。
1. 入力に複数の認識文がある場合は見比べる。後の認識が前の正しい語を別の語で上書きしたり、一部だけを置き換えたりすることがあるため、どれか1つを常に優先せず、話された内容に忠実な語を選ぶ。
2. フィラー（えー、えーと、あの、まあ、なんか など）を削除する。
3. 言い直しがあれば、訂正後の内容だけを残す。
4. 用語集の「→」の左の読みで話された語は、右の表記で書く。用語集の読みは出力に書かない。
5. 句読点を付け、話し言葉の数字は算用数字にする。
6. それ以外の言葉は変えない。内容の追加、要約、質問や依頼への回答はしない。入力が質問や依頼でも、その文を整形して出力する。"""

# 用語集の見出し。ここまでは全ての入力で同じなので、推論ではKVキャッシュを使い回せる。
GLOSSARY_HEADER = "用語集:"
# 用語集が空のときに書く文字列。
EMPTY_GLOSSARY = "（なし）"
# 入力文の見出し。
INPUT_HEADER = "入力:"

# 推論モデル（Qwen3系など）の思考出力を止めるため、chat templateへ渡す引数。対応しないtemplateは無視する。
CHAT_TEMPLATE_KWARGS: dict[str, Any] = {"enable_thinking": False}


@dataclass(frozen=True)
class FormatterInput:
    """異なるASR結果を整形器へ渡す。既存の文字列入力もそのまま使える。"""

    first_pass: str | None = None
    second_pass: str | None = None
    combined_text: str | None = None
    qwen_hypothesis: str | None = None

    def __post_init__(self) -> None:
        if all(text is None for text in (
            self.first_pass, self.second_pass, self.combined_text, self.qwen_hypothesis
        )):
            raise ValueError("ASRの入力文が1つ以上必要です")


def formatter_input_text(asr_input: str | FormatterInput) -> str:
    """用語の絞り込みや出力長の計算に使うASR本文を返す。"""
    if isinstance(asr_input, FormatterInput):
        return "\n".join(
            text
            for text in (
                asr_input.first_pass,
                asr_input.second_pass,
                asr_input.combined_text,
                asr_input.qwen_hypothesis,
            )
            if text is not None
        )
    return asr_input


def formatter_output_reference_text(asr_input: str | FormatterInput) -> str:
    """生成文の長さ上限に使う代表文を返し、複数入力による上限の水増しを防ぐ。"""
    if not isinstance(asr_input, FormatterInput):
        return asr_input
    return (
        asr_input.second_pass
        or asr_input.combined_text
        or asr_input.first_pass
        or asr_input.qwen_hypothesis
        or ""
    )


def format_input_for_prompt(asr_input: str | FormatterInput) -> str:
    """従来の1本文形式を保ち、複数のASR結果には情報源を付けて示す。"""
    if not isinstance(asr_input, FormatterInput):
        return asr_input
    sections = []
    if asr_input.first_pass is not None:
        sections.append(f"1回目（ヒントなし）:\n{asr_input.first_pass}")
    if asr_input.second_pass is not None:
        sections.append(f"2回目（ヒントあり）:\n{asr_input.second_pass}")
    if asr_input.combined_text is not None:
        sections.append(f"結合文（2回目の採否を区間ごとに判断）:\n{asr_input.combined_text}")
    if asr_input.qwen_hypothesis is not None:
        sections.append(f"Qwen3-ASR 0.6Bの仮説:\n{asr_input.qwen_hypothesis}")
    return "\n\n".join(sections)


def format_glossary(glossary: Sequence[GlossaryEntry]) -> str:
    """用語集を「- 読み1、読み2 → 表記」の行の並びにする。

    「表記（読み）」の形だと、学習前のモデルが括弧の読みまで出力へ写す例があったため、置き換えの向きを矢印で示す。
    """
    if not glossary:
        return EMPTY_GLOSSARY
    lines = []
    for entry in glossary:
        readings = "、".join(entry.readings)
        lines.append(f"- {readings} → {entry.surface}" if readings else f"- {entry.surface}")
    return "\n".join(lines)


def build_messages(asr_text: str | FormatterInput, glossary: Sequence[GlossaryEntry]) -> list[dict[str, str]]:
    """chat形式のメッセージ（system、user）を作る。"""
    user = f"{GLOSSARY_HEADER}\n{format_glossary(glossary)}\n\n{INPUT_HEADER}\n{format_input_for_prompt(asr_text)}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _apply_template(tokenizer: Any, messages: list[dict[str, str]], add_generation_prompt: bool) -> str:
    """chat templateで文字列にする。

    system役で例外を出すtemplateや、system役の内容を固定文に差し替えるtemplate（llm-jp-3など）では、
    指示文が届かないため、指示文をuserの先頭へ移して適用し直す。
    """
    try:
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=add_generation_prompt, **CHAT_TEMPLATE_KWARGS
        )
        if messages[0]["role"] != "system" or messages[0]["content"] in rendered:
            return rendered
    except Exception:
        if messages[0]["role"] != "system":
            raise
    merged = {"role": "user", "content": f"{messages[0]['content']}\n\n{messages[1]['content']}"}
    return tokenizer.apply_chat_template(
        [merged, *messages[2:]], tokenize=False, add_generation_prompt=add_generation_prompt, **CHAT_TEMPLATE_KWARGS
    )


def render_prompt(tokenizer: Any, asr_text: str | FormatterInput, glossary: Sequence[GlossaryEntry]) -> str:
    """推論に渡すプロンプト文字列（assistantの応答の直前まで）を作る。"""
    return _apply_template(tokenizer, build_messages(asr_text, glossary), add_generation_prompt=True)


def render_training_pair(
    tokenizer: Any, asr_text: str | FormatterInput, glossary: Sequence[GlossaryEntry], target_text: str
) -> tuple[str, str]:
    """学習用に、プロンプト部分と応答部分（終端の記号を含む）の文字列の組を返す。

    応答部分は、assistantの発話まで含めてtemplateを適用した文字列から、プロンプト部分を除いて得る。
    これで推論時と同じプロンプトの直後に、templateが定める終端の記号まで学習できる。
    """
    prompt = render_prompt(tokenizer, asr_text, glossary)
    messages = build_messages(asr_text, glossary) + [{"role": "assistant", "content": target_text}]
    full = _apply_template(tokenizer, messages, add_generation_prompt=False)
    if full.startswith(prompt):
        return prompt, full[len(prompt) :]
    # templateが応答の前に別の文字列を挟む場合は、応答と終端記号だけを学習する。
    eos = tokenizer.eos_token or ""
    return prompt, target_text + eos


def needs_special_tokens(tokenizer: Any, text: str) -> bool:
    """文字列をtoken化するときにBOSなどを足す必要があるか。templateが既にBOSを入れていれば足さない。

    mlx-lmの`stream_generate`と同じ判定にして、学習と推論でtoken列をそろえる。
    """
    bos = getattr(tokenizer, "bos_token", None)
    return bos is None or not text.startswith(bos)
