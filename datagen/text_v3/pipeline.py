"""用語集v2から整形用LLMの学習文と初見語評価文を計画・検査する。"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import ChainMap, Counter
from pathlib import Path
from typing import Any, Iterable

# 第1版の検査と条件・プロンプトを直接再利用し、既存パッケージの境界は変えない。
TEXT_V1_DIR = Path(__file__).resolve().parents[1] / "text"
if str(TEXT_V1_DIR) not in sys.path:
    sys.path.insert(0, str(TEXT_V1_DIR))

from checks import Glossary, Reject, convert  # noqa: E402
from common import CATEGORIES, SEED, has_latin, parse_items, read_jsonl, surface_pattern, write_jsonl  # noqa: E402
from sentence_prompts import (  # noqa: E402
    ENGLISH_PHRASES,
    SYSTEM as V1_SYSTEM,
    TONES,
    TOPIC_HINTS,
    USER_HEADER,
    render_item,
)
from sentences import (  # noqa: E402
    FILLER_WEIGHTS,
    FREE_USECASES,
    GENERAL_USECASES,
    INSTRUCTION_USECASES,
    LENGTH_WEIGHTS,
    MAX_ZERO_TERMS_RATIO,
    N_TERMS_WEIGHTS,
    P_ENGLISH,
    P_ENUMERATION,
    P_INSTRUCTION,
    P_NUMBERS,
    P_RESTATEMENT,
    P_DISFLUENCY,
    RESTATEMENT_MARKERS,
    pick,
)

# 正解語を用語集から外した例を学習行の約15%にする。
DEFAULT_GLOSSARY_DROP_RATIO = 0.15
# 同じプロンプト構成を維持し、要求1件あたり8文を教師へまとめて送る。
DEFAULT_BATCH_SIZE = 8
# 第1版の教師要求と同じ長さ上限を使う。
DEFAULT_MAX_TOKENS = 4000
# 初見語評価の既定件数。
DEFAULT_NOVEL_COUNT = 400
# 第2版で新しく追加した語は、fame 1・2だけを割当対象にする。
ELIGIBLE_NEW_FAME = frozenset({1, 2})
# 行ごとに最大5個の近音語を各正解語へ混ぜる。
MAX_CONFUSABLES_PER_TERM = 5
# 要求へ追加で割り当てる数。無効出力に備えた余裕で、最終データは最低数で検査する。
DEFAULT_OVERGENERATION = 1.5
# test-novel の正解 terms に含めてよい train 語の割合。新規 held-out 語だけを使うため0を既定とする。
DEFAULT_MAX_NOVEL_TRAIN_RATIO = 0.0

# 旧プロンプトの用途・長さ・フィラー・言い直し・タグの規則を保ち、辞書の意味だけを明示する。
SYSTEM_V3 = V1_SYSTEM + """

