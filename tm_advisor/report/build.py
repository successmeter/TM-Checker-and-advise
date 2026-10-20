"""Turn a completed check into the paid report (design: docs/paid-report-design.md §4).

The report sets out evidence, the relevant law, what remains uncertain and further research paths. It doesn't
recommend what to file. The check decides every review priority and conflict; Claude only writes the narrative
(summary, what each finding means) from those findings, with the Trade Marks Manual excerpts it was given; if Claude
isn't available the report is still complete, with plainer wording.
"""

import logging
from collections.abc import Callable

from ..explain import Explainer, Explanation, ExplanationUnavailable, retrieve
from ..manual import ManualIndex
from ..models import Application, ClassOverlap, Conflict, GoodsLevel, Report, Risk, TermMatch
from ..picklist import ClassInfo
from .schema import (Citation, DistinctivenessSection, Filing, FormatNote, ReportDoc, SimilarMark, SpecClass,
                     SpecTerm)
from .validate import checked, problems

log = logging.getLogger("uvicorn.error")

MAX_MARKS = 40
EXPLAIN_MARKS = 8
REPORT_EFFORT = "high"

DESIGN_GUIDANCE = [
    "Examiners consider whether a design element is substantial and distinctive in its own right; a stylised font, "
    "colour or simple shape around the words usually adds little.",
    "A small symbol beside prominent words usually leaves the words as the main feature of the mark.",
    "Pictures of the goods or services themselves (a coffee cup for a cafe, a chart for analytics) add descriptive "
    "meaning rather than distinctiveness.",
    "A registration covers the mark as filed: that combination of design and words.",
]

LIMITATIONS = [
    "This report provides automated research and decision-support information based on publicly available Australian "
    "trade mark data and IP Australia materials. It does not provide legal advice, a legal opinion, or a "
    "determination of whether a trade mark is registrable or infringes another person's rights. Results are "
    "indicative only and may be incomplete or inaccurate. For advice on your circumstances, consult a registered "
    "Australian trade marks attorney or lawyer.",
    "This report is produced by software. It is not a clearance search for "
    "using the brand, and BizImprint does not file applications for you.",
    "It is based on the register on the date above; marks filed later, or not yet published, are not included.",
    "Examiners decide each case on its facts, and other traders can oppose an application; no outcome is guaranteed.",
]

ADVERSE_HEADSTART = [
    "5 working days to amend the request (changing the mark itself needs a new representation and an extra fee).",
    "Paying Part 2 and responding to the formal examination report within 15 months, with amendments, arguments or "
    "evidence of use.",
    "Withdrawing, and starting again with a different mark.",
]

KIND_STEP = {
    "word": "A TM Headstart request for a word mark sets out the words exactly, and the goods and services (section 4).",
    "composite": "A TM Headstart request for a mark with a design includes an image of the mark, the words in it, and "
                 "the goods and services (section 4).",
    "logo": "A TM Headstart request for a mark with a design includes an image of the mark, and the goods and "
            "services (section 4).",
}


def build_report(application: Application, report: Report, *, classes: dict[int, ClassInfo], reference: str,
                 created: str, register_searched: str, sources: list[str], explainer: Explainer | None = None,
                 manual: ManualIndex | None = None, logo_image: str | None = None, industry: str = "",
                 sample: bool = False) -> ReportDoc:
    explanation = checked(_explain(report, explainer, manual), report)
    by_number = {c.cited_number: c.explanation for c in explanation.conflicts} if explanation else {}
    cited_by_number = {c.cited_number: c.citations for c in explanation.conflicts} if explanation else {}

    marks = [_similar(c, by_number.get(c.cited_number)).model_copy(
        update={"citations": _unique_citations(cited_by_number.get(c.cited_number, []))[:2]})
        for c in _relevant(report.conflicts)]
    attention = [m for m in marks if m.live and m.risk != Risk.LOW]
    summary = explanation.overview if explanation and explanation.overview else _plain_summary(report, len(attention))
    open_from_narrative = explanation.next_steps if explanation else []

    return ReportDoc(
        reference=reference, created=created, register_searched=register_searched, sources=sources, sample=sample,
        prepared_for=application.applicant, mark=application.mark, mark_kind=application.mark_kind,
        logo_image=logo_image, classes=[c.class_number for c in application.classes],
        overall_risk=report.overall_risk, summary=summary,
        key_findings=_key_findings(report, attention),
        format_notes=_format_notes(report, application, attention),
        uncertainties=_uncertainties(report, application, attention, open_from_narrative),
        research_paths=_research_paths(report, application, attention),
        distinctiveness=_distinctiveness(report, explanation, manual),
        similar_marks=marks,
        similar_citations=_guidance(manual, SIMILAR_QUERY, [c for e in (explanation.conflicts if explanation else [])
                                                           for c in e.citations]),
        marks_reviewed=report.marks_screened, own_marks_note=_own_note(report),
        specification=_specification(application, report, classes),
        specification_notes=_spec_notes(industry),
        design_guidance=DESIGN_GUIDANCE if _descriptive(report) or application.mark_kind != "word" else [],
        filing=_filing(application, report),
        attorney_reasons=report.escalation_reasons,
        limitations=LIMITATIONS,
    )


