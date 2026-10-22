"""Entity resolution bands - port of the Meterless reference resolve.ts (Apache-2.0).

    similarity >= 0.85          -> "auto-merge"  (0.85 exactly merges)
    0.82 <= similarity < 0.85   -> "review"      (0.82 exactly queues for review)
    similarity < 0.82           -> "new"
Similarity = 1 - Levenshtein distance / longer length, on NORMALIZED names.
"""
from app.engines.world_model.stable_ids import normalize_name

AUTO_MERGE_AT = 0.85
REVIEW_LOWER = 0.82


def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def name_similarity(raw_a, raw_b):
    a, b = normalize_name(raw_a), normalize_name(raw_b)
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1 - levenshtein(a, b) / longest


def decide(similarity, auto_merge_at=AUTO_MERGE_AT, review_lower=REVIEW_LOWER):
    """'auto-merge' | 'review' | 'new' (boundary values: 0.85 merges, 0.82 queues)."""
    if similarity >= auto_merge_at:
        return "auto-merge"
    if similarity >= review_lower:
        return "review"
    return "new"
