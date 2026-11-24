"""正解文を保ったまま一覧から学習済みの正解語を抜く。"""


def drop_seen_terms(glossary, terms, target, eligible, probability, rng):
    """一覧にある対象語ごとに1回だけ抽選し、抜くと決まった表記の全項目を除く。"""
    gold = {term for term in terms if term in eligible and term in target}
    candidates = dict.fromkeys(entry.surface for entry in glossary if entry.surface in gold)
    removed = {term for term in candidates if rng.random() < probability}
    return [entry for entry in glossary if entry.surface not in removed]
