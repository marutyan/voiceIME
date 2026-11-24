"""音声の無い文を、採用したASR（Haas-ja-v1.0＋用語のヒント）の出力に似せる加工。

`data/text`の`spoken_marked`（フィラーを`{えーと}`、英字で書く語を`[[英字|読み]]`で印付けした話し言葉）から、
ASRが出しそうな文を作る。加工の種類と確率は、合成音声のtrain 9,990件をHaasで認識した実出力
（`runs/asr-tts/haas-quirks.json`、記録は`docs/experiments/2026-11-21-asr-tts-haas.md`）に合わせた。
第1弾（commit d40f689まで）はdev-sayの少数の観察から決めた値で、フィラーを半分落としていた。

- フィラーはほぼ全部残す。伸ばす音の語形は書き方が変わる（「あのー」→「あの」、「えーと」→「ええと」「えっと」）。
- 言い直しの言葉（いや、じゃなくて）は`spoken_marked`の地の文にあり、そのまま残す。
- 句読点：読点は話し言葉の約6割、文末の句点は約4割しか付かない。「？」「！」は半角で書く。迷った所に「...」が入る。
- 用語：two-passのヒントがあれば約7割が表記通り、ヒント無しではほぼ全部が小文字の英字、カタカナ、崩れた形になる。
  用語集に無い英語の句（「sounds good」など）は、ヒントが無いためカタカナか崩れた形になる。

あわせて、本人の声でのHaasの句読点の付き方（文末の句点が多く、読点が少ない）へ寄せる加工`to_user_punctuation`を持つ。
これはASRの実出力にもかける。

学習中に毎回違う加工をかけるほか、valの入力を一度だけ作ってファイルに残すCLIとしても使う（手元で実行）:
    uv run python train/formatter/asr_noise.py --input data/text/val.jsonl --out runs/<実験名>/val-asrsim.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# `spoken_marked`の印。1つ目の組がフィラー、2つ目と3つ目の組が英字の表記と読み。
MARK_PATTERN = re.compile(r"\{([^{}]*)\}|\[\[([^|\]]+)\|([^\]]+)\]\]")
# 用語の読みを近い音へ崩すときに差し替えるカタカナ（ASRが取り違えた例「ドッカー」→「ロッカー」を真似る）。
CONFUSABLE_KANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモラリルレロガギグゲゴダデドバビブベボパピプペポ"
# 文頭を取り違えたときに先頭へ付く文字の例（dev-sayの「a React」「の」など）。
STRAY_HEADS = ("a ", "の", "ん", "え")
# 話したフィラーの語形ごとの、Haasが書く語形と割合（空文字は書かない）。合成音声のtrainで、話し言葉と
# two-passの出力を文字単位で対応づけて数えた（各語形の出現数は数百〜約5,000）。ここに無い語形はそのまま書く。
FILLER_RENDERINGS: dict[str, tuple[tuple[str, float], ...]] = {
    "えーと": (("ええと", 0.32), ("えっと", 0.31), ("えーと", 0.30), ("えーっと", 0.05), ("", 0.02)),
    "えっと": (("えっと", 0.69), ("ええと", 0.17), ("えーと", 0.11), ("えーっと", 0.01), ("", 0.02)),
    "あのー": (("あの", 0.93), ("あのー", 0.05), ("", 0.02)),
    "あの": (("あの", 0.99), ("", 0.01)),
    "その": (("その", 0.99), ("", 0.01)),
    "うーん": (("うーん", 0.50), ("うん", 0.27), ("んー", 0.09), ("ん", 0.02), ("", 0.12)),
    "あー": (("あー", 0.45), ("ああ", 0.31), ("あ", 0.15), ("", 0.09)),
    "えー": (("えー", 0.50), ("え", 0.26), ("ええ", 0.05), ("", 0.19)),
    "まあ": (("まあ", 0.88), ("ま", 0.11), ("", 0.01)),
    "んー": (("ん", 0.55), ("んー", 0.25), ("", 0.20)),
}
# 用語集に無い英字の語（ヒントが付かない英語の句）を読みのカタカナで書く割合。残りは近い音のカタカナに崩す。
# trainのtwo-passで、用語集に無い語4,686回のうちカタカナ読み61%、それ以外37%だった。
UNHINTED_KATAKANA = 0.6
# 本人の声でのHaasの句読点（dev-userの読み上げ50件の集計値。合成音声では文末の句点40%、読点は話し言葉の62%）。
USER_DROP_COMMA = 0.5  # 読点を1つごとに落とす確率（読点の比 62%→31%）
USER_ADD_FINAL_PERIOD = 0.7  # 文末に句読点が無い文へ句点を足す確率（文末の句点 40%→82%）
USER_STRIP_ALL = 0.05  # 句読点をすべて消す確率（句読点が1つも無い出力 3%→8%）
# 文末とみなす句読点。
SENTENCE_END = ("。", "?", "!", "？", "！")
# 実ASRで見つけた率を、v3で各型を作れる行の割合に合わせた条件付き確率。
# v3は56,971行中、長い候補との置換が19,394行、表記後の読み残りが44,764行で作れる。
LONG_CONFUSABLE_REPLACEMENT_RATE = (60 / 9_990) / (19_394 / 56_971)
RESIDUAL_KATAKANA_RATE = (607 / 9_990) / (44_764 / 56_971)
# 実ASRで、繰り返し語の一方だけ置換できる行は995件中6件だった。
REPEATED_CONFUSABLE_REPLACEMENT_RATE = 6 / 995


@dataclass(frozen=True)
class AsrNoiseConfig:
    """加工の確率。フィラーと用語は1か所ごと、句読点は1つごと、その他は1文ごとに独立に引く。

    既定値はtwo-pass（用語のヒントあり）の出力に合わせた値。ヒント無しの値は`HAAS_NOHINT`。
    """

    drop_filler: float = 0.1  # `FILLER_RENDERINGS`の脱落とは別にフィラーを落とす（本人の声の残存82%へ寄せる）
    filler_ellipsis: float = 0.1  # 残したフィラーの後ろに「...」を書く（出力の15%に「...」がある）
    term_lower: float = 0.0  # 用語を小文字の英字で書く（two-passでは綴りの崩れの一部が小文字になるため0）
    term_katakana: float = 0.03  # 用語を読みのカタカナで書く
    term_misspell: float = 0.14  # 用語の英字の綴りを崩す
    term_kana_typo: float = 0.17  # 用語を近い音のカタカナに崩す
    latin_spaces: float = 0.005  # 英字の用語の前後に空白を入れる
    drop_comma: float = 0.38  # 読点を落とす（読点の比 62%）
    drop_mid_period: float = 0.2  # 文中の句点を落とす
    drop_final_period: float = 0.6  # 文末の句点を落とす（文末の句点 40%）
    corrupt_head: float = 0.08  # 文頭の1〜2文字を落とすか、余分な文字を付ける（dev-sayの観察。合成音声では未測定）


# two-passの出力（実出力の用語：表記通り70%、小文字3%、カタカナ3%、それ以外24%）。音声のあるtrainにこの加工をかけて
# 同じ数え方をすると、表記通り71%、小文字7%、カタカナ3%、それ以外19%になる。
HAAS_TWOPASS = AsrNoiseConfig()
# ヒント無しの出力（実出力の用語：表記通り0%、小文字29%、カタカナ38%、それ以外33%。加工後は2%、29%、40%、31%）。
HAAS_NOHINT = AsrNoiseConfig(term_lower=0.15, term_katakana=0.38, term_misspell=0.2, term_kana_typo=0.27)


def misspell(surface: str, rng: random.Random) -> str:
    """英字の表記を、ASRが出しがちな崩れ方（1文字の脱落、途中の空白、数字の前の空白、空白の除去）のどれかにする。"""
    choice = rng.randrange(4)
    if choice == 0 and len(surface) > 3:
        i = rng.randrange(1, len(surface) - 1)
        return surface[:i] + surface[i + 1 :]
    if choice == 1 and len(surface) > 4:
        i = rng.randrange(2, len(surface) - 1)
        return (surface[:i] + " " + surface[i:]).lower()
    if choice == 2 and re.search(r"[A-Za-z]\d", surface):
        return re.sub(r"([A-Za-z])(\d)", r"\1 \2", surface, count=1).lower()  # 「BF16」→「bf 16」
    return surface.replace(" ", "").lower()


def kana_typo(reading: str, rng: random.Random) -> str:
    """カタカナの読みの1文字を別のカタカナへ差し替える。"""
    i = rng.randrange(len(reading))
    return reading[:i] + rng.choice(CONFUSABLE_KANA) + reading[i + 1 :]


def _render_term(surface: str, reading: str, rng: random.Random, config: AsrNoiseConfig, hinted: bool) -> str:
    """1つの用語を、ASRが書きそうな形に変える。`hinted`が偽の語はヒントが付かない英語の句として扱う。"""
    if not hinted:
        return reading if rng.random() < UNHINTED_KATAKANA else kana_typo(reading, rng)
    r = rng.random()
    if r < config.term_katakana:
        return reading
    r -= config.term_katakana
    if r < config.term_kana_typo:
        return kana_typo(reading, rng)
    r -= config.term_kana_typo
    if r < config.term_lower:
        text = surface.lower()
    elif r - config.term_lower < config.term_misspell:
        text = misspell(surface, rng)
    else:
        text = surface
    if rng.random() < config.latin_spaces:
        text = f" {text} "
    return text


def _render_filler(form: str, rng: random.Random, config: AsrNoiseConfig) -> str:
    """1つのフィラーを、Haasが書く語形にする。空文字は落としたことを表す。"""
    if rng.random() < config.drop_filler:
        return ""
    choices = FILLER_RENDERINGS.get(form)
    if not choices:
        return form
    return rng.choices([c[0] for c in choices], weights=[c[1] for c in choices])[0]


def _render_punctuation(text: str, rng: random.Random, config: AsrNoiseConfig) -> str:
    """読点と句点を確率で落とし、全角の「？」「！」を半角にする。"""
    out = []
    for i, c in enumerate(text):
        if c == "、" and rng.random() < config.drop_comma:
            continue
        if c == "。":
            is_final = i == len(text) - 1
            if rng.random() < (config.drop_final_period if is_final else config.drop_mid_period):
                continue
        out.append({"？": "?", "！": "!"}.get(c, c))
    return "".join(out)


def plan_two_pass_error_overrides(
    marked: str, glossary: Sequence[dict], rng: random.Random
) -> tuple[dict[tuple[str, int], str], dict[tuple[str, int], str], tuple[str, ...]]:
    """音声の無い文で、実ASRに見つかった誤り型を一回目・二回目の組にする。"""
    occurrences: dict[str, list[tuple[int, str]]] = {}
    for match in MARK_PATTERN.finditer(marked):
        if match.group(1) is not None:
            continue
        surface, reading = match.group(2), match.group(3)
        indexed = occurrences.setdefault(surface, [])
        indexed.append((len(indexed), reading))

    hinted_surfaces = {
        entry.get("surface")
        for entry in glossary
        if isinstance(entry, dict) and isinstance(entry.get("surface"), str)
    }
    target_surfaces = set(occurrences)
    distractors = [surface for surface in hinted_surfaces if surface not in target_surfaces]
    first_overrides: dict[tuple[str, int], str] = {}
    second_overrides: dict[tuple[str, int], str] = {}
    patterns: list[str] = []
    used_surfaces: set[str] = set()

    # 2回目の誤置換で、1回目の読みが正しい手がかりになる組を作る。
    long_distractors = [surface for surface in distractors if len(surface) >= 10]
    replaceable = [
        (surface, index, reading)
        for surface, mentions in occurrences.items()
        if surface in hinted_surfaces
        for index, reading in mentions
    ]
    if long_distractors and replaceable and rng.random() < LONG_CONFUSABLE_REPLACEMENT_RATE:
        surface, index, reading = rng.choice(replaceable)
        first_overrides[(surface, index)] = reading
        second_overrides[(surface, index)] = rng.choice(long_distractors)
        patterns.append("long_confusable_replacement")
        used_surfaces.add(surface)

    # 同じ用語の繰り返しでは、1回目を両方正しく読み、2回目は片方だけ別語へ変える。
    repeated = [
        (surface, mentions)
        for surface, mentions in occurrences.items()
        if surface in hinted_surfaces and len(mentions) >= 2 and surface not in used_surfaces
    ]
    if distractors and repeated and rng.random() < REPEATED_CONFUSABLE_REPLACEMENT_RATE:
        surface, mentions = rng.choice(repeated)
        first_overrides[(surface, mentions[0][0])] = mentions[0][1]
        first_overrides[(surface, mentions[1][0])] = mentions[1][1]
        second_overrides[(surface, mentions[0][0])] = surface
        second_overrides[(surface, mentions[1][0])] = rng.choice(distractors)
        patterns.append("repeated_confusable_replacement")
        used_surfaces.add(surface)

    # 英字表記の後ろに読みの末尾が残る入力を、読み末尾の1〜2文字で再現する。
    residual_targets = [
        (surface, index, reading)
        for surface, mentions in occurrences.items()
        if surface in hinted_surfaces and re.search(r"[A-Za-z]", surface) and surface not in used_surfaces
        for index, reading in mentions
        if re.search(r"[ァ-ヺ]", reading)
    ]
    if residual_targets and rng.random() < RESIDUAL_KATAKANA_RATE:
        surface, index, reading = rng.choice(residual_targets)
        kana_runs = re.findall(r"[ァ-ヺー]+", reading)
        suffix = kana_runs[-1][-2:]
        second_overrides[(surface, index)] = surface + suffix
        patterns.append("residual_katakana")

    return first_overrides, second_overrides, tuple(patterns)


def simulate_asr_noise(
    marked: str,
    rng: random.Random,
    config: AsrNoiseConfig = HAAS_TWOPASS,
    hinted: frozenset[str] | set[str] | None = None,
    term_overrides: Mapping[tuple[str, int], str] | None = None,
) -> str:
    """`spoken_marked`の文から、ASRの出力に似せた文を作る。正解の`target_text`は変えない。

    `hinted`はtwo-passでヒントが付く用語（その行の用語集の表記）。省略時はすべての英字の語にヒントが付くとみなす。
    """
    pieces: list[str] = []
    pos = 0
    after_filler = ""  # 直前のフィラーの扱い（""：無し、"drop"：落とした、"ellipsis"：後ろに「...」を書く）
    occurrence_counts: dict[str, int] = {}
    for m in MARK_PATTERN.finditer(marked):
        plain = marked[pos : m.start()]
        if after_filler and plain[:1] in ("、", ","):
            plain = plain[1:]  # 落としたフィラーの読点、または「...」に置き換える読点
        if after_filler == "ellipsis":
            pieces.append("...")
        pieces.append(plain)
        after_filler = ""
        if m.group(1) is not None:
            rendered = _render_filler(m.group(1), rng, config)
            pieces.append(rendered)
            if not rendered:
                after_filler = "drop"
            elif rng.random() < config.filler_ellipsis:
                after_filler = "ellipsis"
        else:
            surface = m.group(2)
            occurrence = occurrence_counts.get(surface, 0)
            occurrence_counts[surface] = occurrence + 1
            override = term_overrides.get((surface, occurrence)) if term_overrides else None
            pieces.append(
                override
                if override is not None
                else _render_term(surface, m.group(3), rng, config, hinted is None or surface in hinted)
            )
        pos = m.end()
    tail = marked[pos:]
    if after_filler and tail[:1] in ("、", ","):
        tail = tail[1:]
    if after_filler == "ellipsis":
        pieces.append("...")
    pieces.append(tail)
    text = _render_punctuation("".join(pieces), rng, config)
    if len(text) > 4 and rng.random() < config.corrupt_head:
        text = text[rng.randint(1, 2) :] if rng.random() < 0.5 else rng.choice(STRAY_HEADS) + text
    return text.strip()


def to_user_punctuation(text: str, rng: random.Random) -> str:
    """ASRの出力（実出力または加工した文）の句読点を、本人の声でのHaasの付き方へ寄せる。

    合成音声のHaasは文末の句点が少なく読点が多い。本人の声ではその逆のため、読点を減らし文末に句点を足す。
    """
    if rng.random() < USER_STRIP_ALL:
        return text.replace("、", "").replace("。", "")
    text = "".join(c for c in text if not (c == "、" and rng.random() < USER_DROP_COMMA))
    if text and not text.endswith(SENTENCE_END) and rng.random() < USER_ADD_FINAL_PERIOD:
        text += "。"
    return text


def main() -> None:
    """manifestの各行に、行のidから決まる乱数でtwo-pass相当の加工をかけ、ASRの推論結果と同じ形式で書き出す。"""
    parser = argparse.ArgumentParser(description="ASRに似せた入力を作り、推論結果の形式で書き出す")
    parser.add_argument("--input", required=True, help="`spoken_marked`を持つJSONL")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as f, open(args.out, "w", encoding="utf-8") as out:
        for line in f:
            row = json.loads(line)
            rng = random.Random(f"{args.seed}-{row['id']}")
            hinted = {g["surface"] for g in row.get("glossary", [])}
            hyp = simulate_asr_noise(row["spoken_marked"], rng, hinted=hinted)
            record = {"id": row["id"], "system": "asrsim-haas", "stage": "asr", "hyp": hyp, "latency_s": 0.0}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
