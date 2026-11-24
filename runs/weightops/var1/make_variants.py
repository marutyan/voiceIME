"""FULLの実ASR行から発音ゆれ学習例と固定のval診断セットを作る。"""

import argparse
import hashlib
import json
import random
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path

from fix_omitted_terms import has_surface, surface_key, write_jsonl
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

HOME = Path.home()
WORK = HOME / "voiceime-work-wops"
FR3 = HOME / "voiceime-work-fr3/inputs"
FULL = WORK / "full1/data"
D = FR3 / "d-multiasr-20261123"
VAR = WORK / "var1"
ALT = VAR / "glossary-alt-readings.jsonl"
AUG = WORK / "fix1/data/augmentation-fixed.jsonl"
HELDOUT = HOME / "voiceime-work-asr/r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt"
RUNS = {"first_pass": "first-pass.jsonl", "combined_text": "segment-merge.jsonl",
        "qwen_hypothesis": "qwen06-hypothesis.jsonl"}
POSITIVE_COUNT = 24000
NEGATIVE_COUNT = 9600
KANA = r"ァ-ヶー"
KANA_WORD = re.compile(rf"[{KANA}]{{4,}}")
LONG_VOWEL = "アイウエオカキクケコガギグゲゴサシスセソザジズゼゾタチツテトダヂヅデドナニヌネノハヒフヘホバビブベボパピプペポマミムメモヤユヨラリルレロワャュョァィゥェォ"
GEMINATE = "カキクケコサシスセソタチツテトハヒフヘホパピプペポ"


def records(path):
    """JSONLを順序どおりに読み込む。"""
    with path.open(encoding="utf-8") as source:
        for line in source:
            yield json.loads(line)