def _descriptive(report: Report) -> bool:
    ai = report.ai_distinctiveness
    return report.wholly_descriptive or bool(ai and ai.likelihood != "unlikely") or bool(report.distinctiveness)


def _key_findings(report: Report, attention: list[SimilarMark]) -> list[str]:
    ai = report.ai_distinctiveness
    if ai and ai.likelihood != "unlikely":
        distinct = (f"Distinctiveness (section 41): read as a whole, the mark {'is likely to' if ai.likelihood == 'likely' else 'may'} "
                    "be seen as describing your goods or services (section 2).")
    elif report.distinctiveness:
        distinct = ("Distinctiveness (section 41): some words describe or praise your goods or services; others may "
                    "carry the mark (section 2).")
    else:
        distinct = "Distinctiveness (section 41): no descriptive, praising or place-name meaning was identified (section 2)."
    names = ", ".join(f"{m.words} ({m.number})" for m in attention[:3]) + (" and others" if len(attention) > 3 else "")
    similar = (f"Earlier marks (section 44): {len(attention)} of the {report.marks_screened} marks screened "
               f"{'were' if len(attention) != 1 else 'was'} given a medium or high review priority: {names} (section 3)."
               if attention else f"Earlier marks (section 44): none of the {report.marks_screened} marks screened was "
                                 "given a medium or high review priority (section 3).")
    off = sum(1 for p in report.picklist if not p.on_picklist)
    goods = ("Goods and services: every term is on IP Australia's picklist (section 4)." if not off else
             f"Goods and services: {off} term{'s are' if off != 1 else ' is'} not on IP Australia's picklist (section 4).")
    return [distinct, similar, goods]


def _format_notes(report: Report, application: Application, attention: list[SimilarMark]) -> list[FormatNote]:
    descriptive = _descriptive(report)
    n = len(attention)
    marks = f"the {n} earlier mark{'s' if n != 1 else ''} in section 3"
    word = ("The distinctiveness finding applies directly: the words are assessed on their own. " if descriptive else "")
    word += (f"Your words would be compared with {marks}." if n else "No earlier mark was given a medium or high review "
             "priority for the words.")
    composite = ("Examiners consider whether a substantial, distinctive design gives the mark as a whole the "
                 "distinctiveness the words lack; the words on their own stay unprotected. " if descriptive else "")
    composite += (f"Against {marks}, the words are often the main feature compared; how far a design changes the "
                  "overall impression depends on the design and on those marks." if n else
                  "The registration would cover only that combination of design and words.")
    return [
        FormatNote(kind="Word mark", protects="The words themselves, independent of font or styling. Not a logo design.",
                   findings=word),
        FormatNote(kind="Composite mark (design and words)", protects="One particular combination of design and words.",
                   findings=composite),
        FormatNote(kind="Logo mark", protects="The design only. Your name is not protected.",
                   findings="This report compares words, not designs: IP Australia's image search covers similar logos."),
    ]


def _bases(report: Report) -> set[str]:
    return {m.basis for c in report.conflicts if c.live and c.risk != Risk.LOW for o in c.overlaps for m in o.matches}


def _uncertainties(report: Report, application: Application, attention: list[SimilarMark],
                   from_narrative: list[str]) -> list[str]:
    out = ["Review priorities are screening signals from an automated search, not predictions. Examiners assess each "
           "application as a whole and on its own facts, and other traders can oppose."]
    bases = _bases(report)
    if "shared_words" in bases:
        out.append("Some links between goods and services rest on shared wording in the specifications. Whether the "
                   "goods or services are actually similar depends on their purpose, users and trade channels, which "
                   "the register wording doesn't show.")
    if "related_class" in bases:
        out.append("Some links are between different classes that are often treated as related; whether they are "
                   "closely related here is decided case by case.")
    if any(_pending(m.status) for m in attention):
        out.append("Some earlier marks are not yet registered: they may still be amended, opposed or withdrawn.")
    ai = report.ai_distinctiveness
    if ai and ai.likelihood != "unlikely":
        out.append("The distinctiveness assessment is an automated reading of what the words mean for your goods and "
                   "services. It doesn't take account of any use you have made of the mark, which can be relevant.")
    out.append("The register doesn't show whether or how owners use their marks, and unregistered use by others isn't "
               "covered by this search.")
    out.append("Logos and other designs were not compared; only words. Marks filed very recently may not be searchable yet.")
    for q in from_narrative:
        if q not in out:
            out.append(q)
    return out[:8]