## 行ごとの用語集と出力
- 各条件の「推論時に渡す用語集」は、モデルが実際に見る辞書です。用語集にある語の読みが発話に出たときだけ、その表記へ直してください。
- 用語集にある音の近い語は、誤って選びやすい無関係な候補です。発話でその語が話された場合を除き、正解文へ入れてはいけません。
- 用語集に無い語は、知識だけを理由に英字へ変換しないでください。ASRが出したカタカナや崩れた読みを正解にも残し、明白な聞き間違いだけ読みの範囲で最小限に直してください。
- 用語集に無い語も、話された内容を削除せず、話していない用語を追加しないでください。
- 指示の形式どおり、各条件の`spoken`、`target`、言い直しがある場合の`dropped`をJSONで返してください。
"""


def load_glossary(path: Path) -> list[dict[str, Any]]:
    """用語集を読み、第1版の検査が必要とする項目を補って形式を確かめる。"""
    rows: list[dict[str, Any]] = []
    surfaces: set[str] = set()
    for line_number, raw in enumerate(read_jsonl(path), start=1):
        row = dict(raw)
        surface = row.get("surface")
        readings = row.get("readings")
        if not isinstance(surface, str) or not surface.strip():
            raise ValueError(f"{path}:{line_number}: surfaceは空でない文字列が必要です")
        if surface in surfaces:
            raise ValueError(f"{path}:{line_number}: surfaceが重複しています: {surface}")
        if not isinstance(readings, list) or not readings or not all(isinstance(value, str) and value for value in readings):
            raise ValueError(f"{path}:{line_number}: readingsは空でない文字列の配列が必要です")
        if row.get("split") not in {"train", "held-out"}:
            raise ValueError(f"{path}:{line_number}: splitはtrainまたはheld-outが必要です")
        if row.get("category") not in CATEGORIES:
            raise ValueError(f"{path}:{line_number}: 未知のcategoryです: {row.get('category')}")
        # v2の予定形式にはstyleが無い場合があるため、表記から検査用の値だけ導く。
        if row.get("style") not in {"latin", "either"}:
            row["style"] = "latin" if has_latin(surface) else "either"
        surfaces.add(surface)
        rows.append(row)
    if not rows:
        raise ValueError(f"{path}: 用語がありません")
    return rows


def load_confusables(
    path: Path, glossary_by_surface: dict[str, dict[str, Any]]
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """近音語一覧を読み、用語集から消えた候補数も返す。"""
    result: dict[str, list[dict[str, Any]]] = {}
    stale_references = 0
    for line_number, row in enumerate(read_jsonl(path), start=1):
        owner = row.get("surface")
        candidates = row.get("confusables")
        if not isinstance(owner, str) or not isinstance(candidates, list):
            raise ValueError(f"{path}:{line_number}: surfaceとconfusablesの形式が不正です")
        if owner not in glossary_by_surface:
            stale_references += len(candidates)
            continue
        parsed: list[dict[str, Any]] = []
        for candidate in candidates:
            if isinstance(candidate, str):
                surface, related = candidate, False
            elif isinstance(candidate, dict):
                surface, related = candidate.get("surface"), candidate.get("related", False)
            else:
                raise ValueError(f"{path}:{line_number}: confusablesの要素は文字列またはobjectが必要です")
            if not isinstance(surface, str):
                raise ValueError(f"{path}:{line_number}: confusable surfaceは文字列が必要です")
            if surface not in glossary_by_surface:
                stale_references += 1
                continue
            if surface != owner and related is not True:
                parsed.append(glossary_by_surface[surface])
        result[owner] = parsed[:MAX_CONFUSABLES_PER_TERM]
    return result, stale_references


def new_heldout_terms(
    glossary_rows: list[dict[str, Any]], legacy_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """第1版には無い、用語集v2のheld-out語だけを返す。"""
    legacy_surfaces = {row["surface"] for row in legacy_rows}
    return [row for row in glossary_rows if row["split"] == "held-out" and row["surface"] not in legacy_surfaces]


def load_excluded_terms(path: Path | None) -> set[str]:
    """説明用のコメント行を除き、用語として扱わない表記を読み込む。"""
    if path is None:
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def eligible_training_terms(
    glossary_rows: list[dict[str, Any]],
    legacy_rows: list[dict[str, Any]],
    excluded_surfaces: set[str],
) -> list[dict[str, Any]]:
    """v1のtrain語と、v2で新しく追加されたfame 1・2のtrain語だけを返す。"""
    legacy_train = {row["surface"] for row in legacy_rows if row["split"] == "train"}
    legacy_surfaces = {row["surface"] for row in legacy_rows}
    glossary_by_surface = {row["surface"]: row for row in glossary_rows}
    missing_legacy = legacy_train - glossary_by_surface.keys()
    if missing_legacy:
        raise ValueError(f"glossary-v2にv1 train語がありません: {len(missing_legacy)}語")

    return [
        row
        for row in glossary_rows
        if row["split"] == "train"
        and row["surface"] not in excluded_surfaces
        and (
            row["surface"] in legacy_train
            or (row["surface"] not in legacy_surfaces and row.get("fame") in ELIGIBLE_NEW_FAME)
        )
    ]


def eligible_novel_terms(
    glossary_rows: list[dict[str, Any]],
    legacy_rows: list[dict[str, Any]],
    excluded_surfaces: set[str],
) -> list[dict[str, Any]]:
    """v2で新しく追加されたheld-out語から、除外語とfame 3を外して返す。"""
    return [
        row
        for row in new_heldout_terms(glossary_rows, legacy_rows)
        if row["surface"] not in excluded_surfaces and row.get("fame") in ELIGIBLE_NEW_FAME
    ]


def _make_condition(
    rng: random.Random,
    spec_id: str,
    split: str,
    terms: list[dict[str, Any]],
    *,
    no_change: bool = False,
) -> dict[str, Any]:
    """第1版の条件分布で、用語の割り当て以外の文生成条件を作る。"""
    instruction = not no_change and rng.random() < P_INSTRUCTION
    usecase = pick(rng, INSTRUCTION_USECASES) if instruction else rng.choice(FREE_USECASES)
    if terms:
        domain = terms[0]["category"]
    elif usecase in GENERAL_USECASES and rng.random() < 0.6:
        domain = "general"
    else:
        domain = rng.choice(CATEGORIES)
    length = pick(rng, LENGTH_WEIGHTS) if usecase != "commit-message" else pick(rng, {"short": 0.5, "medium": 0.4, "long": 0.1})
    enumeration = not no_change and rng.random() < P_ENUMERATION
    if enumeration and length == "short":
        length = "medium"
    return {
        "spec_id": spec_id,
        "split": split,
        "usecase": usecase,
        "domain": domain,
        "topic": rng.choice(TOPIC_HINTS[domain]),
        "tone": rng.choice(TONES[usecase]),
        "length": length,
        "no_change": no_change,
        "instruction_like": instruction,
        "filler_level": "none" if no_change else pick(rng, FILLER_WEIGHTS),
        "restatement": None if no_change or rng.random() >= P_RESTATEMENT else rng.choice(RESTATEMENT_MARKERS),
        "disfluency": not no_change and rng.random() < P_DISFLUENCY,
        "enumeration": enumeration,
        "numbers": rng.random() < P_NUMBERS,
        "english_phrase": rng.choice(ENGLISH_PHRASES) if not no_change and rng.random() < P_ENGLISH else None,
        "terms": terms,
    }


def _make_row_glossary(
    planned_terms: list[dict[str, Any]],
    omitted_surfaces: set[str],
    glossary_by_surface: dict[str, dict[str, Any]],
    confusables: dict[str, list[dict[str, Any]]],
    max_confusables: int,
) -> list[dict[str, Any]]:
    """正解語と近音の無関係語を、推論時と同じsurface/readings形式で組み立てる。"""
    focus = {term["surface"] for term in planned_terms}
    entries: dict[str, dict[str, Any]] = {}
    for term in planned_terms:
        surface = term["surface"]
        if surface not in omitted_surfaces:
            entries[surface] = glossary_by_surface[surface]
    for term in planned_terms:
        for candidate in confusables.get(term["surface"], [])[:max_confusables]:
            surface = candidate["surface"]
            if surface not in focus and candidate["split"] == "train":
                # 学習例にはheld-outの表記・読みを辞書の候補としても入れない。
                entries.setdefault(surface, candidate)
    return [{"surface": row["surface"], "readings": list(row["readings"])} for row in entries.values()]


def _format_row_glossary(entries: list[dict[str, Any]]) -> str:
    """推論プロンプトと同じ「読み→表記」の書式にする。"""
    if not entries:
        return "（なし）"
    return "\n".join(f"- {'、'.join(entry['readings'])} → {entry['surface']}" for entry in entries)


def _render_v3_item(index: int, spec: dict[str, Any]) -> str:
    """第1版の条件文に行ごとの辞書内容と、意図的な辞書抜けの指示を足す。"""
    visible_terms = [term for term in spec["terms"] if term["surface"] not in set(spec["omitted_surfaces"])]
    prompt_spec = dict(spec, terms=visible_terms)
    body = render_item(index, prompt_spec)
    lines = [body, "推論時に渡す用語集（実際にモデルへ見せる内容）:\n" + _format_row_glossary(spec["glossary"])]
    omitted = [term for term in spec["terms"] if term["surface"] in set(spec["omitted_surfaces"])]
    if omitted:
        readings = "、".join(term["reading"] for term in omitted)
        lines.append(
            "用語集に無い語（surfaceの英字表記は教師にも示しません）: " + readings
            + "。spokenにはこの読みをカタカナで含め、targetでも英字表記へ変換せず、読みをそのまま残すか明白な崩れだけ最小限に直してください。"
        )
    return "\n".join(lines)


def _pack_term_slots(
    terms: list[dict[str, Any]], repeats: int, rng: random.Random
) -> list[list[dict[str, Any]]]:
    """各語を異なる文へ繰り返し割り当て、1文に1〜4語をまとめる。"""
    groups: list[list[dict[str, Any]]] = []
    for category in CATEGORIES:
        category_terms = [row for row in terms if row["category"] == category]
        slots: list[dict[str, Any]] = []
        for _ in range(repeats):
            cycle = list(category_terms)
            rng.shuffle(cycle)
            slots.extend(cycle)
        while slots:
            requested = int(pick(rng, N_TERMS_WEIGHTS))
            group: list[dict[str, Any]] = []
            used: set[str] = set()
            position = 0
            while position < len(slots) and len(group) < requested:
                candidate = slots[position]
                if candidate["surface"] in used:
                    position += 1
                    continue
                group.append(candidate)
                used.add(candidate["surface"])
                slots.pop(position)
            groups.append(group)
    rng.shuffle(groups)
    return groups


def make_training_specs(
    train_terms: list[dict[str, Any]],
    glossary_by_surface: dict[str, dict[str, Any]],
    confusables: dict[str, list[dict[str, Any]]],
    *,
    minimum_repeats: int = 5,
    overgeneration: float = DEFAULT_OVERGENERATION,
    drop_ratio: float = DEFAULT_GLOSSARY_DROP_RATIO,
    max_confusables: int = MAX_CONFUSABLES_PER_TERM,
    seed: int = SEED,
    id_prefix: str = "train-000",
) -> list[dict[str, Any]]:
    """train語の出現枠を作り、15%の行で正解語を辞書から外した条件を作る。"""
    if minimum_repeats < 1 or overgeneration < 1:
        raise ValueError("minimum_repeatsは1以上、overgenerationは1以上が必要です")
    if not 0 <= drop_ratio <= 1 or not 0 <= max_confusables <= MAX_CONFUSABLES_PER_TERM:
        raise ValueError("drop_ratioまたはmax_confusablesが範囲外です")
    if not train_terms or any(row["split"] != "train" for row in train_terms):
        raise ValueError("train_termsにはsplit=trainの用語だけを指定してください")
    rng = random.Random(f"{seed}-{id_prefix}")
    planned_repeats = max(minimum_repeats, math.ceil(minimum_repeats * overgeneration))
    groups = _pack_term_slots(train_terms, planned_repeats, rng)

    # 第1版同様、train全体の用語なし行を約15%にする。無変更行はそのうち約10%。
    total_rows = math.ceil(len(groups) / (1 - MAX_ZERO_TERMS_RATIO)) if MAX_ZERO_TERMS_RATIO < 1 else len(groups)
    extra_count = max(0, total_rows - len(groups))
    no_change_count = min(extra_count, round(total_rows * 0.10))
    no_change_indices = set(rng.sample(range(extra_count), no_change_count)) if no_change_count else set()
    zero_groups = [[] for _ in range(extra_count)]
    specs: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        assigned = [
            {"surface": row["surface"], "reading": rng.choice(row["readings"]), "category": row["category"]}
            for row in group
        ]
        spec = _make_condition(rng, f"{id_prefix}-{index + 1:06d}", "train", assigned)
        specs.append(spec)
    for index, group in enumerate(zero_groups):
        spec = _make_condition(
            rng,
            f"{id_prefix}-z{index + 1:06d}",
            "train",
            group,
            no_change=index in no_change_indices,
        )
        specs.append(spec)
    rng.shuffle(specs)

    # 辞書抜け行は全体の約15%。各行から1語だけ抜き、他の割当語は通常どおり辞書へ入れる。
    term_specs = [spec for spec in specs if spec["terms"]]
    n_dropped = min(len(term_specs), round(len(specs) * drop_ratio))
    for spec in rng.sample(term_specs, n_dropped):
        omitted = rng.choice(spec["terms"])
        spec["omitted_surfaces"] = [omitted["surface"]]
    for spec in specs:
        spec.setdefault("omitted_surfaces", [])
        spec["planned_terms"] = [term["surface"] for term in spec["terms"]]
        spec["glossary"] = _make_row_glossary(
            spec["terms"], set(spec["omitted_surfaces"]), glossary_by_surface, confusables, max_confusables
        )
    return specs


def make_novel_specs(
    novel_terms: list[dict[str, Any]],
    glossary_by_surface: dict[str, dict[str, Any]],
    confusables: dict[str, list[dict[str, Any]]],
    *,
    count: int = DEFAULT_NOVEL_COUNT,
    max_confusables: int = MAX_CONFUSABLES_PER_TERM,
    seed: int = SEED,
) -> list[dict[str, Any]]:
    """held-out新語を重複なく選び、初見語評価の条件を作る。"""
    if not 1 <= count <= len(novel_terms):
        raise ValueError(f"novel countは1〜{len(novel_terms)}の範囲が必要です")
    rng = random.Random(f"{seed}-test-novel")
    by_category = {category: [row for row in novel_terms if row["category"] == category] for category in CATEGORIES}
    for rows in by_category.values():
        rng.shuffle(rows)
    ordered: list[dict[str, Any]] = []
    while len(ordered) < count:
        progressed = False
        for category in CATEGORIES:
            if by_category[category] and len(ordered) < count:
                ordered.append(by_category[category].pop())
                progressed = True
        if not progressed:
            break
    specs = []
    for index, row in enumerate(ordered, start=1):
        term = {"surface": row["surface"], "reading": rng.choice(row["readings"]), "category": row["category"]}
        spec = _make_condition(rng, f"novel-{index:06d}", "test", [term])
        spec["planned_terms"] = [term["surface"]]
        spec["omitted_surfaces"] = []
        spec["novel_terms"] = [term["surface"]]
        spec["glossary"] = _make_row_glossary(
            [term], set(), glossary_by_surface, confusables, max_confusables
        )
        specs.append(spec)
    return specs


def _system_with_excluded_terms(excluded_terms: list[dict[str, Any]]) -> str:
    """除外表記をプロンプトへ示し、文中では読みのカタカナを使うよう指示する。"""
    if not excluded_terms:
        return SYSTEM_V3
    lines = [
        SYSTEM_V3,
        "## 用語集から除外した語",
        "次の語は用語として扱いません。話された場合は、対応する読みをカタカナで書き、英字表記や英字の印を使わないでください。",
    ]
    for term in excluded_terms:
        readings = "、".join(term.get("readings", []))
        lines.append(f"- {term['surface']}" + (f"（読み: {readings}）" if readings else ""))
    return "\n".join(lines)


def make_requests(
    specs: list[dict[str, Any]],
    batch_size: int,
    split: str,
    request_prefix: str | None = None,
    seed_offset: int = 0,
    excluded_terms: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """仕様を第1版と同じJSON応答形式の教師要求へまとめる。"""
    if batch_size < 1:
        raise ValueError("batch_sizeは1以上が必要です")
    system_prompt = _system_with_excluded_terms(excluded_terms or [])
    requests: list[dict[str, Any]] = []
    for offset in range(0, len(specs), batch_size):
        chunk = specs[offset : offset + batch_size]
        prefix = request_prefix or split
        request_id = f"req-{prefix}-{offset // batch_size:06d}"
        for item_index, spec in enumerate(chunk, start=1):
            spec["request_id"] = request_id
            spec["request_index"] = item_index
        user = USER_HEADER.format(n=len(chunk)) + "\n".join(
            _render_v3_item(index, spec) for index, spec in enumerate(chunk, start=1)
        )
        requests.append(
            {
                "id": request_id,
                "spec_ids": [spec["spec_id"] for spec in chunk],
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}],
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                "max_tokens": DEFAULT_MAX_TOKENS,
                "seed": SEED + seed_offset + offset + (2 * 10**7 if split == "test-novel" else 0),
            }
        )
    return requests


def _load_outputs(path: Path) -> dict[str, dict[str, Any]]:
    """教師出力を要求idでまとめる。再開実行で重複した場合は最後の行を使う。"""
    return {row["id"]: row for row in read_jsonl(path) if isinstance(row.get("id"), str)}


def _validation_glossary(full: Glossary, omitted_surfaces: Iterable[str]) -> Glossary:
    """辞書抜け行の読みだけを許容し、ほかの第1版検査規則は維持する。"""
    replacements = {
        surface: {**full.terms[surface], "style": "either"}
        for surface in omitted_surfaces
        if surface in full.terms
    }
    if not replacements:
        return full
    return Glossary(
        ChainMap(replacements, full.terms),
        full.reading_owner,
        full.reading_re,
        full.held_out_surface_re,
        full.surface_re,
    )


def _convert_one(spec: dict[str, Any], item: dict[str, Any], full_glossary: Glossary) -> dict[str, Any]:
    """教師の1件を第1版検査へ通し、正解と話し言葉をデータ行へ変換する。"""
    omitted = set(spec.get("omitted_surfaces", []))
    convert_spec = dict(spec)
    convert_spec["terms"] = [
        {"surface": term["surface"], "reading": term["reading"]}
        for term in spec["terms"]
        if term["surface"] not in omitted
    ]
    convert_spec["split"] = "test" if spec["split"] == "test" else "train"
    validation_glossary = _validation_glossary(full_glossary, omitted)
    return convert(
        convert_spec,
        item.get("spoken"),
        item.get("target"),
        validation_glossary,
        item.get("dropped", ""),
    )


def _excluded_surface_patterns(excluded_surfaces: set[str] | None) -> list[re.Pattern[str]]:
    """除外表記を、文中で英字使用を検出する正規表現に変換する。"""
    surfaces = sorted(excluded_surfaces or set(), key=len, reverse=True)
    if not surfaces:
        return []
    alternatives = "|".join(re.escape(surface) for surface in surfaces)
    return [re.compile(r"(?<![A-Za-z0-9])(?:" + alternatives + r")(?![A-Za-z0-9])", re.IGNORECASE)]


def _contains_excluded_surface(text: str, patterns: list[re.Pattern[str]]) -> bool:
    """除外語の英字表記が、前後を英数字に挟まれず現れるかを返す。"""
    return any(pattern.search(text) is not None for pattern in patterns)


def _build_rows(
    specs: list[dict[str, Any]],
    outputs: dict[str, dict[str, Any]],
    full_glossary: Glossary,
    kind: str,
    excluded_surfaces: set[str] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """教師出力を検査し、重複のない学習または初見語評価行を返す。"""
    accepted: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    excluded_patterns = _excluded_surface_patterns(excluded_surfaces)
    parsed_items_by_request: dict[str, dict[int, dict[str, Any]]] = {}
    for spec in specs:
        request_id = spec.get("request_id")
        output = outputs.get(request_id)
        if output is None:
            rejects["output_missing"] += 1
            continue
        if request_id not in parsed_items_by_request:
            parsed_items_by_request[request_id] = {
                item["i"]: item
                for item in parse_items(output.get("text", ""))
                if isinstance(item.get("i"), int)
            }
        item = parsed_items_by_request[request_id].get(spec.get("request_index"))
        if item is None or "spoken" not in item or "target" not in item:
            rejects["item_missing_or_unparsable"] += 1
            continue
        raw_text = "\n".join(str(item.get(field, "")) for field in ("spoken", "target", "dropped"))
        if _contains_excluded_surface(raw_text, excluded_patterns):
            rejects["excluded_surface_written_in_latin"] += 1
            continue
        try:
            record = _convert_one(spec, item, full_glossary)
        except Reject as error:
            rejects[str(error)] += 1
            continue
        row = {
            "split": "train" if kind == "train" else "test-novel",
            "spoken_text": record["spoken_text"],
            "spoken_text_kana": record["spoken_text_kana"],
            "spoken_text_mixed": record["spoken_text_mixed"],
            "target_text": record["target_text"],
            "terms": record["terms"],
            "glossary": spec["glossary"],
            "source": "synthetic-tts",
            "domain": spec["domain"],
            "fillers": record["fillers"],
            "tags": record["tags"],
            "usecase": spec["usecase"],
            "spoken_marked": record["spoken_marked"],
            "est_seconds": record["est_seconds"],
            "gen_id": spec["spec_id"],
        }
        if kind == "train":
            # 学習時に行ごとの用語集を再選択せず、生成条件と同じ内容を渡す。
            row["glossary_fixed"] = True
            row["planned_terms"] = list(spec["planned_terms"])
            row["omitted_terms"] = [
                {"surface": term["surface"], "readings": [term["reading"]]}
                for term in spec["terms"]
                if term["surface"] in set(spec.get("omitted_surfaces", []))
            ]
        else:
            row["novel_terms"] = list(spec["novel_terms"])
        accepted.append(row)

    # 文章と読み上げ文の重複は第1版と同じく取り除く。
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in accepted:
        keys = {row["target_text"], row["spoken_text_kana"]}
        if keys & seen:
            rejects["duplicate"] += 1
            continue
        seen.update(keys)
        unique.append(row)
    return unique, rejects


def _training_row_errors(
    row: dict[str, Any],
    glossary_by_surface: dict[str, dict[str, Any]],
    train_glossary_terms: set[str],
    train_terms: set[str],
    full_glossary: Glossary | None,
    excluded_patterns: list[re.Pattern[str]],
    surface_patterns: dict[str, re.Pattern[str]],
) -> Counter[str]:
    """train行1件に第1版由来の保持条件と用語条件を適用する。"""
    errors: Counter[str] = Counter()
    text = "\n".join((row["spoken_text_mixed"], row["target_text"]))
    if full_glossary and full_glossary.held_out_surface_re.search(text):
        errors["held_out_surface_leak"] += 1
    if _contains_excluded_surface(text, excluded_patterns):
        errors["excluded_surface_written_in_latin"] += 1
    row_glossary = {entry["surface"] for entry in row["glossary"]}
    if any(surface not in train_glossary_terms for surface in row_glossary):
        errors["non_train_glossary_entry"] += 1
    for surface in row.get("planned_terms", []):
        if surface not in train_terms:
            errors["non_train_planned_term"] += 1
    for surface in row["terms"]:
        if surface not in train_terms or surface not in row_glossary:
            errors["invalid_gold_term"] += 1
        pattern = surface_patterns.get(surface)
        if pattern is None:
            pattern = surface_pattern(surface)
            surface_patterns[surface] = pattern
        if surface not in glossary_by_surface or not pattern.search(row["target_text"]):
            errors["gold_term_not_in_target"] += 1
    for omitted in row.get("omitted_terms", []):
        surface = omitted["surface"]
        pattern = surface_patterns.get(surface)
        if pattern is None:
            pattern = surface_pattern(surface)
            surface_patterns[surface] = pattern
        if surface in row_glossary or surface in row["terms"] or pattern.search(row["target_text"]):
            errors["omitted_term_leak"] += 1
        if not any(reading in row["spoken_text_kana"] for reading in omitted["readings"]):
            errors["omitted_term_missing_from_spoken"] += 1
        if not any(reading in row["target_text"] for reading in omitted["readings"]):
            errors["omitted_term_not_preserved_in_target"] += 1
    if full_glossary:
        for match in full_glossary.reading_re.finditer(row["spoken_text_kana"]):
            owner = full_glossary.reading_owner[match.group()]
            if full_glossary.terms[owner]["split"] == "held-out":
                errors["held_out_reading_leak"] += 1
                break
    return errors


def _filter_invalid_training_rows(
    rows: list[dict[str, Any]],
    glossary_rows: list[dict[str, Any]],
    full_glossary: Glossary,
    required_train_surfaces: set[str],
    excluded_surfaces: set[str],
) -> tuple[list[dict[str, Any]], Counter[str], int]:
    """第1版由来の行単位検査に落ちた文を除き、理由別の件数を返す。"""
    glossary_by_surface = {row["surface"]: row for row in glossary_rows}
    train_glossary_terms = {
        row["surface"] for row in glossary_rows if row["split"] == "train" and row["surface"] not in excluded_surfaces
    }
    excluded_patterns = _excluded_surface_patterns(excluded_surfaces)
    surface_patterns: dict[str, re.Pattern[str]] = {}
    accepted: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    for row in rows:
        errors = _training_row_errors(
            row,
            glossary_by_surface,
            train_glossary_terms,
            required_train_surfaces,
            full_glossary,
            excluded_patterns,
            surface_patterns,
        )
        if errors:
            rejects.update(dict.fromkeys(errors, 1))
        else:
            accepted.append(row)
    return accepted, rejects, len(rows) - len(accepted)


def validate_training_rows(
    rows: list[dict[str, Any]],
    glossary_rows: list[dict[str, Any]],
    minimum_repeats: int,
    full_glossary: Glossary | None = None,
    required_train_surfaces: set[str] | None = None,
    excluded_surfaces: set[str] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """train行のheld-out漏れ、正解語、辞書抜け、各語の出現数を再検査する。"""
    by_surface = {row["surface"]: row for row in glossary_rows}
    excluded = excluded_surfaces or set()
    train_glossary_terms = {
        row["surface"] for row in glossary_rows if row["split"] == "train" and row["surface"] not in excluded
    }
    train_terms = required_train_surfaces if required_train_surfaces is not None else train_glossary_terms
    counts: Counter[str] = Counter(surface for row in rows for surface in row["terms"])
    errors: Counter[str] = Counter()
    excluded_patterns = _excluded_surface_patterns(excluded)
    surface_patterns: dict[str, re.Pattern[str]] = {}
    for row in rows:
        errors.update(
            _training_row_errors(
                row,
                by_surface,
                train_glossary_terms,
                train_terms,
                full_glossary,
                excluded_patterns,
                surface_patterns,
            )
        )
    missing = [surface for surface in sorted(train_terms) if counts[surface] < minimum_repeats]
    if missing:
        errors["terms_below_minimum"] = len(missing)
    return missing, errors


def validate_novel_rows(
    rows: list[dict[str, Any]],
    novel_surfaces: set[str],
    glossary_by_surface: dict[str, dict[str, Any]],
    max_train_ratio: float = DEFAULT_MAX_NOVEL_TRAIN_RATIO,
    excluded_surfaces: set[str] | None = None,
) -> Counter[str]:
    """test-novelのheld-out新語、train語比率、novel_termsとの対応を検査する。"""
    errors: Counter[str] = Counter()
    total_terms = 0
    train_terms = 0
    seen_novel: set[str] = set()
    excluded_patterns = _excluded_surface_patterns(excluded_surfaces)
    for row in rows:
        text = "\n".join((row["spoken_text_mixed"], row["target_text"]))
        if _contains_excluded_surface(text, excluded_patterns):
            errors["excluded_surface_written_in_latin"] += 1
        if not row.get("novel_terms"):
            errors["novel_terms_missing"] += 1
        row_glossary = {entry["surface"] for entry in row["glossary"]}
        for surface in row["novel_terms"]:
            if surface not in novel_surfaces or surface not in row["terms"]:
                errors["not_a_new_heldout_gold_term"] += 1
            if surface in seen_novel:
                errors["novel_term_reused"] += 1
            seen_novel.add(surface)
            if surface not in row_glossary:
                errors["novel_term_missing_from_glossary"] += 1
        for surface in row["terms"]:
            total_terms += 1
            entry = glossary_by_surface.get(surface)
            train_terms += entry is not None and entry["split"] == "train"
        if set(row["terms"]) != set(row["novel_terms"]):
            errors["non_novel_gold_term"] += 1
        if any(surface not in novel_surfaces for surface in row["novel_terms"]):
            errors["v1_or_train_focus_term"] += 1
    ratio = train_terms / total_terms if total_terms else 0.0
    if ratio > max_train_ratio:
        errors["train_term_ratio_over_limit"] += 1
    return errors


def _filter_invalid_novel_rows(
    rows: list[dict[str, Any]],
    novel_surfaces: set[str],
    glossary_by_surface: dict[str, dict[str, Any]],
    max_train_ratio: float,
    excluded_surfaces: set[str],
) -> tuple[list[dict[str, Any]], Counter[str], int]:
    """初見語の条件を満たさない文と、初見語を再利用した文を除く。"""
    accepted: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    seen_novel: set[str] = set()
    for row in rows:
        errors = validate_novel_rows(
            [row], novel_surfaces, glossary_by_surface, max_train_ratio, excluded_surfaces
        )
        repeated = set(row.get("novel_terms", [])) & seen_novel
        if repeated:
            errors["novel_term_reused"] += len(repeated)
        if errors:
            rejects.update(dict.fromkeys(errors, 1))
        else:
            accepted.append(row)
            seen_novel.update(row.get("novel_terms", []))
    return accepted, rejects, len(rows) - len(accepted)


def _write_json(path: Path, value: Any) -> None:
    """診断用のJSONをUTF-8で保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_content_characters(requests: list[dict[str, Any]]) -> int:
    """教師要求のmessage本文文字数を合計する。token数そのものではない。"""
    return sum(len(message["content"]) for request in requests for message in request["messages"])


