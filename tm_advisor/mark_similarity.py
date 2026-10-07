"""How alike two word marks look and sound.

This is a screen, not the examiner's test: it finds marks worth a human look and says why.
"""

from dataclasses import dataclass, field

from .text import edit_similarity, phonetic_key, squash, words

# Words that add little to a mark's identity, so containment of only these does not count.
_WEAK_WORDS = {"the", "a", "an", "and", "of", "co", "pty", "ltd", "group", "australia", "au", "company"}


@dataclass
class MarkSimilarity:
    score: float
    reasons: list[str] = field(default_factory=list)


def compare(user_mark: str, cited_mark: str) -> MarkSimilarity:
    a, b = squash(user_mark), squash(cited_mark)
    if not a or not b:
        return MarkSimilarity(0.0)

    if a == b:
        if user_mark.strip().lower() == cited_mark.strip().lower():
            return MarkSimilarity(1.0, ["Identical words."])
        return MarkSimilarity(0.97, ["Same letters; only spacing, punctuation or capitals differ."])

    score = 0.0
    reasons: list[str] = []

    looks = edit_similarity(a, b)
    if looks >= 0.75:
        score = max(score, looks)
        reasons.append(f"Spelled very similarly ({round(looks * 100)}% letter match).")
    elif looks >= 0.6 and min(len(a), len(b)) >= 4:
        score = max(score, round(looks, 2))
        reasons.append(f"Spelled somewhat similarly ({round(looks * 100)}% letter match).")

    prefix = _common_prefix(a, b)
    if looks < 0.75 and len(prefix) >= 3 and len(prefix) * 2 >= min(len(a), len(b)) and abs(len(a) - len(b)) <= 3:
        score = max(score, 0.6)
        reasons.append(f"Begins with the same letters ('{prefix.upper()}'), which people tend to notice and remember.")

    key_a, key_b = phonetic_key(a), phonetic_key(b)
    if len(key_a) >= 2 and key_a == key_b and abs(len(a) - len(b)) <= 3:
        score = max(score, 0.9)
        reasons.append("Likely to sound alike when spoken.")

    shorter, longer = sorted((a, b), key=len)
    whole_contained = len(shorter) >= 4 and shorter in longer
    if whole_contained:
        contained = 0.85 if longer.startswith(shorter) else 0.75
        score = max(score, contained)
        reasons.append(f"'{shorter.upper()}' appears inside '{longer.upper()}'.")

    common_words = set(words(user_mark)) & set(words(cited_mark))
    elements = [(w, b, cited_mark) for w in words(user_mark)] + [(w, a, user_mark) for w in words(cited_mark)]
    for word, other, other_text in [] if whole_contained else elements:
        if len(word) >= 4 and word not in _WEAK_WORDS and word not in common_words and word in other:
            score = max(score, 0.75)
            reasons.append(f"The word '{word.upper()}' appears inside '{other_text.upper()}'.")
            break

    shared = common_words - _WEAK_WORDS
    shared = {w for w in shared if len(w) >= 3}
    if shared:
        score = max(score, 0.7)
        reasons.append("Shares the word(s): " + ", ".join(sorted(w.upper() for w in shared)) + ".")

    return MarkSimilarity(round(score, 2), reasons)


def _common_prefix(a: str, b: str) -> str:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n]