def _pending(status: str) -> bool:
    s = status.lower()
    return not (s.startswith("registered") or s.startswith("protected")) and "never" not in s and "removed" not in s


def _research_paths(report: Report, application: Application, attention: list[SimilarMark]) -> list[str]:
    paths = []
    if attention:
        paths.append("The full register records of the marks in section 3 (linked), including every class, the full "
                     "goods and services, status history and owner.")
    paths.append("Unregistered use of similar names: ASIC's business names register, ABN Lookup, domain names and a "
                 "general web search.")
    if application.mark_kind != "word" or any(m.logo for m in attention):
        paths.append("IP Australia's trade mark image search, for similar logos and designs.")
    paths.append("IP Australia's TM Headstart: an examiner's preliminary assessment of your application, usually "
                 "within about 5 business days, before a full application (fees in section 6).")
    attorney = "A registered trade marks attorney or lawyer, for advice on your circumstances"
    if attention or report.escalation_reasons:
        attorney += (": because potentially relevant earlier registrations were identified, professional review may "
                     "be useful before committing to an application or adopting the brand")
    paths.append(attorney + ".")
    return paths


def _explain(report: Report, explainer: Explainer | None, manual: ManualIndex | None) -> Explanation | None:
    if explainer is None:
        return None
    try:
        excerpts = retrieve(report, manual) if manual is not None else []
        # Only the marks that matter: hundreds of screened marks would make the answer too long to finish.
        focus = [c for c in _relevant(report.conflicts) if c.live and c.risk != Risk.LOW][:EXPLAIN_MARKS]
        return explainer.explain(report.model_copy(update={"conflicts": focus}), excerpts, effort=REPORT_EFFORT)
    except ExplanationUnavailable as e:
        log.warning("Report narrative unavailable, using plain wording: %s", e)
        return None


def _unique_citations(cited) -> list[Citation]:
    """One line per Manual section; no heading when it just repeats the page title."""
    out: dict[tuple[str, str], Citation] = {}
    for c in cited:
        heading = "" if c.heading.strip() == c.title.strip() else c.heading
        out.setdefault((c.title, heading), Citation(title=c.title, heading=heading, url=c.url, published=c.published))
    return list(out.values())


def _relevant(conflicts: list[Conflict]) -> list[Conflict]:
    order = {Risk.HIGH: 0, Risk.MEDIUM: 1, Risk.LOW: 2}
    return sorted(conflicts, key=lambda c: (not c.live, order[c.risk], -c.mark_score))[:MAX_MARKS]


def _similar(c: Conflict, explained: str | None) -> SimilarMark:
    overlap = " ".join(
        f"Your class {o.user_class} vs their class {o.cited_class}: {o.note}"
        + (f" Overlapping: {', '.join(o.overlapping_terms)}." if o.overlapping_terms else "")
        for o in c.overlaps)
    return SimilarMark(number=c.cited_number, words=c.cited_words or "(no words)", logo=c.cited_logo,
                       image=c.cited_image, status=c.cited_status, owner=c.cited_owner,
                       classes=sorted({o.cited_class for o in c.overlaps}), live=c.live, risk=c.risk,
                       why_similar=c.mark_reasons, goods_overlap=overlap or "No overlapping goods or services.",
                       goods_points=[p for o in c.overlaps for p in _goods_points(o)],
                       what_to_do=explained or "", open_questions=_open_questions(c))