def _next_topup_prefix(work: Path) -> str:
    """top-upのファイル名に使う、未使用の連番を返す。"""
    used = [int(path.stem.rsplit("-", 1)[1]) for path in work.glob("specs-train-topup-*.jsonl")]
    return f"train-topup-{max(used, default=0) + 1:03d}"


def plan(
    glossary_path: Path,
    confusables_path: Path,
    legacy_path: Path,
    work: Path,
    minimum_repeats: int,
    overgeneration: float,
    novel_count: int,
    batch_size: int,
    max_confusables: int,
    top_up_from: Path | None = None,
    excluded_path: Path | None = None,
) -> None:
    """trainと初見語評価の教師要求を作業ディレクトリへ書き出す。"""
    glossary_rows = load_glossary(glossary_path)
    legacy_rows = load_glossary(legacy_path)
    by_surface = {row["surface"]: row for row in glossary_rows}
    legacy_surfaces = {row["surface"] for row in legacy_rows}
    legacy_train_surfaces = {row["surface"] for row in legacy_rows if row["split"] == "train"}
    excluded_surfaces = load_excluded_terms(excluded_path)
    conf_map, stale_confusable_references = load_confusables(confusables_path, by_surface)
    excluded_confusable_references = sum(
        candidate["surface"] in excluded_surfaces for candidates in conf_map.values() for candidate in candidates
    )
    conf_map = {
        surface: [candidate for candidate in candidates if candidate["surface"] not in excluded_surfaces]
        for surface, candidates in conf_map.items()
    }
    train_terms = eligible_training_terms(glossary_rows, legacy_rows, excluded_surfaces)
    new_terms = eligible_novel_terms(glossary_rows, legacy_rows, excluded_surfaces)
    train_terms_with_confusables = {
        row["surface"]
        for row in train_terms
        if any(candidate["split"] == "train" for candidate in conf_map.get(row["surface"], []))
    }
    terms_without_confusable_rows = {row["surface"] for row in train_terms} - set(conf_map)
    excluded_prompt_terms = [
        {"surface": surface, "readings": by_surface.get(surface, {}).get("readings", [])}
        for surface in sorted(excluded_surfaces)
    ]
    work.mkdir(parents=True, exist_ok=True)
    if not top_up_from and not 300 <= novel_count <= 500:
        raise ValueError("novel-countは完成データの指定として300〜500が必要です")

    if top_up_from:
        coverage = {row["surface"]: int(row["accepted"]) for row in read_jsonl(top_up_from)}
        deficits = {
            row["surface"]: max(0, minimum_repeats - coverage.get(row["surface"], 0))
            for row in train_terms
        }
        needed = {surface: max(count, math.ceil(count * overgeneration)) for surface, count in deficits.items() if count}
        selected_terms = [by_surface[surface] for surface in needed]
        if not selected_terms:
            raise ValueError("top-up対象の不足語がありません")
        # 各語の不足数が違う場合は、個別のslot listから同じグルーピング処理を使う。
        topup_slots = [by_surface[surface] for surface, count in needed.items() for _ in range(count)]
        rng = random.Random(f"{SEED}-topup-{top_up_from}")
        groups = _pack_term_slots_from_slots(topup_slots, rng)
        prefix = _next_topup_prefix(work)
        specs = _specs_from_groups(groups, by_surface, conf_map, max_confusables, DEFAULT_GLOSSARY_DROP_RATIO, rng, prefix)
        train_spec_path = work / f"specs-{prefix}.jsonl"
        train_request_path = work / f"requests-{prefix}.jsonl"
        novel_specs = []
        novel_spec_path = None
        novel_request_path = None
    else:
        prefix = "train-000"
        specs = make_training_specs(
            train_terms,
            by_surface,
            conf_map,
            minimum_repeats=minimum_repeats,
            overgeneration=overgeneration,
            max_confusables=max_confusables,
            id_prefix=prefix,
        )
        train_spec_path = work / "specs-train.jsonl"
        train_request_path = work / "requests-train.jsonl"
        # 完成件数に余裕を持たせ、build時に有効な行から指定件数だけ選ぶ。
        novel_plan_count = min(len(new_terms), max(novel_count, math.ceil(novel_count * overgeneration)))
        novel_specs = make_novel_specs(new_terms, by_surface, conf_map, count=novel_plan_count, max_confusables=max_confusables)
        novel_spec_path = work / "specs-test-novel.jsonl"
        novel_request_path = work / "requests-test-novel.jsonl"
    paths = [train_spec_path, train_request_path]
    if novel_spec_path is not None and novel_request_path is not None:
        paths.extend((novel_spec_path, novel_request_path))
    for path in paths:
        if path.exists():
            raise FileExistsError(f"既存ファイルを上書きしません: {path}")
    request_prefix = prefix if top_up_from else "train"
    seed_offset = int(prefix.rsplit("-", 1)[1]) * 10**6 if top_up_from else 0
    train_requests = make_requests(
        specs,
        batch_size,
        "train",
        request_prefix=request_prefix,
        seed_offset=seed_offset,
        excluded_terms=excluded_prompt_terms,
    )
    novel_requests = (
        make_requests(novel_specs, batch_size, "test-novel", excluded_terms=excluded_prompt_terms)
        if novel_specs
        else []
    )
    write_jsonl(train_spec_path, specs)
    write_jsonl(train_request_path, train_requests)
    if novel_spec_path is not None and novel_request_path is not None:
        write_jsonl(novel_spec_path, novel_specs)
        write_jsonl(novel_request_path, novel_requests)
    _write_json(
        work / f"plan-summary-{prefix}.json",
        {
            "minimum_repeats": minimum_repeats,
            "overgeneration": overgeneration,
            "planned_train_specs": len(specs),
            "train_requests": len(train_requests),
            "train_prompt_characters": _request_content_characters(train_requests),
            "train_terms": len(train_terms),
            "topup_terms": len(selected_terms) if top_up_from else 0,
            "legacy_train_terms": sum(row["surface"] in legacy_train_surfaces for row in train_terms),
            "new_fame_1_2_train_terms": sum(row["surface"] not in legacy_surfaces for row in train_terms),
            "excluded_terms": len(excluded_surfaces),
            "excluded_confusable_references": excluded_confusable_references,
            "requested_novel_count": novel_count if novel_specs else 0,
            "planned_novel_specs": len(novel_specs),
            "novel_requests": len(novel_requests),
            "novel_prompt_characters": _request_content_characters(novel_requests),
            "eligible_new_heldout_terms": len(new_terms),
            "confusable_references_missing_from_glossary": stale_confusable_references,
            "glossary_terms_without_confusable_rows": len(terms_without_confusable_rows),
            "train_terms_with_train_confusables": len(train_terms_with_confusables),
            "train_terms_without_train_confusables": len(train_terms) - len(train_terms_with_confusables),
            "glossary_drop_ratio_requested": DEFAULT_GLOSSARY_DROP_RATIO,
        },
    )
    print(f"train: {len(specs)} specs / {len(train_requests)} requests; novel: {len(novel_specs)} specs / {len(novel_requests)} requests")
    topup_count = len(selected_terms) if top_up_from else 0
    print(
        f"eligible train terms={len(train_terms)}, top-up targets={topup_count}, "
        f"eligible new held-out candidates={len(new_terms)}, excluded terms={len(excluded_surfaces)}, work={work}"
    )
    if stale_confusable_references:
        print(f"WARNING: ignored {stale_confusable_references} confusable references absent from glossary-v2")
    if terms_without_confusable_rows:
        print(f"WARNING: {len(terms_without_confusable_rows)} glossary terms have no confusables row")
    if train_terms_with_confusables:
        print(
            f"train terms with valid train confusables={len(train_terms_with_confusables)}/"
            f"{len(train_terms)}"
        )


