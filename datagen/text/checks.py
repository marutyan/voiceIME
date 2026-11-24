"""教師LLMが作った話し言葉と整形後の文の組を、データの行へ変換しながら自動で検査する。

検査に落ちた組は捨て、理由ごとの件数を数える。検査の項目はdata/text/README.mdにも書く。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from common import KATAKANA_CHAR, KATAKANA_USUAL_WORDS, has_latin
from sentence_prompts import UNITS

# 話し言葉の [[英字|読み]] の印。英字部分と読み部分に [ ] | を含まない。
TAG_RE = re.compile(r"\[\[([^\[\]|]+)\|([^\[\]|]+)\]\]")
# 話し言葉の {フィラー} の印。
FILLER_RE = re.compile(r"\{([^{}]+)\}")

# フィラーとして認める語の基本形。長音「ー」と促音「っ」、末尾の読点を除いて比べる。
# 長音を除くと「えーと」は「えと」、「うーん」は「うん」になる。
FILLER_BASES = {
    "え", "ええ", "えと", "ええと", "えっと", "えと", "あの", "あ", "ああ", "う", "うん", "ん", "んと",
    "まあ", "ま", "なんか", "なんかこう", "その", "こう", "ほら", "あのね", "えとですね", "あのですね",
}

# 印を付け忘れたフィラーを見つけるための、フィラーとしか読めない語。
# 「その」「まあ」などは普通の語としても使うため、ここには入れない。
STRONG_FILLER_RE = re.compile(r"えーっと|えーと|えっと|ええと|えー|あのー|うーん|んー|あー")

# 言い直しありの条件で、話し言葉に現れるべき言葉。
RESTATEMENT_RE = re.compile(r"いや|じゃなくて|じゃなく|やっぱ|訂正|違う|違った|ちがう|っていうか|というか|間違え|ごめん")

# 用語集から除いた一般語のうち、制御構文の予約語。「if文」を「イフ文」とするようにカタカナに直すと
# 不自然な文になるため、用語集には入れないが、整形後の文では英字のまま残す。
LATIN_KEYWORDS = frozenset(
    "if else for from while def except finally yield async await try break continue".split()
)

# 日本語の文字（かな、漢字、全角の記号）。英字との間の空白を除くときに使う。
JA_CHAR = r"ぁ-んァ-ヺー一-龯々、。，．！？「」『』（）・"

# 「変更なし」の判定で無視する句読点と空白。
PUNCT_RE = re.compile(r"[、。，．,.!?！？\s]")

# 同じ英字の語を話し言葉で繰り返してよい回数の上限。教師LLMが同じ語を延々と繰り返す失敗を除くために置く。
MAX_TAG_REPEAT = 3

# 読み上げ時間の推定に使う、1秒あたりの文字数（漢字かな交じりの話し言葉）。
CHARS_PER_SEC = 6.0
# 課題の読み上げ時間の範囲（3〜30秒）に、推定の誤差のための余裕を持たせた範囲。
MIN_SEC, MAX_SEC = 2.5, 32.0


def filler_base(text: str) -> str:
    """フィラーの表記から長音、促音、句読点を除いた基本形を返す。"""
    return re.sub(r"[ー〜~っッ、。,.\s]", "", text) or text


def estimate_seconds(spoken_kana: str) -> float:
    """カタカナ読みの話し言葉から、読み上げにかかる秒数をおおまかに推定する。"""
    n = len(re.sub(r"[、。，．,.!?！？\s「」『』（）()]", "", spoken_kana))
    return n / CHARS_PER_SEC


@dataclass
class Glossary:
    """用語集と、検査に使う一括検索用の正規表現を持つ。"""

    terms: dict[str, dict]  # surface -> 用語集の行
    reading_owner: dict[str, str]  # 読み -> surface
    reading_re: re.Pattern[str]  # 3文字以上の読みを前後のカタカナ境界つきで一括検索する
    held_out_surface_re: re.Pattern[str]  # held-outの表記を前後の英数字境界つきで一括検索する
    surface_re: re.Pattern[str]  # すべての表記を前後の英数字境界つきで一括検索する（印の付け忘れの修復用）

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "Glossary":
        """用語集の行から、検査用の辞書と一括検索の正規表現を作る。"""
        terms = {r["surface"]: r for r in rows}
        owner = {rd: r["surface"] for r in rows for rd in r["readings"]}
        # 2文字以下の読み（例：ゴー）は普通の語とよく重なるため、書き忘れの検査には使わない。
        long_readings = sorted((rd for rd in owner if len(rd) >= 3), key=len, reverse=True)
        reading_re = re.compile(
            rf"(?<![{KATAKANA_CHAR}])(?:" + "|".join(map(re.escape, long_readings)) + rf")(?![{KATAKANA_CHAR}])"
        )
        held = sorted((r["surface"] for r in rows if r["split"] == "held-out"), key=len, reverse=True)
        held_re = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(map(re.escape, held)) + r")(?![A-Za-z0-9])")
        alls = sorted(terms, key=len, reverse=True)
        surface_re = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(map(re.escape, alls)) + r")(?![A-Za-z0-9])")
        return cls(terms, owner, reading_re, held_re, surface_re)


class Reject(Exception):
    """検査に落ちたことを、理由の短い名前とともに知らせる。"""


def repair_spoken(spoken: str, gl: Glossary) -> str:
    """教師LLMの印の付け方の誤りのうち、正しい形が一つに決まるものだけを直す。

    - [[えーと]] のように英字の印で囲んだフィラーを {えーと} にする。
    - 印の外に用語集の表記がそのまま書かれていれば、最初の読みで印を付ける。
    - 用語集の語の読みの部分に英字が書かれていれば（例：[[SAM|SAM]]）、最初の読みに置き換える。
    """
    spoken = re.sub(
        r"\[\[([^\[\]|A-Za-z]+)\]\]",
        lambda m: "{" + m.group(1) + "}" if filler_base(m.group(1)) in FILLER_BASES else m.group(0),
        spoken,
    )

    def fix_tag(m: re.Match[str]) -> str:
        latin, kana = m.group(1).strip(), m.group(2).strip()
        if latin in gl.terms and has_latin(kana):
            return f"[[{latin}|{gl.terms[latin]['readings'][0]}]]"
        return m.group(0)

    spoken = TAG_RE.sub(fix_tag, spoken)
    parts = re.split(r"(\[\[[^\[\]]*\]\])", spoken)
    for k in range(0, len(parts), 2):  # 偶数番目が印の外
        parts[k] = gl.surface_re.sub(lambda m: f"[[{m.group(0)}|{gl.terms[m.group(0)]['readings'][0]}]]", parts[k])
    return "".join(parts)


def repair_target(target: str) -> str:
    """整形後の文に話し言葉の印が残る誤りのうち、正しい形が一つに決まるものだけを直す。

    {フィラー} は直後の読点ごと消し、[[英字|読み]] は英字表記にする。どちらも整形の規則そのものである。
    英字と日本語の間の空白（例「sanity check もしておかないと」）は、日本語の文では書かないので除く。
    """
    target = re.sub(r"\{[^{}]*\}、?", "", target)
    target = TAG_RE.sub(lambda m: m.group(1).strip(), target)
    target = re.sub(rf"(?<=[A-Za-z0-9])[ 　]+(?=[{JA_CHAR}])", "", target)
    target = re.sub(rf"(?<=[{JA_CHAR}])[ 　]+(?=[A-Za-z0-9])", "", target)
    return target.strip()


def untag_katakana_words(spoken: str, dropped: str, target: str) -> tuple[str, str, str]:
    """カタカナで書くのが普通の一般語（KATAKANA_USUAL_WORDS）の印を外し、カタカナのまま残す。

    話し言葉と取り消した部分では [[set|セット]] を「セット」にし、整形後の文の「set」は
    話し言葉で使われた読み（例：セット）に置き換える。制御構文の予約語（LATIN_KEYWORDS）は、
    カタカナにすると不自然になる（例：「イフ文」）ため、印も整形後の英字もそのまま残す。
    """
    kana_of: dict[str, str] = {}

    def untag(m: re.Match[str]) -> str:
        latin, kana = m.group(1).strip(), m.group(2).strip()
        if latin in KATAKANA_USUAL_WORDS and latin not in LATIN_KEYWORDS:
            kana_of.setdefault(latin, kana)
            return kana
        return m.group(0)

    spoken, dropped = TAG_RE.sub(untag, spoken), TAG_RE.sub(untag, dropped)
    for latin, kana in kana_of.items():
        target = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(latin) + r"(?![A-Za-z0-9_])", kana, target)
    return spoken, dropped, target


def render_spoken(marked: str) -> tuple[str, str]:
    """印つきの話し言葉から、カタカナ読みの文と、英字を残した文を作って返す。"""
    kana = FILLER_RE.sub(lambda m: m.group(1), TAG_RE.sub(lambda m: m.group(2).strip(), marked))
    mixed = FILLER_RE.sub(lambda m: m.group(1), TAG_RE.sub(lambda m: m.group(1).strip(), marked))
    return kana, mixed


def is_no_change(spoken_kana: str, target: str) -> bool:
    """句読点と空白を除くと、話し言葉と整形後の文が同じ文字の並びかを返す。"""
    return PUNCT_RE.sub("", spoken_kana) == PUNCT_RE.sub("", target)


def plain_text(marked: str) -> str:
    """印つきの話し言葉から、フィラーと句読点と空白を除き、英字の語を英字表記にした文字列を返す。"""
    text = TAG_RE.sub(lambda m: m.group(1).strip(), FILLER_RE.sub("", marked))
    return PUNCT_RE.sub("", text)


def convert(spec: dict, spoken: str, target: str, gl: Glossary, dropped: object = "") -> dict:
    """教師LLMの出力1件を検査し、データの行（id、glossaryなどは除く）へ変換する。

    検査に落ちた場合はReject（理由つき）を投げる。split が train / val の場合は held-out の用語が
    文に一切出ないことも確かめる。
    """
    if not isinstance(spoken, str) or not isinstance(target, str) or not spoken.strip() or not target.strip():
        raise Reject("empty_field")
    spoken, target = repair_spoken(spoken.strip(), gl), repair_target(target.strip())
    dropped = repair_spoken(dropped.strip(), gl) if isinstance(dropped, str) else ""
    spoken, dropped, target = untag_katakana_words(spoken, dropped, target)
    # 用語集から除いた一般語は、指定した用語として扱わない
    assigned = [t for t in spec["terms"] if t["surface"] not in KATAKANA_USUAL_WORDS]
    allow_held_out = spec["split"] == "test"

    # 1. 印の形。話し言葉に改行や箇条書きは無い
    if "\n" in spoken:
        raise Reject("newline_in_spoken")
    if re.search(r"[{}]|\[\[|\]\]|\|", target):
        raise Reject("markup_in_target")
    stripped = FILLER_RE.sub("", TAG_RE.sub("", spoken))
    if re.search(r"[{}\[\]|]", stripped):
        raise Reject("broken_markup_in_spoken")
    if has_latin(stripped):
        raise Reject("untagged_latin_in_spoken")

    # 2. フィラー
    fillers = FILLER_RE.findall(spoken)
    for f in fillers:
        if filler_base(f) not in FILLER_BASES:
            raise Reject("unknown_filler")
    if spec["filler_level"] == "none" and fillers:
        raise Reject("filler_level_mismatch")
    if spec["filler_level"] != "none" and not fillers:
        raise Reject("filler_level_mismatch")
    if STRONG_FILLER_RE.search(FILLER_RE.sub("", spoken)):
        raise Reject("unmarked_filler")
    if STRONG_FILLER_RE.search(target):
        raise Reject("filler_in_target")

    # 3. 英字の印と用語
    tags = TAG_RE.findall(spoken)
    tag_terms: list[str] = []
    n_phrases = 0
    for latin, kana in tags:
        latin, kana = latin.strip(), kana.strip()
        if not has_latin(latin) or has_latin(kana):
            raise Reject("bad_tag")
        if latin in gl.terms:
            term = gl.terms[latin]
            if kana not in term["readings"]:
                raise Reject("reading_not_in_glossary")
            if term["split"] == "held-out" and not allow_held_out:
                raise Reject("held_out_leak")
            if latin not in tag_terms:
                tag_terms.append(latin)
        else:
            lower = {s.lower(): s for s in gl.terms}
            if latin.lower() in lower:
                raise Reject("surface_case_mismatch")
            if latin in LATIN_KEYWORDS:
                pass  # 用語集に入れない予約語。英字のまま整形後の文に残す
            elif latin in UNITS:
                if not spec["numbers"]:
                    raise Reject("unrequested_latin")
            elif not spec["english_phrase"]:
                raise Reject("unrequested_latin")
            else:
                n_phrases += 1
    if spec["english_phrase"] and n_phrases == 0:
        raise Reject("english_phrase_missing")
    for t in assigned:
        if t["surface"] not in tag_terms:
            raise Reject("assigned_term_missing_in_spoken")
    if any(n > MAX_TAG_REPEAT for n in Counter(l.strip() for l, _ in tags).values()):
        raise Reject("excessive_repetition")

    spoken_kana, spoken_mixed = render_spoken(spoken)
    if has_latin(spoken_kana):
        raise Reject("latin_in_spoken_kana")

    # 4. 整形後の文：用語の表記と、印の無い英字が無いこと
    terms = [s for s in tag_terms if re.search(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", target)]
    for t in assigned:
        # 言い直しで取り消した部分にだけ現れる用語は、正解に無くてよい
        in_dropped = f"[[{t['surface']}|" in dropped
        if t["surface"] not in terms and not (spec["restatement"] and in_dropped):
            raise Reject("assigned_term_missing_in_target")
    rest = target
    for latin in sorted({l.strip() for l, _ in tags}, key=len, reverse=True):
        rest = rest.replace(latin, "")
    if has_latin(rest):
        raise Reject("untagged_latin_in_target")

    # 5. 読みの書き忘れ：印の外に用語の読みがあると、用語集と正解が食い違う
    plain_spoken = FILLER_RE.sub(lambda m: m.group(1), TAG_RE.sub("", spoken))
    for m in gl.reading_re.finditer(plain_spoken):
        owner = gl.terms[gl.reading_owner[m.group(0)]]
        if owner["surface"] in tag_terms:
            raise Reject("term_reading_untagged")
        if owner["split"] == "held-out" and not allow_held_out:
            raise Reject("held_out_reading_leak")
        if owner["style"] == "latin":
            raise Reject("latin_term_reading_untagged")

    # 6. held-outの表記の漏れ（train / val）
    if not allow_held_out and (gl.held_out_surface_re.search(target) or gl.held_out_surface_re.search(spoken_mixed)):
        raise Reject("held_out_leak")

    # 7. 条件との一致：長さ、言い直し、書き足し
    sec = estimate_seconds(spoken_kana)
    if not (MIN_SEC <= sec <= MAX_SEC):
        raise Reject("duration_out_of_range")
    if spec["restatement"]:
        # 取り消した部分（dropped）が話し言葉にあり、その後に言い直しの言葉が続き、正解に残っていないこと
        if not dropped:
            raise Reject("restatement_dropped_missing")
        pos = spoken.find(dropped)
        if pos < 0:
            raise Reject("restatement_dropped_not_in_spoken")
        # 言い直しの言葉は、取り消した部分の直後か、取り消した部分の末尾（言葉まで含めて書いた場合）にある
        end = pos + len(dropped)
        if not RESTATEMENT_RE.search(spoken[max(pos, end - 12) : end + 20]):
            raise Reject("restatement_marker_missing")
        dropped_plain = plain_text(dropped)
        if len(dropped_plain) >= 2 and dropped_plain in PUNCT_RE.sub("", target):
            raise Reject("restatement_dropped_kept_in_target")
    body = re.sub(r"^- ", "", target, flags=re.M).replace("\n", "")
    if len(body) > len(FILLER_RE.sub("", TAG_RE.sub(lambda m: m.group(1), spoken))) * 1.1 + 8:
        raise Reject("target_longer_than_spoken")
    n_bullets = len(re.findall(r"^- \S", target, flags=re.M))
    if spec["enumeration"] and n_bullets < 2:
        raise Reject("list_not_bulleted")
    # 変更なし：句読点と空白を除くと話し言葉と整形後の文が同じ文字の並びになる
    no_change = is_no_change(spoken_kana, target)
    if spec["no_change"] and not no_change:
        raise Reject("no_change_mismatch")

    tags_out = []
    if spec["restatement"]:
        tags_out.append("self_correction")
    if no_change:
        tags_out.append("no_change")
    if spec["instruction_like"]:
        tags_out.append("instruction_like")
    if n_bullets >= 2:
        tags_out.append("list")
    if n_phrases:
        tags_out.append("english_phrase")

    return {
        "spoken_text": spoken_kana,
        "spoken_text_kana": spoken_kana,
        "spoken_text_mixed": spoken_mixed,
        "target_text": target,
        "terms": terms,
        "spoken_terms": tag_terms,
        "fillers": len(fillers),
        "tags": tags_out,
        "spoken_marked": spoken,
        "dropped": dropped if spec["restatement"] else "",
        "est_seconds": round(sec, 1),
    }