def _open_questions(c: Conflict) -> list[str]:
    bases = {m.basis for o in c.overlaps for m in o.matches}
    out = []
    if not c.live:
        out.append("No longer in force: marks like this are generally not cited against new applications, but the "
                   "owner may still be using the name.")
    if "shared_words" in bases:
        out.append("Are their goods or services actually like yours in purpose, users and trade channels? The "
                   "specifications share wording only.")
    if bases & {"identical", "broad_heading"}:
        out.append("Their specification uses the same or broader wording, so the goods or services overlap on the "
                   "register itself.")
    if "related_class" in bases:
        out.append("Different classes: would consumers expect these goods and services to come from the same business?")
    if c.live and _pending(c.cited_status):
        out.append("Not yet registered: it may still be amended, opposed or withdrawn.")
    if "renewal" in c.cited_status.lower():
        out.append("Renewal is due or overdue: the registration may lapse if it isn't renewed.")
    if c.cited_logo:
        out.append("It includes a design, which this report doesn't compare: only the words were compared.")
    if c.live:
        out.append("Is the mark in use, and how? The register doesn't say.")
    return out[:4]


def _short(term: str, n: int = 110) -> str:
    return term if len(term) <= n else term[:n].rsplit(" ", 1)[0] + "…"


def _match_text(m: TermMatch, o: ClassOverlap) -> str:
    ours, theirs = f"“{_short(m.user_term)}”", f"“{_short(m.cited_term)}”"
    if m.basis == "identical":
        return f"Identical wording: your {ours} also appears in their class {o.cited_class} specification."
    if m.basis == "broad_heading":
        return (f"Broad term: their class {o.cited_class} specification includes {theirs}, which can cover your "
                f"{ours}." if m.cited_term != m.user_term else f"Broad term: {ours}.")
    if m.basis == "shared_words":
        shared = ", ".join(f"“{w}”" for w in m.shared_words)
        return (f"Shared wording: your {ours} and their {theirs} both use {shared}. Shared words alone don't make the "
                "services similar; that depends on what each is for, who uses it and how it is sold.")
    return (f"Related classes: your class {o.user_class} {ours} and their class {o.cited_class} {theirs}. "
            f"{o.note.split(' Their goods')[0]}")


def _goods_points(o: ClassOverlap) -> list[str]:
    if not o.matches:
        return [f"Class {o.cited_class}: {o.note}"]
    points = [_match_text(m, o) for m in o.matches[:3]]
    if len(o.matches) > 3:
        points.append(f"…and {len(o.matches) - 3} more of your class {o.user_class} terms.")
    return points


def _own_note(report: Report) -> str:
    if report.own_marks_assumed:
        nums = ", ".join(f"#{n}" for n in report.own_marks_assumed)
        return (f"Left out as your own: {nums}, the same mark owned by a business named after it. If it isn't yours, "
                "it is an identical earlier mark and changes this report: run the check again with your name or "
                "company, and contact us for a free re-check.")
    if report.own_marks:
        return "Left out as your own: " + ", ".join(f"#{n}" for n in report.own_marks) + "."
    return ""


def _plain_summary(report: Report, attention: int) -> str:
    parts = [f"Overall review priority: {report.overall_risk.value}. This is a guide to where to look first, not a "
             "prediction."]
    ai = report.ai_distinctiveness
    if ai and ai.likelihood != "unlikely":
        parts.append(f"The mark as a whole is {'likely' if ai.likelihood == 'likely' else 'possibly'} going to be "
                     "seen as describing your goods or services.")
    elif report.distinctiveness:
        parts.append("Some words in the mark describe or praise your goods or services.")
    parts.append(f"{attention} similar mark{'s' if attention != 1 else ''} on the register deserve{'s' if attention == 1 else ''} "
                 "a closer look." if attention else "No similar mark on the register was flagged for a closer look.")
    return " ".join(parts)


SIMILAR_QUERY = "section 44 substantially identical deceptively similar trade marks similar goods closely related services"
DISTINCT_QUERY = "section 41 trade mark capable of distinguishing inherently adapted ordinary signification descriptive"


def _guidance(manual: ManualIndex | None, query: str, cited: list, limit: int = 3) -> list[Citation]:
    """Trade Marks Manual sections for a finding: those the explanation cited, then the closest matches to the
    legal test, so every finding links to IP Australia's own guidance even without the AI narrative."""
    found = list(cited)
    if manual is not None:
        try:
            found += manual.search(query, limit)
        except Exception as e:  # an old or damaged index: the report still works without it
            log.warning("Manual search failed: %s", e)
    return _unique_citations(found)[:limit]


