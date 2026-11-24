"""条件Dの学習元から用語だけを差し替え、監査済みの拡張JSONLを作る。"""

import argparse
import hashlib
import json
import multiprocessing
import random
import re
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from itertools import islice
from pathlib import Path

from rapidfuzz import fuzz, process

from analyze_baselines import term_kind
from asr_noise import (
    HAAS_NOHINT, HAAS_TWOPASS, MARK_PATTERN, plan_two_pass_error_overrides, simulate_asr_noise, to_user_punctuation,
)
from voiceime.formatter.glossary import GlossaryIndex, entry_from_record, load_glossary, load_term_list
from voiceime.formatter.prompt import FormatterInput, formatter_input_text

LIMIT = 57_000
MAX_ENTRIES = 20
MAX_PER_TERM = 3
SOURCE_WORKERS = 8
SOURCE_NAMES = ("first_pass", "combined_text", "qwen_hypothesis")
SPACED_ASR_RUN = re.compile(r"[a-z0-9_]+(?: [a-z0-9_]+)+")
DAKUTEN_FAMILIES = ("カガキギクグケゲコゴ", "サザシジスズセゼソゾ", "タダチヂツヅテデトド", "ハバパヒビピフブプヘベペホボポ", "ウヴ")
DAKUTEN = {}
for family in DAKUTEN_FAMILIES:
    width = 3 if family.startswith("ハ") else 2
    for i in range(0, len(family), width):
        group = family[i:i + width]
        DAKUTEN.update({char: group.replace(char, "") for char in group})


def lines(path):
    """読み取り元のJSONLを順番にたどる。"""
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def compact(obj):
    """日本語の表記を保ってJSONLの1行にする。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def source_hash(path):
    """元データを記録するため、ファイル全体のSHA-256を求める。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def source_index(path, key):
    """行別の補助入力を一意のidで引けるようにする。"""
    result = {}
    for row in lines(path):
        if row["id"] in result:
            raise ValueError(f"{path}: idの重複 {row['id']}")
        result[row["id"]] = row[key]
    return result


class SurfaceIndex:
    """文字列に含まれる用語を、先頭3文字までの索引を使って列挙する。"""

    def __init__(self, surfaces):
        self.prefixes = defaultdict(list)
        for surface in surfaces:
            if surface:
                self.prefixes[surface[:3]].append(surface)

    def matches(self, text, *, word_boundaries=False):
        """元の表記との部分一致を列挙する。漏えい検査では英字語の境界を要求する。"""
        for _, _, surface in self.occurrences(text, word_boundaries=word_boundaries):
            yield surface

    def occurrences(self, text, *, word_boundaries=False):
        """一致箇所の位置を返し、元の空白の境界を後から調べられるようにする。"""
        for i in range(len(text)):
            for width in range(1, min(3, len(text) - i) + 1):
                for surface in self.prefixes.get(text[i:i + width], ()):
                    end = i + len(surface)
                    if (word_boundaries and
                        ((i and ascii_word(surface[0]) and ascii_word(text[i - 1])) or
                         (end < len(text) and ascii_word(surface[-1]) and ascii_word(text[end])))):
                        continue
                    if text.startswith(surface, i):
                        yield i, end, surface


def ascii_word(char):
    """英字識別子の内部と、独立した短い用語を区別する。"""
    return char.isascii() and (char.isalnum() or char == "_")


def canonical(text):
    """漏えい検査で幅・大小・空白の表記差を揃える。"""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def blocked_index(terms):
    """Qwenで起きる空白除去も検出対象に加える。"""
    forms = {canonical(term) for term in terms}
    return SurfaceIndex(forms | {form.replace(" ", "") for form in forms})


@lru_cache(maxsize=131_072)
def has_blocked(text, index):
    """禁止語が独立した表記として含まれるか確かめる。"""
    return next(index.matches(canonical(text), word_boundaries=True), None) is not None


def has_spaced_asr_term(text, index):
    """Qwenが字間を空けた語も、空白前後の実際の語境界を使って漏えい検査する。"""
    for match in SPACED_ASR_RUN.finditer(canonical(text)):
        raw = match[0]
        offsets = [i for i, char in enumerate(raw) if char != " "]
        compact_run = "".join(raw[i] for i in offsets)
        for start, end, _ in index.occurrences(compact_run):
            left = offsets[start]
            right = offsets[end - 1] + 1
            if (left == 0 or raw[left - 1] == " ") and (right == len(raw) or raw[right] == " "):
                return True
    return False


def entry_record(entry):
    """用語一覧に表示される表記と読みだけを保持する。"""
    return {"surface": entry.surface, "readings": list(entry.readings)}