def file_hash(path):
    """入力と出力のSHA-256を記録する。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def kana(text):
    """仮名をNFKCとカタカナにそろえて読みを比較する。"""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in normalized)


def rule_variants(reading):
    """基本読みに長音・促音・小さな文字編集・語尾の変化を1つ加える。"""
    for index, char in enumerate(reading):
        if char in "ーッ":
            yield reading[:index] + reading[index + 1:], "長音" if char == "ー" else "促音"
        if char in LONG_VOWEL and reading[index + 1:index + 2] != "ー":
            yield reading[:index + 1] + "ー" + reading[index + 1:], "長音"
        if char in GEMINATE and index and reading[index - 1] != "ッ":
            yield reading[:index] + "ッ" + reading[index:], "促音"
        if len(reading) >= 5 and char not in "ーッ":
            yield reading[:index] + reading[index + 1:], "1文字脱落"
    for a, b in (("ティ", "チ"), ("ディ", "ジ"), ("ヴ", "ブ"), ("フ", "ホ"),
                 ("ス", "ズ"), ("シ", "ジ"), ("チ", "ジ"), ("ウ", "オ")):
        for old, new in ((a, b), (b, a)):
            for match in re.finditer(old, reading):
                yield reading[:match.start()] + new + reading[match.end():], "置換"
    for old, new in (("ディー", "ド"), ("ド", "ディー"), ("ティー", "ト"),
                     ("ト", "ティー"), ("ダー", "ド"), ("ル", "ー"), ("ス", "ズ")):
        if reading.endswith(old):
            yield reading[:-len(old)] + new, "語尾"


@cache
def term_pattern(surface, readings):
    """表記と基本読みの候補を長い順に並べ、短い片仮名・英数字の部分一致を抑える。"""
    forms = {surface, *(v for v in readings if v)}
    alternatives = []
    for form in sorted(forms, key=lambda text: (-len(text), text)):
        if form.isascii():
            alternatives.append(r"(?<![A-Za-z0-9])" + re.escape(form) + r"(?![A-Za-z0-9])")
        elif len(form) <= 3 and re.fullmatch(rf"[{KANA}]+", form):
            alternatives.append(rf"(?<![{KANA}])" + re.escape(form) + rf"(?![{KANA}])")
        else:
            alternatives.append(re.escape(form))
    return re.compile("|".join(alternatives), flags=re.IGNORECASE)


def read_inputs(directory, glossary_file):
    """同じIDの3本のASR文と一覧を取得する。"""
    inputs = {field: {row["id"]: row["hyp"] for row in records(directory / name)}
              for field, name in RUNS.items()}
    lists = {row["id"]: row["glossary"] for row in records(glossary_file)}
    if any(values.keys() != lists.keys() for values in inputs.values()):
        raise ValueError(f"{directory}: 一覧とASRのIDが一致しません")
    return inputs, lists


class Vocabulary:
    """FULLの学習辞書と追加読みを管理し、混同候補を探す。"""

    def __init__(self):
        self.pool = {row["surface"]: row for row in records(D / "legacy/training-glossary.jsonl")}
        self.alt = {row["surface"]: row["readings"] for row in records(ALT)}
        original = FR3 / "sft3-20261122/train-sft3.jsonl"
        self.protected = {surface_key(term) for term in HELDOUT.read_text().splitlines() if term.strip()}
        self.protected.update(surface_key(term["surface"])
                              for row in records(original) for term in row.get("omitted_terms", []))
        self.owners = defaultdict(set)
        self.by_length = defaultdict(list)
        for term, entry in self.pool.items():
            for reading in (*entry["readings"], *self.alt.get(term, [])):
                self.owners[kana(reading)].add(term)
        for reading in self.owners:
            if KANA_WORD.fullmatch(reading):
                self.by_length[len(reading)].append(reading)
        self.surface_keys = {surface_key(term) for term in self.pool}

    @cache
    def options(self, term, readings):
        """他の用語と同じ読みを避け、追加済み読みと規則生成候補を分けて返す。"""
        originals = {kana(reading) for reading in readings}
        added = {}
        for reading in self.alt.get(term, ()):
            added[kana(reading)] = "別読みファイル"
        written = {}
        for reading in sorted(originals):
            if not re.fullmatch(rf"[{KANA}]{{3,}}", reading):
                continue
            for changed, kind in rule_variants(reading):
                written.setdefault(changed, kind)

        def retain(candidates):
            return [(reading, kind) for reading, kind in candidates.items()
                    if reading not in originals and re.fullmatch(rf"[{KANA}]{{3,}}", reading)
                    and not (self.owners.get(reading, set()) - {term})]

        added = dict(retain(added))
        return list(added.items()), [(r, k) for r, k in retain(written) if r not in added]

    @cache
    def near_terms(self, word):
        """普通のカタカナ語と距離1〜2の、既存辞書読みを持つ表記を返す。"""
        result = {}
        for length in range(len(word) - 2, len(word) + 3):
            for reading, distance, _ in process.extract_iter(
                word, self.by_length[length], scorer=Levenshtein.distance, score_cutoff=2,
            ):
                for term in sorted(self.owners[reading]):
                    if surface_key(term) in self.protected or reading not in map(kana, self.pool[term]["readings"]):
                        continue
                    if distance and (term not in result or distance < result[term][1]):
                        result[term] = reading, distance
        return [(term, reading, distance) for term, (reading, distance) in result.items()]


def make_example(row, inputs, glossary, mode):
    """fix1の拡張Datasetが読む形式で、正解文と用語注記を保つ。"""
    return {"id": f"var-{mode}-{row['id']}", "source_id": row["id"],
            "target_text": row["target_text"], "terms": row["terms"],
            "gold_glossary": row["glossary"], "glossary": glossary, **inputs}


def positive(row, inputs, glossary, vocab, rng):
    """一覧内の正解語1種類の表記・基本読みを見つけ、ASR文ごとに別読みを選ぶ。"""
    listed = {entry["surface"]: entry["readings"] for entry in glossary}
    choices = [term for term in dict.fromkeys(row["terms"])
               if term in listed and term in vocab.pool and surface_key(term) not in vocab.protected
               and row["target_text"].count(term) == 1]
    rng.shuffle(choices)
    for term in choices:
        forms = tuple(dict.fromkeys((*listed[term], *vocab.pool[term]["readings"])))
        added, generated = vocab.options(term, forms)
        if not (added or generated):
            continue
        blocked = {}
        for other in set(row["terms"]) - {term}:
            other_forms = tuple(vocab.pool.get(other, {}).get("readings", listed.get(other, ())))
            for field, text in inputs.items():
                blocked.setdefault(field, []).extend(m.span() for m in term_pattern(other, other_forms).finditer(text))
        result = dict(inputs)
        changes = {}
        for field, text in inputs.items():
            matches = [m for m in term_pattern(term, forms).finditer(text)
                       if not any(m.start() < end and start < m.end() for start, end in blocked.get(field, ()))]
            if not matches:
                continue
            primary = (added or generated) if rng.random() < 0.5 else (generated or added)
            changed, kind = rng.choice(primary)
            for match in reversed(matches):
                result[field] = result[field][:match.start()] + changed + result[field][match.end():]
            changes[field] = {"from": [m.group() for m in matches], "to": changed, "kind": kind}
        if changes:
            return make_example(row, result, glossary, "positive"), {"term": term, "changes": changes}
    return None


def negative(row, inputs, glossary, vocab, rng):
    """実際の文に残る普通語に似た読みの用語を、元の正解語を保って一覧へ混ぜる。"""
    text = row["target_text"]
    base = unicodedata.normalize("NFKC", text)
    spoken = " ".join(row.get(field, "") or "" for field in ("spoken_text", "spoken_text_kana"))
    used = {entry["surface"] for entry in glossary}
    gold = set(row["terms"])
    words = list(dict.fromkeys(KANA_WORD.findall(base)))
    rng.shuffle(words)
    for word in words:
        if (word in vocab.owners or surface_key(word) in vocab.surface_keys or
                any(word in kana(term) for term in gold) or not any(word in kana(hyp) for hyp in inputs.values())):
            continue
        choices = vocab.near_terms(word).copy()
        rng.shuffle(choices)
        for term, reading, distance in choices:
            entry = vocab.pool[term]
            if term in used or term in gold or has_surface(text + " " + spoken, term):
                continue
            if any(kana(r) in kana(text + " " + spoken) for r in (*entry["readings"], *vocab.alt.get(term, []))):
                continue
            modified = list(glossary)
            evicted = None
            if len(modified) >= 20:
                index = next((i for i in range(len(modified) - 1, -1, -1)
                              if modified[i]["surface"] not in gold
                              and not has_surface(spoken, modified[i]["surface"])
                              and not any(kana(r) in kana(spoken) for r in modified[i]["readings"])), None)
                if index is None:
                    continue
                evicted = modified.pop(index)["surface"]
            modified.insert(rng.randrange(min(len(modified), 5) + 1), entry)
            return make_example(row, inputs, modified, "negative"), {
                "word": word, "term": term, "reading": reading, "distance": distance, "evicted": evicted}
    return None


def train(vocab):
    """元の拡張をそのまま先頭に残し、固定seedで正例と負例を規定件数作る。"""
    seed = 173
    rng = random.Random(seed)
    row_map = {row["id"]: row for row in records(FULL / "train-fixed.jsonl")}
    run = FULL / "train-runs"
    inputs, lists = read_inputs(run, run / "formatter-glossary.jsonl")
    ids = [sample_id for sample_id in lists if not row_map[sample_id].get("omitted_terms")]
    rng.shuffle(ids)
    examples = {"positive": [], "negative": []}
    counts = Counter()
    types = defaultdict(set)
    distribution = {"positive": Counter(), "negative": Counter()}
    detail_examples = []
    for mode, generate, limit in (("positive", positive, POSITIVE_COUNT), ("negative", negative, NEGATIVE_COUNT)):
        signatures = {}
        for attempt in range(2):
            for sample_id in ids:
                asr = {field: values[sample_id] for field, values in inputs.items()}
                if any(not value for value in asr.values()):
                    continue
                got = generate(row_map[sample_id], asr, lists[sample_id], vocab, rng)
                if not got:
                    continue
                row, detail = got
                signature = tuple(row[field] for field in RUNS) if mode == "positive" else detail["term"]
                if signatures.get(sample_id) == signature:
                    continue
                signatures[sample_id] = signature
                if attempt:
                    row["id"] += f"-{attempt + 1}"
                    counts[f"{mode}_second_version_rows"] += 1
                examples[mode].append(row)
                counts[mode] += 1
                types[mode].add(detail["term"])
                counts[f"{mode}_listed_terms_removed"] += len(
                    set(row["terms"]) & ({e["surface"] for e in lists[sample_id]}
                                         - {e["surface"] for e in row["glossary"]}))
                if mode == "positive":
                    for change in detail["changes"].values():
                        distribution[mode][change["kind"]] += len(change["from"])
                    counts[f"positive_changed_{len(detail['changes'])}_passes"] += 1
                else:
                    distribution[mode][f"distance_{detail['distance']}"] += 1
                    counts["negative_replaced_distractor_rows"] += detail["evicted"] is not None
                if counts[mode] <= 10:
                    detail_examples.append({"mode": mode, "source_id": sample_id, "target": row["target_text"], **detail})
                if counts[mode] == limit:
                    break
            if counts[mode] == limit:
                break
        counts[f"{mode}_source_rows"] = len(signatures)
        if counts[mode] != limit:
            raise ValueError(f"{mode}件数不足: {counts[mode]}/{limit}")
    data = VAR / "data"
    data.mkdir()
    with (data / "augmentation-var.jsonl").open("xb") as sink, AUG.open("rb") as past:
        shutil.copyfileobj(past, sink)
        for mode in examples:
            for row in examples[mode]:
                sink.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    audit = {"seed": seed, "counts": counts, "distribution": distribution,
             "term_types": {mode: len(terms) for mode, terms in types.items()},
             "sha256": {p.name: file_hash(p) for p in (ALT, AUG, data / "augmentation-var.jsonl")},
             "examples": detail_examples}
    (data / "generation-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "examples"}, ensure_ascii=False, indent=2))


def val(vocab):
    """別seedでvalを加工し、変えた語と元の一覧を固定して書き出す。"""
    seed = 913
    rng = random.Random(seed)
    glossary_file = FR3 / "glossary-capacity-20261123-corrected/glossaries/val/max32-haas-qwen.jsonl"
    inputs, lists = read_inputs(D / "val-runs", glossary_file)
    rows = list(records(FR3 / "manifest-val-no-audio.jsonl"))
    output = VAR / "val-variants"
    manifests, glossaries, changed, runs = [], [], [], {key: [] for key in RUNS}
    kinds = Counter()
    passes = Counter()
    for row in rows:
        sample_id = row["id"]
        original = {field: values[sample_id] for field, values in inputs.items()}
        got = positive(row, original, lists[sample_id], vocab, rng)
        if not got:
            continue
        augmented, detail = got
        manifests.append(row)
        glossaries.append({"id": sample_id, "glossary": lists[sample_id]})
        changed.append({"id": sample_id, **detail})
        for field in RUNS:
            runs[field].append({"id": sample_id, "hyp": augmented[field]})
        for change in detail["changes"].values():
            kinds[change["kind"]] += len(change["from"])
        passes[len(detail["changes"])] += 1
    if not manifests:
        raise ValueError("val-ゆれが0件です")
    output.mkdir()
    write_jsonl(output / "manifest.jsonl", manifests)
    write_jsonl(output / "formatter-glossary.jsonl", glossaries)
    write_jsonl(output / "changed.jsonl", changed)
    for field, name in RUNS.items():
        write_jsonl(output / name, runs[field])
    summary = {"seed": seed, "val_rows": len(rows), "changed_rows": len(manifests),
               "all_reference_terms": sum(len(row["terms"]) for row in manifests),
               "changed_pass_count": passes, "distribution": kinds,
               "sha256": {p.name: file_hash(p) for p in sorted(output.glob("*.jsonl"))}}
    (output / "audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("train", "val"))
    args = parser.parse_args()
    (train if args.split == "train" else val)(Vocabulary())