def _distinctiveness(report: Report, explanation: Explanation | None,
                     manual: ManualIndex | None = None) -> DistinctivenessSection:
    flags = [f"{f.word.upper()}: {f.reason}" for f in report.distinctiveness]
    citations = _guidance(manual, DISTINCT_QUERY, explanation.distinctiveness.citations
                          if explanation and explanation.distinctiveness else [])
    ai = report.ai_distinctiveness
    if ai:
        reasoning = ai.reasoning if not problems(ai.reasoning, report) else (
            "Read as a whole, the mark " + {"likely": "is likely to", "possible": "may", "unlikely": "is not expected to"}[
                ai.likelihood] + " be seen as describing your goods or services.")
        return DistinctivenessSection(likelihood=ai.likelihood, meaning=ai.meaning, reasoning=reasoning,
                                      affected_terms=ai.affected_terms, word_flags=flags,
                                      options=[o for o in ai.options if not problems(o, report)], citations=citations)
    likelihood = "likely" if report.wholly_descriptive else "possible" if flags else "unlikely"
    reasoning = (explanation.distinctiveness.explanation if explanation and explanation.distinctiveness else
                 "Every word in the mark describes or praises your goods or services." if report.wholly_descriptive
                 else "Some words in the mark describe or praise your goods or services; the rest may carry the mark."
                 if flags else "No descriptive, praising or place-name words were found.")
    options = [] if likelihood == "unlikely" else [
        "Some applicants add or substitute an invented or unusual word.",
        "Some file a composite mark, where a substantial, distinctive design can give the mark as a whole its "
        "distinctiveness (section 1).",
        "Where a mark has been used for some time, evidence of that use can be relevant."]
    return DistinctivenessSection(likelihood=likelihood, reasoning=reasoning, word_flags=flags, options=options,
                                  citations=citations)


def _specification(application: Application, report: Report, classes: dict[int, ClassInfo]) -> list[SpecClass]:
    picklist = {(p.class_number, p.term): p for p in report.picklist}
    narrowable: dict[tuple[int, str], str] = {}
    for c in report.conflicts:
        if not c.live or c.risk == Risk.LOW:
            continue
        for o in c.overlaps:
            if o.level == GoodsLevel.SAME and o.narrowing_helps:
                for term in o.overlapping_terms:
                    narrowable.setdefault((o.user_class, term), c.cited_words)
    narrow_route = report.route is not None and report.route.recommended == "narrow_goods"

    out = []
    for spec in application.classes:
        kept, removed = [], []
        for term in spec.terms:
            p = picklist.get((spec.class_number, term))
            on = p.on_picklist if p else True
            note = "" if on else ("Not on the picklist (A$400 per class instead of A$250)."
                                  + (f" Closest picklist wording: {'; '.join(p.suggestions)}." if p and p.suggestions else ""))
            other = narrowable.get((spec.class_number, term))
            if other and narrow_route:
                removed.append(SpecTerm(text=term, on_picklist=on,
                                        note=f"Overlaps {other}. Do you offer it? If not, you may not need it."))
            else:
                if other:
                    note = (note + f" Overlaps {other}. Do you offer it? If not, you may not need it.").strip()
                kept.append(SpecTerm(text=term, on_picklist=on, note=note))
        title = classes[spec.class_number].title if spec.class_number in classes else ""
        out.append(SpecClass(class_number=spec.class_number, title=title, terms=kept, removed=removed))
    return out


def _spec_notes(industry: str) -> list[str]:
    notes = ["An application claims goods and services the applicant uses or intends to use. Terms that are never used "
             "can later be removed for non-use, and each term claimed is a term that can overlap other marks."]
    area = industry.strip().removeprefix("for ").removeprefix("the ").strip()
    if area:
        notes.append(f"Your industry or customers: “{industry.strip()}”. Where another mark's goods are for a "
                     f"different purpose, the Trade Marks Manual (Part 27.3) describes limitations such as “…; all for "
                     f"use in {area}”, which can affect an overlap. They don't affect a mark that covers the broad term.")
    return notes


def _filing(application: Application, report: Report) -> Filing:
    n = len(application.classes)
    all_picklist = report.picklist_only
    return Filing(classes=n, headstart_part1=200 * n, headstart_part2=130 * n, standard=(250 if all_picklist else 400) * n,
                  all_picklist=all_picklist,
                  steps=["Requests and applications are made online, through an IP Australia online services account "
                         "(portal.ipaustralia.gov.au).",
                         KIND_STEP[application.mark_kind],
                         "Once Part 1 is paid, an examiner's assessment usually arrives within about 5 business days.",
                         "Paying Part 2 turns the request into an application; that date becomes the filing date.",
                         "The application is then examined; an examination report, if issued, sets a deadline to "
                         "respond."],
                  adverse_headstart=ADVERSE_HEADSTART)


def make_report(application: Application, check: Callable[[Application], Report], **kwargs) -> ReportDoc:
    """Run the check and build the report in one go (used by the report worker)."""
    return build_report(application, check(application), **kwargs)