def noise(reading, rng):
    """30%で、可能な種類から一つだけ読みの軽い変形を選ぶ。"""
    if rng.random() >= 0.3:
        return reading, "none"
    candidates = {
        "long_vowel": [(i, "") for i, char in enumerate(reading) if char == "ー"],
        "voicing": [(i, value) for i, char in enumerate(reading) for value in DAKUTEN.get(char, ())],
        "small_tsu": [(i, "") for i, char in enumerate(reading) if char == "ッ"],
    }
    available = [kind for kind, options in candidates.items() if options]
    if not available:
        return reading, "no_applicable_edit"
    kind = rng.choice(available)
    i, value = rng.choice(candidates[kind])
    return reading[:i] + value + reading[i + 1:], kind


def base_input(row, actual, selector, rng):
    """保存済みASRを使い、音声のない行だけ条件Dの処理で合成する。"""
    sample_id = row["id"]
    if sample_id in actual["first_pass"]:
        return {key: actual[key][sample_id] for key in (*SOURCE_NAMES, "glossary")}
    seed = rng.randrange(2**31)
    marked = row.get("spoken_marked")
    if marked:
        glossary = row.get("glossary", [])
        hinted = {entry["surface"] for entry in glossary}
        overrides = ({}, {})
        if row.get("glossary_fixed") is True:
            first, merged, _ = plan_two_pass_error_overrides(marked, glossary, random.Random(seed + 701))
            overrides = (first, merged)
        first = simulate_asr_noise(marked, random.Random(seed + 101), HAAS_NOHINT, hinted, term_overrides=overrides[0])
        merged = simulate_asr_noise(marked, random.Random(seed + 211), HAAS_TWOPASS, hinted, term_overrides=overrides[1])
    else:
        first = merged = row["spoken_text"]
    if random.Random(seed + 503).random() < 0.5:
        first = to_user_punctuation(first, random.Random(seed + 601))
        merged = to_user_punctuation(merged, random.Random(seed + 603))
    asr = FormatterInput(first_pass=first, combined_text=merged)
    return {"first_pass": first, "combined_text": merged, "qwen_hypothesis": "",
            "glossary": [entry_record(e) for e in selector.select(formatter_input_text(asr), MAX_ENTRIES)]}


def source_worker(actual, selector):
    """worker内で条件Dのselectorと保存済みASRを再利用する。"""
    global worker_actual, worker_selector
    worker_actual, worker_selector = actual, selector


def base_input_in_worker(job):
    """親プロセスが先に割り当てたseedで1行を準備する。"""
    row, seed = job
    return base_input(row, worker_actual, worker_selector, random.Random(seed))


def prepared_rows(rows, actual, selector):
    """順序と乱数を固定し、条件Dの合成・選択だけをCPUで並列化する。"""
    source_rng = random.Random(0)
    rows = iter(row for row in rows if row["terms"])
    with ProcessPoolExecutor(max_workers=SOURCE_WORKERS, mp_context=multiprocessing.get_context("fork"),
                             initializer=source_worker, initargs=(actual, selector)) as executor:
        while batch := list(islice(rows, 512)):
            jobs = [(row, source_rng.randrange(2**31)) for row in batch]
            for row, original in zip(batch, executor.map(base_input_in_worker, jobs, chunksize=8), strict=True):
                yield row, original


def replacement_pattern(term, readings, other_terms, qwen=False):
    """表記・読みを長い順に合わせ、他の正解語に重なる置換を防ぐ。"""
    forms = {term, *readings}
    others = {form for key, values in other_terms.items() if key != term for form in (key, *values)}
    safe = forms - others
    choices = sorted((forms | others) - {""}, key=lambda part: (-len(part), part))
    branches = []
    for i, value in enumerate(choices):
        pattern = re.escape(value)
        if ascii_word(value[0]):
            pattern = r"(?<![A-Za-z0-9_])" + pattern
        if ascii_word(value[-1]):
            pattern += r"(?![A-Za-z0-9_])"
        if qwen and value.isascii() and any(char.isalpha() for char in value):
            spaced = r"\s*".join(re.escape(char) for char in value if not char.isspace())
            pattern += r"|(?<![A-Za-z0-9_])(?i:" + spaced + r")(?![A-Za-z0-9_])"
        branches.append(f"(?P<{'t' if value in safe else 'o'}{i}>{pattern})")
    return re.compile("|".join(branches))