def _pack_term_slots_from_slots(slots: list[dict[str, Any]], rng: random.Random) -> list[list[dict[str, Any]]]:
    """top-upの不足回数が語ごとに違うslotを重複なく文へまとめる。"""
    remaining = list(slots)
    rng.shuffle(remaining)
    groups: list[list[dict[str, Any]]] = []
    while remaining:
        requested = int(pick(rng, N_TERMS_WEIGHTS))
        group: list[dict[str, Any]] = []
        used: set[str] = set()
        index = 0
        while index < len(remaining) and len(group) < requested:
            item = remaining[index]
            if item["surface"] in used:
                index += 1
                continue
            group.append(item)
            used.add(item["surface"])
            remaining.pop(index)
        groups.append(group)
    return groups


def _specs_from_groups(
    groups: list[list[dict[str, Any]]],
    glossary_by_surface: dict[str, dict[str, Any]],
    confusables: dict[str, list[dict[str, Any]]],
    max_confusables: int,
    drop_ratio: float,
    rng: random.Random,
    id_prefix: str,
) -> list[dict[str, Any]]:
    """top-up slotを条件、辞書抜け、用語集つきの仕様へ変換する。"""
    specs = []
    for index, group in enumerate(groups, start=1):
        assigned = [
            {"surface": row["surface"], "reading": rng.choice(row["readings"]), "category": row["category"]}
            for row in group
        ]
        specs.append(_make_condition(rng, f"{id_prefix}-{index:06d}", "train", assigned))
    count = min(len(specs), round(len(specs) * drop_ratio))
    for spec in rng.sample(specs, count):
        spec["omitted_surfaces"] = [rng.choice(spec["terms"])["surface"]]
    for spec in specs:
        spec.setdefault("omitted_surfaces", [])
        spec["planned_terms"] = [term["surface"] for term in spec["terms"]]
        spec["glossary"] = _make_row_glossary(
            spec["terms"], set(spec["omitted_surfaces"]), glossary_by_surface, confusables, max_confusables
        )
    return specs


