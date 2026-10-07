"""Runs every check for an application and builds the report."""

from . import distinctiveness, goods_similarity
from .mark_similarity import compare
from .models import (Application, ClassOverlap, Conflict, GoodsLevel, PicklistResult, RegisterMark, Report, Risk)
from .picklist import Picklist
from .register import RegisterClient

MIN_MARK_SCORE = 0.5

DISCLAIMERS = [
    "TM Advisor is software, not a law firm or a trade marks attorney, and this report is not legal advice.",
    "Results are an automated screen of public IP Australia data. They can miss marks and cannot predict an "
    "examiner's decision. Registration is not guaranteed.",
    "You choose the wording of your application and file it yourself. Changing your goods and services changes "
    "what your registration would protect.",
    "This is not a clearance search for using the brand. For that, or for any High risk result, speak to a "
    "registered trade marks attorney.",
]

LOGO_DISTINCTIVENESS_NOTE = (
    "Filing as a logo: a distinctive design can help a descriptive word get accepted, but the registration then "
    "protects the logo as a whole. Other traders may still be able to use the words on their own.")
LOGO_SIMILARITY_NOTE = (
    "Filing as a logo rarely avoids a similarity objection: examiners compare the main feature of each mark, "
    "which is usually the words.")

_RISK_ORDER = {Risk.LOW: 0, Risk.MEDIUM: 1, Risk.HIGH: 2}


def check(application: Application, register: RegisterClient, picklist: Picklist) -> Report:
    class_numbers = [c.class_number for c in application.classes]
    conflicts = [c for m in register.search(application.mark, class_numbers) if (c := _conflict(application, m))]
    conflicts.sort(key=lambda c: (not c.live, -_RISK_ORDER[c.risk], -c.mark_score))

    picklist_results = [
        PicklistResult(
            class_number=spec.class_number,
            term=term,
            on_picklist=(on := picklist.match(spec.class_number, term) is not None),
            suggestions=[] if on else picklist.suggest(spec.class_number, term),
        )
        for spec in application.classes
        for term in spec.terms
    ]

    all_terms = [t for spec in application.classes for t in spec.terms]
    flags, wholly_descriptive = distinctiveness.screen(application.mark, all_terms)

    logo = application.mark_kind == "logo"
    notes: list[str] = []
    overall = max((c.risk for c in conflicts if c.live), key=_RISK_ORDER.get, default=Risk.LOW)
    if wholly_descriptive:
        overall = max(overall, Risk.MEDIUM if logo else Risk.HIGH, key=_RISK_ORDER.get)
    if logo and flags:
        notes.append(LOGO_DISTINCTIVENESS_NOTE)
    if logo and conflicts:
        notes.append(LOGO_SIMILARITY_NOTE)

    reasons = _escalation_reasons(conflicts, wholly_descriptive and not logo)
    return Report(
        mark=application.mark,
        mark_kind=application.mark_kind,
        notes=notes,
        overall_risk=overall,
        conflicts=conflicts,
        picklist=picklist_results,
        picklist_only=all(p.on_picklist for p in picklist_results),
        distinctiveness=flags,
        escalate=bool(reasons),
        escalation_reasons=reasons,
        disclaimers=DISCLAIMERS,
    )


def _conflict(application: Application, cited: RegisterMark) -> Conflict | None:
    similarity = compare(application.mark, cited.words)
    if similarity.score < MIN_MARK_SCORE:
        return None

    overlaps: list[ClassOverlap] = []
    for spec in application.classes:
        for cited_class in cited.classes:
            overlap = goods_similarity.relate(spec.class_number, spec.terms, cited_class.class_number, cited_class.terms)
            if overlap.level != GoodsLevel.NONE:
                overlaps.append(overlap)
    if not overlaps:
        return None

    has_same = any(o.level == GoodsLevel.SAME for o in overlaps)
    if not cited.is_live:
        risk = Risk.LOW
    elif similarity.score >= 0.85 and has_same:
        risk = Risk.HIGH
    elif similarity.score >= 0.85 or (similarity.score >= 0.7 and has_same):
        risk = Risk.MEDIUM
    else:
        risk = Risk.LOW

    return Conflict(
        cited_number=cited.number,
        cited_words=cited.words,
        cited_status=cited.status,
        cited_owner=cited.owner,
        live=cited.is_live,
        risk=risk,
        mark_score=similarity.score,
        mark_reasons=similarity.reasons,
        overlaps=overlaps,
        option=_option(cited, overlaps),
    )


RENEWAL_NOTE = (" Its registration has expired but can still be renewed for a limited time. If the owner doesn't "
                "renew, it will be removed and stop blocking you; filing after that is one option.")


def _option(cited: RegisterMark, overlaps: list[ClassOverlap]) -> str:
    text = _base_option(cited, overlaps)
    if cited.is_live and "renewal possible" in cited.status.lower():
        text += RENEWAL_NOTE
    return text


def _base_option(cited: RegisterMark, overlaps: list[ClassOverlap]) -> str:
    if not cited.is_live:
        return (f"Not live ({cited.status}), so it should not be cited against your application. The owner may "
                "still be using the name, so check before you launch.")
    same = [o for o in overlaps if o.level == GoodsLevel.SAME]
    if same and all(o.narrowing_helps for o in same):
        terms = sorted({t for o in same for t in o.overlapping_terms})
        return ("If you don't actually sell " + ", ".join(terms) + ", leaving them out removes the direct overlap "
                "with this mark. Related goods can still draw an objection.")
    if same:
        return ("Leaving out terms is unlikely to remove this overlap. Options to weigh: a more distinctive mark, "
                "or a registered trade marks attorney's view on arguments such as different trade channels or "
                "honest concurrent use.")
    return ("Your goods/services are related rather than the same. An examiner may still object; how close the "
            "marks are matters most.")


def _escalation_reasons(conflicts: list[Conflict], wholly_descriptive: bool) -> list[str]:
    reasons: list[str] = []
    for c in conflicts:
        if not c.live or c.risk != Risk.HIGH:
            continue
        if c.mark_score >= 0.97:
            reasons.append(f"An identical or near-identical mark ({c.cited_words}, {c.cited_number}) already covers "
                           "the same goods/services.")
        elif not all(o.narrowing_helps for o in c.overlaps if o.level == GoodsLevel.SAME):
            reasons.append(f"The overlap with {c.cited_words} ({c.cited_number}) can't be removed by narrowing "
                           "your goods/services.")
    if wholly_descriptive:
        reasons.append("Every word in the mark describes or praises the goods/services, a likely section 41 "
                       "objection that usually needs a new mark or evidence of use.")
    return reasons