def replace_at_matches(text, pattern, updated):
    """1回の走査で対象箇所を書き換え、元の他の文字を保持する。"""
    count = 0

    def substitute(match):
        """他の正解語は書き換えず、置換した出現だけを数える。"""
        nonlocal count
        if match.lastgroup.startswith("o"):
            return match[0]
        count += 1
        return updated

    return pattern.sub(substitute, text), count


class ReplacementPool:
    """種類が一致する差し替え先と、読みが近い候補を提供する。"""

    def __init__(self, entries, seen):
        self.entries = {e.surface: e for e in entries}
        self.by_kind = defaultdict(list)
        self.by_reading = defaultdict(list)
        self.used = Counter()
        self.ranked = {}
        for entry in entries:
            self.by_kind[term_kind(entry.surface), entry.surface in seen].append(entry)
            for reading in entry.readings:
                self.by_reading[reading].append(entry)
        self.readings = list(self.by_reading)

    def choose(self, term, target, existing, rng):
        """未出の用語を先に選び、各語を3回までに抑える。"""
        kind = term_kind(term)
        for seen in (False, True):
            # 消費済み語を末尾との交換で取り除き、一様な抽選を保つ。
            candidates = self.by_kind[kind, seen]
            for _ in range(80):
                if not candidates:
                    break
                i = rng.randrange(len(candidates))
                entry = candidates[i]
                if self.used[entry.surface] >= MAX_PER_TERM:
                    candidates[i] = candidates[-1]
                    candidates.pop()
                elif entry.surface not in target and entry.surface not in existing:
                    return entry
            eligible = [e for e in candidates if self.used[e.surface] < MAX_PER_TERM
                        and e.surface not in target and e.surface not in existing]
            if eligible:
                return rng.choice(eligible)
        return None

    def nearest(self, reading, target, occupied, count):
        """RapidFuzzの全体類似度が高い順に、正解と重複しない別語を返す。"""
        if not count:
            return []
        if reading not in self.ranked:
            self.ranked[reading] = [item[0] for item in process.extract(reading, self.readings, scorer=fuzz.ratio, limit=64)]
        found = []
        used = set(occupied)
        for candidate in self.ranked[reading]:
            for entry in self.by_reading[candidate]:
                if entry.surface in used or entry.surface in target:
                    continue
                found.append(entry)
                used.add(entry.surface)
                if len(found) == count:
                    return found
        return found


def swapped_glossary(original, term, new, target, gold, pool, rng):
    """正解語を残したまま上限20語を守り、近い読みの候補を追加する。"""
    entries = [entry_record(new) if entry["surface"] == term else entry for entry in original]
    protected = set(gold)
    replaced = any(entry["surface"] == term for entry in original)

    def insert(entry, position=None):
        """満杯なら元の一覧にある正解以外の語を一つ外す。"""
        if len(entries) >= MAX_ENTRIES:
            removable = [i for i, existing in enumerate(entries)
                         if existing["surface"] not in protected and existing["surface"] not in target]
            if not removable:
                return False
            entries.pop(rng.choice(removable))
        index = rng.randrange(len(entries) + 1) if position == "random" else len(entries)
        entries.insert(index, entry_record(entry))
        protected.add(entry.surface)
        return True

    mode = "replaced" if replaced else "omitted"
    if not replaced and rng.random() < 0.85 and insert(new, "random"):
        mode = "inserted"
    occupied = {e["surface"] for e in entries} | {term, new.surface} | set(gold)
    desired = rng.randint(0, 3)
    added = [entry.surface for entry in pool.nearest(new.readings[0], target, occupied, desired) if insert(entry)]
    return entries, mode, added


