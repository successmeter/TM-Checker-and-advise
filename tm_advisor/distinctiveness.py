"""A screen for section 41 problems: marks that describe the goods or praise them.

Distinctiveness is judged for the mark against its goods/services. Changing the goods list does not make a
descriptive mark distinctive, so these flags point at the mark itself.
"""

from .models import DistinctivenessFlag
from .text import stem, words

_LAUDATORY = {
    "best", "premium", "quality", "ultimate", "super", "supreme", "elite", "prime", "deluxe", "luxury", "perfect",
    "top", "first", "number", "one", "pro", "professional", "original", "genuine", "smart", "easy", "fresh",
    "natural", "pure", "fast", "quick", "cheap", "value", "gold", "royal", "classic", "superior", "great",
    "success", "successful", "winning", "winner", "excellence", "expert", "leading", "champion", "ideal",
}
_DESCRIPTIVE = {
    "eco", "green", "organic", "vegan", "local", "aussie", "australian", "online", "digital", "global", "kids",
    "baby", "home", "health", "healthy", "fit", "fitness", "tech", "solutions", "services", "store", "shop",
    "co", "group", "hub", "app", "cloud", "web", "plus", "max", "mini",
}
_GEOGRAPHIC = {
    "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "hobart", "darwin", "canberra",
    "bondi", "byron", "queensland", "victoria", "tasmania", "nsw", "qld", "vic", "wa", "sa", "nt", "act",
}
_GLUE = {"the", "a", "an", "and", "of", "by", "for", "&"}


def screen(mark: str, all_terms: list[str]) -> tuple[list[DistinctivenessFlag], bool]:
    """Flags for each problem word, and whether every meaningful word in the mark is flagged."""
    goods_stems = {stem(w) for t in all_terms for w in words(t) if len(w) >= 3}
    flags: list[DistinctivenessFlag] = []
    meaningful = [w for w in words(mark) if w not in _GLUE]

    for word in meaningful:
        s = stem(word)
        if s in goods_stems or any(g.startswith(s) and len(s) >= 4 for g in goods_stems):
            flags.append(DistinctivenessFlag(word=word, reason="Describes the goods or services you listed."))
        elif word in _LAUDATORY:
            flags.append(DistinctivenessFlag(word=word, reason="Praises the goods (a word other traders may need to use)."))
        elif word in _GEOGRAPHIC:
            flags.append(DistinctivenessFlag(word=word, reason="A place name, which may describe where the goods come from."))
        elif word in _DESCRIPTIVE:
            flags.append(DistinctivenessFlag(word=word, reason="A common descriptive word in trade."))

    wholly_descriptive = bool(meaningful) and len({f.word for f in flags}) == len(set(meaningful))
    return flags, wholly_descriptive


# Ordinary words that praise or describe: sharing one of these with another mark is a weak resemblance.
COMMON_WORDS = _LAUDATORY | _DESCRIPTIVE | _GEOGRAPHIC
