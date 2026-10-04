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

    key_a, key_b = phonetic_key(a), phonetic_key(b)
    if len(key_a) >= 2 and key_a == key_b and abs(len(a) - len(b)) <= 3:
        score = max(score, 0.9)
        reasons.append("Likely to sound alike when spoken.")

    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 4 and shorter in longer:
        contained = 0.85 if longer.startswith(shorter) else 0.75
        score = max(score, contained)
        reasons.append(f"'{shorter.upper()}' appears inside '{longer.upper()}'.")

    shared = (set(words(user_mark)) & set(words(cited_mark))) - _WEAK_WORDS
    shared = {w for w in shared if len(w) >= 3}
    if shared:
        score = max(score, 0.7)
        reasons.append("Shares the word(s): " + ", ".join(sorted(w.upper() for w in shared)) + ".")

    return MarkSimilarity(round(score, 2), reasons)