def create(row, original, term, entries, replacement, pool, rng):
    """指定した一語を正解・ASR3入力・一覧で差し替える。"""
    text = row["target_text"].replace(term, replacement.surface, 1)
    reading = replacement.readings[0]
    pronounced, noise_kind = noise(reading, rng)
    pattern = replacement_pattern(term, entries[term], entries)
    first, first_count = replace_at_matches(original["first_pass"], pattern, pronounced)
    if not first_count:
        raise ValueError(f"{row['id']}: Haas 1回目の差し替え箇所がありません")
    merged_value = replacement.surface if rng.random() < 0.6 else pronounced
    merged, merged_count = replace_at_matches(original["combined_text"], pattern, merged_value)
    qwen_mode = "empty"
    qwen, qwen_count = original["qwen_hypothesis"], 0
    if qwen:
        p = rng.random()
        if p < 0.25:
            qwen_mode, value = "surface", replacement.surface
        elif p < 0.40:
            qwen_mode = rng.choice(("lower", "no_space"))
            value = replacement.surface.lower() if qwen_mode == "lower" else replacement.surface.replace(" ", "")
        else:
            qwen_mode, value = "reading", pronounced
        qwen, qwen_count = replace_at_matches(qwen, replacement_pattern(term, entries[term], entries, qwen=True), value)
    gold = [replacement.surface if value == term else value for value in row["terms"]]
    glossary, listed, distractors = swapped_glossary(original["glossary"], term, replacement, text, gold, pool, rng)
    gold_glossary = [{"surface": surface, "readings": list(entries[surface])}
                     for surface in dict.fromkeys(row["terms"]) if surface != term and entries[surface]]
    gold_glossary.append(entry_record(replacement))
    augmented = {
        "id": f"rsi-{row['id']}", "source_id": row["id"], "target_text": text, "terms": gold,
        "gold_glossary": gold_glossary, "first_pass": first, "combined_text": merged,
        "qwen_hypothesis": qwen, "glossary": glossary,
    }
    detail = {
        "original_term": term, "new_term": replacement.surface, "reading": reading,
        "haas_reading": pronounced, "noise": noise_kind, "first_positions": first_count,
        "merged_positions": merged_count, "merged_mode": "surface" if merged_value == replacement.surface else "reading",
        "qwen_positions": qwen_count, "qwen_mode": qwen_mode, "listed": listed, "distractors": distractors,
    }
    return augmented, detail


def clean_row(row, blocked):
    """target・3仮説・用語一覧と読みを検査し、正解語と置き換え前以外の情報を保つ。"""
    texts = [row["target_text"], *(row[key] for key in SOURCE_NAMES), *row["terms"]]
    for entry in (*row["glossary"], *row["gold_glossary"]):
        texts.extend((entry["surface"], *entry["readings"]))
    return not any(has_blocked(text, blocked) for text in texts) and not has_spaced_asr_term(
        row["qwen_hypothesis"], blocked,
    )


def spoken_terms(row):
    """正解語と、言い直しで取り消した側も含む発話中の用語を保持する。"""
    readings = {entry.surface: set(entry.readings) for entry in map(entry_from_record, row["glossary"])}
    for _, surface, reading in MARK_PATTERN.findall(row.get("spoken_marked") or ""):
        if surface:
            readings.setdefault(surface, set()).add(reading)
    return {surface: tuple(sorted(values)) for surface, values in readings.items()}