def build(
    work: Path,
    glossary_path: Path,
    legacy_path: Path,
    train_outputs_path: Path,
    novel_outputs_path: Path,
    out_dir: Path,
    minimum_repeats: int,
    novel_train_ratio_limit: float,
    excluded_path: Path | None = None,
    novel_count: int = DEFAULT_NOVEL_COUNT,
) -> None:
    """出力を検査し、完全な場合だけtrain.jsonlとtest-novel.jsonlを完成名で保存する。"""
    glossary_rows = load_glossary(glossary_path)
    legacy_rows = load_glossary(legacy_path)
    by_surface = {row["surface"]: row for row in glossary_rows}
    excluded_surfaces = load_excluded_terms(excluded_path)
    required_train_rows = eligible_training_terms(glossary_rows, legacy_rows, excluded_surfaces)
    required_train_surfaces = {row["surface"] for row in required_train_rows}
    novel_surfaces = {
        row["surface"] for row in eligible_novel_terms(glossary_rows, legacy_rows, excluded_surfaces)
    }
    if not 300 <= novel_count <= 500:
        raise ValueError("novel-countは完成データの指定として300〜500が必要です")
    full_glossary = Glossary.from_rows(glossary_rows)
    train_specs = [row for path in sorted(work.glob("specs-train*.jsonl")) for row in read_jsonl(path)]
    novel_specs = list(read_jsonl(work / "specs-test-novel.jsonl"))
    train_candidates, train_rejects = _build_rows(
        train_specs, _load_outputs(train_outputs_path), full_glossary, "train", excluded_surfaces
    )
    train_rows, train_validation_rejects, train_validation_rejected = _filter_invalid_training_rows(
        train_candidates,
        glossary_rows,
        full_glossary,
        required_train_surfaces,
        excluded_surfaces,
    )
    novel_candidates, novel_rejects = _build_rows(
        novel_specs, _load_outputs(novel_outputs_path), full_glossary, "novel", excluded_surfaces
    )
    novel_valid_rows, novel_validation_rejects, novel_validation_rejected = _filter_invalid_novel_rows(
        novel_candidates,
        novel_surfaces,
        by_surface,
        novel_train_ratio_limit,
        excluded_surfaces,
    )
    novel_rows = novel_valid_rows[:novel_count]
    novel_errors = validate_novel_rows(
        novel_rows, novel_surfaces, by_surface, novel_train_ratio_limit, excluded_surfaces
    )
    missing, train_errors = validate_training_rows(
        train_rows,
        glossary_rows,
        minimum_repeats,
        full_glossary,
        required_train_surfaces,
        excluded_surfaces,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    gold_counts: Counter[str] = Counter(surface for row in train_rows for surface in row["terms"])
    spoken_counts: Counter[str] = Counter(surface for row in train_rows for surface in row.get("planned_terms", []))
    coverage = [
        {
            "surface": surface,
            "accepted": gold_counts[surface],
            "spoken_assignments": spoken_counts[surface],
            "required": minimum_repeats,
        }
        for surface in sorted(required_train_surfaces)
    ]
    coverage_path = work / "coverage-train.jsonl"
    write_jsonl(coverage_path, coverage)
    _write_json(
        work / "build-report.json",
        {
            "train_specs": len(train_specs),
            "train_candidates": len(train_candidates),
            "train_accepted": len(train_rows),
            "train_rejects": dict(train_rejects),
            "train_validation_rejected": train_validation_rejected,
            "train_validation_rejects": dict(train_validation_rejects),
            "train_errors": dict(train_errors),
            "required_train_terms": len(required_train_surfaces),
            "train_terms_below_minimum": len(missing),
            "novel_specs": len(novel_specs),
            "novel_candidates": len(novel_candidates),
            "novel_valid_candidates": len(novel_valid_rows),
            "novel_validation_rejected": novel_validation_rejected,
            "novel_validation_rejects": dict(novel_validation_rejects),
            "novel_accepted": len(novel_rows),
            "novel_target_count": novel_count,
            "novel_valid_candidates_not_selected": max(0, len(novel_valid_rows) - len(novel_rows)),
            "novel_rejects": dict(novel_rejects),
            "novel_errors": dict(novel_errors),
            "excluded_terms": len(excluded_surfaces),
            "coverage_path": str(coverage_path),
        },
    )
    train_complete = not missing and not train_errors
    novel_complete = len(novel_rows) == novel_count and not novel_errors
    final_train = out_dir / "train.jsonl"
    partial_train = out_dir / "train.partial.jsonl"
    final_novel = out_dir / "test-novel.jsonl"
    partial_novel = out_dir / "test-novel.partial.jsonl"
    existing = [path for path in (final_train, partial_train, final_novel, partial_novel) if path.exists()]
    if existing:
        raise FileExistsError(f"出力先に既存ファイルがあります: {existing[0]}")
    if train_complete:
        write_jsonl(final_train, [dict(row, id=f"train-v3-{index:06d}") for index, row in enumerate(train_rows, 1)])
    else:
        write_jsonl(partial_train, [dict(row, id=f"train-v3-{index:06d}") for index, row in enumerate(train_rows, 1)])
    if novel_complete:
        write_jsonl(final_novel, [dict(row, id=f"novel-{index:06d}") for index, row in enumerate(novel_rows, 1)])
    else:
        write_jsonl(partial_novel, [dict(row, id=f"novel-{index:06d}") for index, row in enumerate(novel_rows, 1)])
    print(
        f"train accepted={len(train_rows)}/{len(train_specs)} after validation "
        f"(candidates={len(train_candidates)}, validation-rejected={train_validation_rejected}), "
        f"missing terms={len(missing)}, errors={dict(train_errors)}"
    )
    print(
        f"test-novel accepted={len(novel_rows)}/{len(novel_specs)} "
        f"(semantic-valid={len(novel_valid_rows)}, validation-rejected={novel_validation_rejected}), "
        f"errors={dict(novel_errors)}"
    )
    if missing:
        print(f"coverage report for top-up: {coverage_path}")
    if not train_complete or not novel_complete:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """計画作成と教師出力の検査に使うCLIを組み立てる。"""
    parser = argparse.ArgumentParser(description="用語集v2から学習文と初見語評価文を作る")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="教師LLMへの要求を作る")
    plan_parser.add_argument("--glossary-v2", type=Path, required=True)
    plan_parser.add_argument("--confusables", type=Path, required=True)
    plan_parser.add_argument("--legacy-glossary", type=Path, required=True)
    plan_parser.add_argument("--excluded-terms", type=Path, required=True)
    plan_parser.add_argument("--work", type=Path, required=True)
    plan_parser.add_argument("--minimum-repeats", type=int, default=5)
    plan_parser.add_argument("--overgeneration", type=float, default=DEFAULT_OVERGENERATION)
    plan_parser.add_argument("--novel-count", type=int, default=DEFAULT_NOVEL_COUNT)
    plan_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    plan_parser.add_argument("--max-confusables", type=int, default=MAX_CONFUSABLES_PER_TERM)
    plan_parser.add_argument("--top-up-from", type=Path, help="coverage-train.jsonl。不足した語だけ追加計画を作る")
    build_parser = subparsers.add_parser("build", help="教師出力を検査して最終JSONLを書き出す")
    build_parser.add_argument("--glossary-v2", type=Path, required=True)
    build_parser.add_argument("--legacy-glossary", type=Path, required=True)
    build_parser.add_argument("--excluded-terms", type=Path, required=True)
    build_parser.add_argument("--work", type=Path, required=True)
    build_parser.add_argument("--train-outputs", type=Path, required=True)
    build_parser.add_argument("--novel-outputs", type=Path, required=True)
    build_parser.add_argument("--out-dir", type=Path, required=True)
    build_parser.add_argument("--minimum-repeats", type=int, default=5)
    build_parser.add_argument("--max-novel-train-ratio", type=float, default=DEFAULT_MAX_NOVEL_TRAIN_RATIO)
    build_parser.add_argument("--novel-count", type=int, default=DEFAULT_NOVEL_COUNT)
    return parser


def main() -> None:
    """CLI引数に応じて計画またはビルドを実行する。"""
    args = build_parser().parse_args()
    if args.command == "plan":
        plan(
            args.glossary_v2,
            args.confusables,
            args.legacy_glossary,
            args.work,
            args.minimum_repeats,
            args.overgeneration,
            args.novel_count,
            args.batch_size,
            args.max_confusables,
            args.top_up_from,
            args.excluded_terms,
        )
    else:
        build(
            args.work,
            args.glossary_v2,
            args.legacy_glossary,
            args.train_outputs,
            args.novel_outputs,
            args.out_dir,
            args.minimum_repeats,
            args.max_novel_train_ratio,
            args.excluded_terms,
            args.novel_count,
        )


if __name__ == "__main__":
    main()
