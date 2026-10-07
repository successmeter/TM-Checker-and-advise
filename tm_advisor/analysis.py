"""Runs every check for an application and builds the report."""

from . import distinctiveness, goods_similarity
from .mark_similarity import compare
from .models import (AiDistinctiveness, Application, ClassOverlap, Conflict, GoodsLevel, PicklistResult, RegisterMark,
                     Report, Risk, Route)
from .picklist import Picklist
from .text import normalise
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
    "Filing as a composite mark (design plus words): a substantial, distinctive design can help descriptive words "
    "get accepted, but the registration then protects the combination as a whole. Other traders may still be able "
    "to use the words on their own.")
LOGO_SIMILARITY_NOTE = (
    "A composite mark rarely avoids a similarity objection: examiners compare the main feature of each mark, "
    "which is usually the words.")
LOGO_ONLY_NOTE = (
    "Logo only (no words): pictures can't be compared automatically, so no register search was run. Search IP "
    "Australia's image search (Australian Trade Mark Search, by image description) before filing. A logo-only "
    "registration protects the picture, not your name: consider registering the name as a word mark too.")

_RISK_ORDER = {Risk.LOW: 0, Risk.MEDIUM: 1, Risk.HIGH: 2}


def check(application: Application, register: RegisterClient, picklist: Picklist) -> Report:
    class_numbers = [c.class_number for c in application.classes]
    logo_only = application.mark_kind == "logo"
    found = [] if logo_only else register.search(application.mark, class_numbers)
    own = [m.number for m in found if application.applicant and same_owner(application.applicant, m.owner)]
    conflicts = [c for m in found if m.number not in own and (c := _conflict(application, m))]
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
    flags, wholly_descriptive = ([], False) if logo_only else distinctiveness.screen(application.mark, all_terms)

    logo = application.mark_kind in ("composite", "logo")  # has a design element
    notes: list[str] = [LOGO_ONLY_NOTE] if logo_only else []
    overall = max((c.risk for c in conflicts if c.live), key=_RISK_ORDER.get, default=Risk.LOW)
    if wholly_descriptive:
        overall = max(overall, Risk.MEDIUM if logo else Risk.HIGH, key=_RISK_ORDER.get)
    if logo and flags:
        notes.append(LOGO_DISTINCTIVENESS_NOTE)
    if logo and conflicts:
        notes.append(LOGO_SIMILARITY_NOTE)

    reasons = _escalation_reasons(conflicts, wholly_descriptive and not logo)
    report = Report(
        mark=application.mark,
        mark_kind=application.mark_kind,
        notes=notes,
        own_marks=own,
        overall_risk=overall,
        conflicts=conflicts,
        picklist=picklist_results,
        picklist_only=all(p.on_picklist for p in picklist_results),
        distinctiveness=flags,
        wholly_descriptive=wholly_descriptive,
        escalate=bool(reasons),
        escalation_reasons=reasons,
        disclaimers=DISCLAIMERS,
    )
    return report.model_copy(update={"route": recommend_route(report)})


def _conflict(application: Application, cited: RegisterMark) -> Conflict | None:
    """A Conflict when the marks are alike and the goods or services are the same or related."""
    similarity = compare(application.mark, cited.words)
    if similarity.score < MIN_MARK_SCORE:
        return None

    overlaps: list[ClassOverlap] = []
    for spec in application.classes:
        for cited_class in cited.classes:
            overlap = goods_similarity.relate(spec.class_number, spec.terms, cited_class.class_number, cited_class.terms)
            if overlap.level != GoodsLevel.NONE:
                overlaps.append(overlap)
    if not overlaps:  # unrelated goods and services: not a conflict
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
        cited_image=cited.image,
        cited_logo=cited.logo,
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


