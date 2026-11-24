"""書き出した拡張データを元manifestと再照合し、一語差し替えと転用上限を確認する。"""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from analyze_baselines import term_kind
from prepare_rsi import SurfaceIndex, ascii_word, blocked_index, canonical, lines
from voiceime.formatter.glossary import load_term_list


def qwen_compact_match(text, blocked):
    """ASCII記号を含む区間でも字間空白を詰め、元の単語境界で禁用語を照合する。"""
    for matched in re.finditer(r"[!-~]+(?: [!-~]+)+", canonical(text)):
        raw = matched[0]
        positions = [i for i, char in enumerate(raw) if char != " "]
        compact = "".join(raw[i] for i in positions)
        for start, end, term in blocked.occurrences(compact):
            left, right = positions[start], positions[end - 1] + 1
            if ((left == 0 or not ascii_word(term[0]) or not ascii_word(raw[left - 1])) and
                (right == len(raw) or not ascii_word(term[-1]) or not ascii_word(raw[right]))):
                return term
    return None


def verify():
    """拡張JSONLの出典と各例の厳密な変更範囲を独立に検査する。"""
    home = Path.home()
    fr3 = home / "voiceime-work-fr3/inputs"
    work = home / "voiceime-work-wops/rsi1/data"
    audit = json.loads((work / "augmentation-audit.json").read_text())
    base_path = fr3 / "sft3-20261122/train-sft3.jsonl"
    past = {row["id"]: (row["target_text"], Counter(row["terms"])) for row in lines(base_path)}
    excluded = load_term_list(fr3 / "glossary-v2-excluded.txt")
    held = load_term_list(home / "voiceime-work-asr/r3-twopass-20261122/terms/exclude-v2-plus-heldout.txt")
    novel = {term for row in lines(fr3 / "test-novel-20261122/test-novel.jsonl") for term in row["terms"]}
    blocked = blocked_index(held | novel | {term for term in excluded if not term.startswith("# ")})
    qwen_count = 0
    swaps = Counter()
    ids = set()
    output = work / "augmentation.jsonl"
    for row in lines(output):
        sample = row["source_id"]
        if row["id"] in ids or row["id"] != f"rsi-{sample}":
            raise ValueError(f"拡張IDの重複または不一致 {row['id']}")
        ids.add(row["id"])
        target, orig_terms = past[sample]
        new_terms = Counter(row["terms"])
        old, = (orig_terms - new_terms).elements()
        new, = (new_terms - orig_terms).elements()
        if term_kind(old) != term_kind(new) or target.count(old) != 1 or target.replace(old, new, 1) != row["target_text"]:
            raise ValueError(f"{row['id']}: 置換した1語以外に正解文の変更があります")
        swaps[new] += 1
        if row["qwen_hypothesis"]:
            qwen_count += 1
            if match := qwen_compact_match(row["qwen_hypothesis"], blocked):
                raise ValueError(f"{row['id']}: 禁用語の字間空白表記が残っています ({match})")
    with output.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    assert digest == audit["augmentation_sha256"]
    assert not any(audit["leakage_rows"].values())
    assert len(ids) == audit["verified_rows"] == sum(swaps.values())
    assert max(swaps.values()) == audit["replacement_max_count"] <= 3
    assert len(swaps) == audit["replacement_unique_terms"]
    replaced = SurfaceIndex(swaps.keys())
    seen = {surface for target, _ in past.values() for surface in replaced.matches(target)}
    unseen_rows = sum(count for surface, count in swaps.items() if surface not in seen)
    assert unseen_rows == audit["counts"]["replacement_from_unseen_surface"]
    return {"rows": len(ids), "max_swaps_per_term": max(swaps.values()), "qwen_nonempty": qwen_count,
            "qwen_additional_matches": 0, "augmentation_sha256": digest,
            "replacement_unique_seen_in_original_targets": len(seen),
            "replacement_unique_absent_from_original_targets": len(swaps) - len(seen),
            "replacement_rows_absent_from_original_targets": unseen_rows}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