def prepare(root):
    """元データを照合し、独立検査後に拡張の集計と例20件を確定する。"""
    home = Path.home()
    inputs = home / "voiceime-work-fr3/inputs"
    base = inputs / "sft3-20261122/train-sft3.jsonl"
    d = inputs / "d-multiasr-20261123"
    source_paths = {
        "first_pass": d / "train-runs/first-pass.jsonl",
        "combined_text": d / "train-runs/segment-merge.jsonl",
        "qwen_hypothesis": d / "train-runs/qwen06-hypothesis.jsonl",
        "glossary": d / "train-runs/formatter-glossary.jsonl",
    }
    glossary_path = inputs / "test-novel-20261122/glossary-v2.jsonl"
    excluded_path = inputs / "glossary-v2-excluded.txt"
    held_path = home / "voiceime-work-asr/r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
    novel_path = inputs / "test-novel-20261122/test-novel.jsonl"
    pool_path = d / "legacy/training-glossary.jsonl"
    excluded = {s for s in load_term_list(excluded_path) if not s.startswith("# ")}
    held = load_term_list(held_path)
    novel_rows = list(lines(novel_path))
    novel = {term for row in novel_rows for term in row["terms"]}
    originals = list(lines(base))
    assert (len(excluded), len(held), len(novel), len(novel_rows)) == (83, 6437, 500, 500)
    assert all(row["source"] == "synthetic-tts" for row in originals)
    assert len({row["id"] for row in originals}) == len(originals)
    actual = {name: source_index(path, "glossary" if name == "glossary" else "hyp")
              for name, path in source_paths.items()}
    support_ids = actual["first_pass"].keys()
    assert all(runs.keys() == support_ids for runs in actual.values())
    assert support_ids <= {row["id"] for row in originals}
    v2 = load_glossary(glossary_path)
    assert len(v2) == 31415
    blocked = blocked_index(excluded | held | novel)
    p = [entry for entry in v2 if entry.surface not in excluded | held | novel and entry.readings]
    # Pの定義と、実際に挿入できる表記・読みの漏えい検査を分ける。
    safe_p = [entry for entry in p if not has_blocked(entry.surface, blocked) and
              not any(has_blocked(reading, blocked) for reading in entry.readings) and
              not re.search(r"[A-Za-z]", entry.readings[0])]
    lookup = SurfaceIndex(e.surface for e in safe_p)
    seen = {surface for row in originals for surface in lookup.matches(row["target_text"])}
    original_pool = load_glossary(pool_path)
    selector = GlossaryIndex(original_pool)
    pool = ReplacementPool(safe_p, seen)
    rng = random.Random(0)
    rng.shuffle(originals)
    counts = Counter(without_terms=sum(not row["terms"] for row in originals))
    types = Counter()
    examples = []
    augmented_path = root / "augmentation.jsonl"
    root.mkdir(parents=True, exist_ok=False)
    limit = min(LIMIT, len(originals))
    with augmented_path.open("x", encoding="utf-8") as output:
        for row, original in prepared_rows(originals, actual, selector):
            if counts["created"] >= limit:
                break
            counts["examined"] += 1
            terms = spoken_terms(row)
            for gold_term in row["terms"]:
                terms.setdefault(gold_term, ())
            eligible = [
                term for term in dict.fromkeys(row["terms"]) if row["target_text"].count(term) == 1 and
                replace_at_matches(original["first_pass"], replacement_pattern(term, terms[term], terms), term)[1]
                and not any(term in other and other in row["target_text"] for other in terms if term != other)
            ]
            if not eligible:
                counts["without_replacement_position"] += 1
                continue
            term = rng.choice(eligible)
            existing = {entry["surface"] for entry in original["glossary"]} | set(terms)
            replacement = pool.choose(term, row["target_text"], existing, rng)
            if replacement is None:
                counts["without_available_term"] += 1
                continue
            new, detail = create(row, original, term, terms, replacement, pool, rng)
            if not clean_row(new, blocked):
                counts["excluded_from_output_by_leakage_check"] += 1
                continue
            output.write(compact(new) + "\n")
            pool.used[replacement.surface] += 1
            counts["created"] += 1
            counts["replacement_from_unseen_surface"] += replacement.surface not in seen
            counts["source_with_saved_asr"] += row["id"] in support_ids
            counts["noise_" + detail["noise"]] += 1
            counts["glossary_" + detail["listed"]] += 1
            counts["merged_" + (detail["merged_mode"] if detail["merged_positions"] else "no_match")] += 1
            counts["qwen_" + (detail["qwen_mode"] if detail["qwen_positions"] or not original["qwen_hypothesis"] else "no_match")] += 1
            counts["distractors_" + str(len(detail["distractors"]))] += 1
            types[term_kind(term)] += 1
            if len(examples) < 20:
                examples.append({"before": {**original, "target_text": row["target_text"]}, "after": new, **detail})

    # 出力を読み直し、禁止語を種類別に照合する。作成処理の集計値には依存しない。
    blocked_sets = {name: blocked_index(value) for name, value in
                    (("excluded", excluded), ("heldout", held), ("test_novel", novel))}
    leaks = Counter(dict.fromkeys(blocked_sets, 0))
    verified = 0
    for row in lines(augmented_path):
        verified += 1
        for name, index in blocked_sets.items():
            leaks[name] += not clean_row(row, index)
        assert len(row["glossary"]) <= MAX_ENTRIES
        assert len({entry["surface"] for entry in row["glossary"]}) == len(row["glossary"])
    assert verified == counts["created"] and verified > 0 and not any(leaks.values())
    assert max(pool.used.values()) <= MAX_PER_TERM
    counts_by_kind = defaultdict(dict)
    for kind, count in types.items():
        counts_by_kind[kind] = {"rows": count, "unique_terms": sum(term_kind(s) == kind for s in pool.used)}
    summary = {
        "seed": 0, "source_workers": SOURCE_WORKERS,
        "original_rows": len(originals), "source_rows_with_saved_asr": len(support_ids),
        "max_rows": limit, "candidate_pool_p": len(p), "usable_candidates_after_leakage_and_reading_check": len(safe_p),
        "usable_candidates_unseen_in_original_target": len(safe_p) - len(seen),
        "excluded_terms": len(excluded), "heldout_terms": len(held), "test_novel_terms": len(novel),
        "counts": dict(counts), "replacement_unique_terms": len(pool.used),
        "replacement_max_count": max(pool.used.values()), "counts_by_kind": counts_by_kind,
        "leakage_rows": dict(leaks), "verified_rows": verified,
        "augmentation_sha256": source_hash(augmented_path),
        "sources_sha256": {str(path): source_hash(path) for path in
                           (base, pool_path, glossary_path, excluded_path, held_path, novel_path, *source_paths.values())},
    }
    (root / "augmentation-examples.json").write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n")
    (root / "augmentation-audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(compact(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    prepare(parser.parse_args().output)