def with_ai_distinctiveness(report: Report, ai: AiDistinctiveness) -> Report:
    """Add the AI section 41 view: a likely objection is High risk (Medium for a logo), a possible one Medium."""
    logo = report.mark_kind in ("composite", "logo")
    level = {"likely": Risk.MEDIUM if logo else Risk.HIGH, "possible": Risk.MEDIUM}.get(ai.likelihood, Risk.LOW)
    overall = max(report.overall_risk, level, key=_RISK_ORDER.get)
    reasons = list(report.escalation_reasons)
    if ai.likelihood == "likely" and not logo:
        reasons.append("The mark as a whole is likely to be seen as describing your goods/services (section 41). "
                       "That usually needs a changed mark, or arguments and evidence of use that an attorney can "
                       "help prepare.")
    updated = report.model_copy(update={"ai_distinctiveness": ai, "overall_risk": overall,
                                        "escalate": bool(reasons), "escalation_reasons": reasons})
    return updated.model_copy(update={"route": recommend_route(updated)})


def recommend_route(report: Report) -> Route:
    """Word mark, composite mark, a new name, or narrower goods, depending on the kind of problem found.

    A design helps when the words are descriptive (section 41), because a distinctive design can carry the mark.
    It does not help against an earlier similar mark (section 44): examiners compare the main feature, usually the
    words, so a logo with a taken name is usually refused too.
    """
    if report.mark_kind == "logo":
        return Route(recommended="logo", headline="Logo only: protects the picture, not your name",
                     reasons=["Check the picture against IP Australia's image search before filing.",
                              "If your name matters to your brand, a word mark (or composite mark) protects it."])

    blocking = [c for c in report.conflicts if c.live and c.risk == Risk.HIGH]
    ai = report.ai_distinctiveness
    descriptive = report.wholly_descriptive or bool(ai and ai.likelihood == "likely")
    possibly_descriptive = bool(report.distinctiveness) or bool(ai and ai.likelihood == "possible")

    if blocking:
        names = ", ".join(f"{c.cited_words} ({c.cited_number})" for c in blocking[:3])
        if all(all(o.narrowing_helps for o in c.overlaps if o.level.value == "same") for c in blocking):
            return Route(recommended="narrow_goods", headline="Leave out the overlapping goods or services",
                         reasons=[f"Similar earlier marks: {names}.",
                                  "Dropping the goods/services you don't actually offer removes the direct overlap.",
                                  "Adding a logo would not help: examiners compare the words."])
        return Route(recommended="new_name", headline="Consider a different name",
                     reasons=[f"Similar earlier marks cover the same goods/services: {names}.",
                              "A composite mark (logo plus these words) is unlikely to get around them: examiners "
                              "compare the main feature of each mark, which is usually the words.",
                              "If you are attached to the name, a registered trade marks attorney can assess "
                              "arguments such as different trade channels or honest concurrent use."])
    if descriptive:
        reasons = ["Your words are likely to be seen as describing your goods/services (section 41), so a word mark "
                   "is likely to be refused.",
                   "A composite mark with a substantial, distinctive design has a much better chance: the design "
                   "gives the mark its distinctiveness.",
                   "It protects the logo and words together, not the words on their own, so others may still use "
                   "the words descriptively."]
        if report.mark_kind == "word":
            reasons.append("To change a TM Headstart request from a word mark to a composite mark, you send a new "
                           "representation of the mark (an extra fee applies).")
        return Route(recommended="composite", headline="File as a composite mark (logo plus words)", reasons=reasons)
    reasons = ["No major problems found with the words.",
               "A word mark protects the words in any style, font or logo, so it is the broadest protection.",
               "You can register your logo as a composite mark later if you want to protect the design too."]
    if possibly_descriptive:
        reasons.insert(1, "Some words may be seen as descriptive. If a word mark draws an objection, a composite "
                          "mark with a distinctive design is the fallback.")
    return Route(recommended="word", headline="File as a word mark", reasons=reasons)


_OWNER_NOISE = {"pty", "ltd", "limited", "proprietary", "inc", "incorporated", "llc", "co", "company", "corp",
                "corporation", "the", "trustee", "for", "trust", "as", "atf", "and"}


def _owner_key(name: str) -> str:
    return " ".join(w for w in normalise(name).split() if w not in _OWNER_NOISE)


def same_owner(applicant: str, owners: str | None) -> bool:
    """Whether the applicant is one of a mark's owners (ignoring Pty Ltd, punctuation and case)."""
    wanted = _owner_key(applicant)
    return bool(wanted) and any(_owner_key(o) == wanted for o in (owners or "").split(", "))
