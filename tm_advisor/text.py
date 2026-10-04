"""Small text helpers for comparing marks and goods descriptions."""

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    """Lower case, punctuation to spaces, single spaces."""
    return " ".join(_NON_ALNUM.sub(" ", text.lower()).split())


def squash(text: str) -> str:
    """The mark with spaces and punctuation removed, so ECO-KNIT and EcoKnit compare equal."""
    return normalise(text).replace(" ", "")


def words(text: str) -> list[str]:
    return normalise(text).split()


def stem(word: str) -> str:
    """Strip common English plurals: sweaters -> sweater, dresses -> dress, accessories -> accessory."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "shes", "ches", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def stems(text: str) -> set[str]:
    return {stem(w) for w in words(text)}


def edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def edit_similarity(a: str, b: str) -> float:
    """1.0 for identical strings, 0.0 for nothing in common."""
    if not a and not b:
        return 1.0
    return 1.0 - edit_distance(a, b) / max(len(a), len(b))


_PHONETIC_RULES = [
    ("ph", "f"), ("ck", "k"), ("qu", "kw"), ("q", "k"), ("x", "ks"), ("z", "s"),
    ("ce", "se"), ("ci", "si"), ("cy", "sy"), ("c", "k"), ("gh", "g"), ("wr", "r"),
    ("kn", "n"), ("y", "i"),
]


def phonetic_key(text: str) -> str:
    """A rough sound-alike key: KWIK and QUICK, FONE and PHONE, KOOL and COOL share a key.

    Keeps the first letter's sound, then drops vowels and doubled letters.
    """
    s = squash(text)
    if not s:
        return ""
    for old, new in _PHONETIC_RULES:
        s = s.replace(old, new)
    head, tail = s[0], s[1:]
    tail = re.sub(r"[aeiouhw]", "", tail)
    key = head
    for ch in tail:
        if ch != key[-1]:
            key += ch
    return key
