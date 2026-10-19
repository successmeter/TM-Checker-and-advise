"""Whether the user's goods/services overlap a cited mark's goods/services.

Section 44 asks whether goods are the same, of the same description, or closely related services.
This screen approximates that with word overlap inside a class, broad headings that cover a whole class,
and a short curated list of class pairs examiners commonly treat as related. It errs on the side of flagging.
"""

from dataclasses import dataclass

from .models import ClassOverlap, GoodsLevel
from .text import stems

_FILLER = {
    "and", "of", "for", "in", "the", "to", "relation", "a", "being", "namely", "service", "featuring",
    "all", "other", "goods", "product", "include", "including", "use", "with", "or", "online",
}

# Words that, alone, make a term a broad heading for the class (e.g. "Clothing", "Computer software").
_BROAD_WORDS = {
    9: {"computer", "software", "downloadable", "application", "app", "mobile"},
    25: {"clothing", "apparel", "garment", "wear", "fashion"},
    35: {"retail", "wholesale", "advertising", "marketing", "business"},
    42: {"software", "computer", "it", "technology", "saa"},
}


@dataclass(frozen=True)
class _RelatedPair:
    """Two classes examiners commonly treat as related, but only for the goods named on each side.

    `sides` maps a class to the words its terms must contain for the pair to apply (no entry: any term). Each side
    is checked against that side's own terms, so a class 9 mark for safety boots is not "related" to software
    services just because the user's class 42 terms mention software.
    """
    classes: frozenset[int]
    sides: dict[int, frozenset[str]]
    note: str


_SOFTWARE_GOODS = frozenset({"software", "computer", "app", "application", "downloadable", "program", "programme",
                             "firmware", "database", "platform", "saa", "game", "e", "ebook"})
_SOFTWARE_SERVICES = frozenset({"software", "computer", "saa", "paa", "iaa", "platform", "program", "programming",
                                "app", "application", "website", "web", "cloud", "database", "hosting", "it"})
_CLOTHING = frozenset({"clothing", "apparel", "footwear", "headwear", "fashion", "garment"})

_RELATED = [
    _RelatedPair(frozenset({25, 35}), {35: _CLOTHING},
                 "Retail of clothing (class 35) is commonly treated as closely related to clothing (class 25)."),
    _RelatedPair(frozenset({9, 42}), {9: _SOFTWARE_GOODS, 42: _SOFTWARE_SERVICES},
                 "Software goods (class 9) and software services (class 42) are commonly treated as closely related."),
    _RelatedPair(frozenset({30, 43}), {30: frozenset({"coffee", "tea", "bakery", "bread", "pastry", "cake"})},
                 "Food and drink goods (class 30) are often related to cafe or restaurant services (class 43)."),
    _RelatedPair(frozenset({29, 43}), {},
                 "Food goods (class 29) are often related to restaurant services (class 43)."),
    _RelatedPair(frozenset({32, 33}), {},
                 "Non-alcoholic (class 32) and alcoholic (class 33) drinks are often treated as related."),
    _RelatedPair(frozenset({3, 5}), {},
                 "Cosmetics (class 3) and pharmaceutical or health goods (class 5) can be treated as related."),
    _RelatedPair(frozenset({18, 25}), {},
                 "Bags and leather goods (class 18) are often sold alongside clothing (class 25)."),
    _RelatedPair(frozenset({9, 41}), {9: _SOFTWARE_GOODS,
                                      41: frozenset({"education", "educational", "training", "fitness", "game",
                                                     "entertainment", "learning"})},
                 "Downloadable content or apps (class 9) can relate to the matching education or entertainment services (class 41)."),
    _RelatedPair(frozenset({35, 42}), {35: frozenset({"software", "computer", "platform", "database", "marketplace",
                                                      "website", "saa"}),
                                       42: _SOFTWARE_SERVICES},
                 "Online business platforms can sit across class 35 and class 42."),
]


def _content(term: str) -> set[str]:
    return stems(term) - _FILLER


# How a mark registered for every class (class "All" on the register) lists its goods and services here.
ALL_GOODS = "All goods and services"


def _is_broad(class_number: int, term: str) -> bool:
    if term == ALL_GOODS:
        return True
    content = _content(term)
    broad = _BROAD_WORDS.get(class_number, set())
    return bool(content) and content <= broad


def _matching(terms: list[str], keywords: frozenset[str] | None) -> list[str] | None:
    """The terms that bring a related-class pair into play, or None if none do.

    With no keywords every term counts. With no terms (the register gave none) the pair is assumed to apply,
    erring on the side of flagging.
    """
    if not keywords or not terms:
        return list(terms)
    found = [t for t in terms if stems(t) & keywords or t == ALL_GOODS]
    return found or None


def relate(user_class: int, user_terms: list[str], cited_class: int, cited_terms: list[str]) -> ClassOverlap:
    if user_class == cited_class:
        return _same_class(user_class, user_terms, cited_terms)

    pair = next((p for p in _RELATED if p.classes == frozenset({user_class, cited_class})), None)
    if pair:
        user_match = _matching(user_terms, pair.sides.get(user_class))
        cited_match = _matching(cited_terms, pair.sides.get(cited_class))
        if user_match is not None and cited_match is not None:
            note = pair.note
            if cited_terms and pair.sides.get(cited_class):
                note += " Their goods/services include: " + "; ".join(cited_match[:3]) + "."
            return ClassOverlap(user_class=user_class, cited_class=cited_class, level=GoodsLevel.RELATED,
                                overlapping_terms=user_match, narrowing_helps=False, note=note)

    return ClassOverlap(user_class=user_class, cited_class=cited_class, level=GoodsLevel.NONE,
                        overlapping_terms=[], narrowing_helps=False, note="Different classes with no known close relationship.")


def _same_class(class_number: int, user_terms: list[str], cited_terms: list[str]) -> ClassOverlap:
    cited_broad = any(_is_broad(class_number, t) for t in cited_terms)
    cited_words = set().union(*(_content(t) for t in cited_terms)) if cited_terms else set()

    overlapping: list[str] = []
    broad_user_terms: list[str] = []
    for term in user_terms:
        if _is_broad(class_number, term):
            broad_user_terms.append(term)
            overlapping.append(term)
        elif cited_broad or _content(term) & cited_words:
            overlapping.append(term)

    if not overlapping:
        return ClassOverlap(user_class=class_number, cited_class=class_number, level=GoodsLevel.RELATED,
                            overlapping_terms=[], narrowing_helps=False,
                            note="Same class but no shared wording. The examiner may still find the goods related.")

    if cited_broad:
        note = "The cited mark covers a broad heading in this class, so leaving out terms is unlikely to avoid the overlap."
        helps = False
    elif len(overlapping) == len(user_terms):
        note = "Every one of your terms in this class overlaps the cited goods/services."
        helps = False
    else:
        note = "Some of your terms overlap the cited goods/services."
        helps = True
    if broad_user_terms and not cited_broad:
        note += (" Broad headings (" + ", ".join(broad_user_terms) + ") include the cited goods; "
                 "a narrower list of what you actually sell may help.")
    return ClassOverlap(user_class=class_number, cited_class=class_number, level=GoodsLevel.SAME,
                        overlapping_terms=overlapping, narrowing_helps=helps, note=note)
