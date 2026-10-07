"""A sample report (SUCCESS METER) to design and preview the paid report.

  py -m tm_advisor.report.sample                 writes data/sample_report.pdf and data/sample_report.html

The similar marks are real entries from the register (number, status and classes as at October 2026); everything
else is illustrative. The page carries a "Sample report" banner.
"""

import sys
from pathlib import Path

from ..models import Risk, Route
from .render import render_html, render_pdf
from .schema import DistinctivenessSection, Filing, ReportDoc, SimilarMark, SpecClass, SpecTerm

ROOT = Path(__file__).resolve().parents[2]

GOODS_NOTE = "Both cover class {c}. Their exact goods and services are compared term by term in a real report."


def sample_report() -> ReportDoc:
    return ReportDoc(
        reference="TA-SAMPLE-0001", created="7 October 2026", sample=True,
        prepared_for="Example Pty Ltd",
        register_searched="7 October 2026, 10:42 AEDT",
        sources=["Australian Trade Mark Search API (IP Australia), production register, searched 7 October 2026.",
                 "IP Australia goods and services picklist (tmgns.search.ipaustralia.gov.au), copied 6 October 2026.",
                 "IP Australia Trade Marks Manual of Practice and Procedure, downloaded 1 October 2026."],
        mark="SUCCESS METER", mark_kind="word", classes=[35, 42],
        overall_risk=Risk.HIGH,
        summary=("SUCCESS METER is likely to be refused as a word mark because, read as a whole, it describes what your "
                 "services do: measure business success. No earlier mark blocks you outright, but two marks that lead "
                 "with SUCCESS in class 35 need a closer look. Your best route is a composite mark: a distinctive "
                 "design together with the words, or a more distinctive name."),
        top_actions=[
            "Commission a logo with a substantial, distinctive design element (see section 6) and file SUCCESS METER "
            "as a composite mark, or choose a more distinctive word mark.",
            "Leave out website hosting and website design from class 42 unless you actually offer them (section 5).",
            "File through TM Headstart with the specification in section 5; you get the examiner's view within about "
            "5 business days and can amend before paying Part 2.",
        ],
        route=Route(recommended="composite", headline="File as a composite mark (logo plus words)",
                    reasons=["Your words are likely to be seen as describing your services (section 41), so a word "
                             "mark is likely to be refused.",
                             "A composite mark with a substantial, distinctive design has a much better chance: the "
                             "design gives the mark its distinctiveness.",
                             "It protects the logo and words together, not the words on their own, so others may still "
                             "use the words “success meter” descriptively."]),
        route_detail=[
            "The examiner's concern is the phrase, not an earlier trade mark. That is exactly the situation where a "
            "design helps: the design, not the words, makes the mark distinctive.",
            "If owning the words themselves matters to you, the alternative is a different name with an invented or "
            "unusual element, filed as a word mark. Run it through Trademark Advisor before you commit.",
            "Adding a logo would not help if the problem were an earlier similar mark; the similar marks in section 4 "
            "are rated Medium and Low, so they don't change this recommendation.",
        ],
        distinctiveness=DistinctivenessSection(
            likelihood="likely",
            meaning="A measure or standard used to judge whether a goal, project or strategy has been achieved.",
            reasoning=("Read as a whole, SUCCESS METER describes a tool or service that measures business success. "
                       "Business analysts, strategy consultants and software providers would naturally want to use "
                       "these words for what their services do, so an examiner is likely to find the mark not "
                       "capable of distinguishing your services. Joining the words or changing capitals does not "
                       "change that."),
            affected_terms=["business data analysis", "strategic business consultancy",
                            "benchmarking services for business management purposes", "software as a service [SaaS]"],
            word_flags=["SUCCESS: praises the outcome of the services (a word other traders use).",
                        "METER: describes measuring, which is what analysis and benchmarking services do."],
            options=["File as a composite mark with a substantial, distinctive design (section 6).",
                     "Change the name: add or substitute an invented or unusual word.",
                     "If you have used SUCCESS METER for some time, gather evidence of that use (sales, advertising, "
                     "customers) for the examiner."],
        ),
        marks_reviewed=238,
        similar_marks=[
            SimilarMark(number="2536546", words="SUCCESS+", status="Protected: Registered/protected", classes=[35, 41],
                        risk=Risk.MEDIUM,
                        why_similar=["Your mark starts with the whole of this mark (SUCCESS).",
                                     "Short marks that lead with the same word are compared closely."],
                        goods_overlap=GOODS_NOTE.format(c=35),
                        what_to_do=("Check its class 35 services on the linked record. If they are business "
                                    "consultancy or analysis, a distinctive design in a composite mark lowers the "
                                    "risk only a little; consider a more distinctive name.")),
            SimilarMark(number="2580382", words="SUCCESSCULTURE", status="Registered: Registered/protected",
                        classes=[35, 41], risk=Risk.MEDIUM,
                        why_similar=["Both marks begin with SUCCESS, which people tend to notice first."],
                        goods_overlap=GOODS_NOTE.format(c=35),
                        what_to_do="Usually manageable: the second word differs. Keep your class 35 terms specific."),
            SimilarMark(number="2451395", words="P PRACTICE SUCCESS", logo=True, status="Registered: Registered/protected",
                        classes=[35, 42], risk=Risk.LOW,
                        why_similar=["Shares the word SUCCESS, but the rest of the marks is different."],
                        goods_overlap=GOODS_NOTE.format(c="35 and 42"),
                        what_to_do="No action needed; listed so you know it exists."),
            SimilarMark(number="2390609", words="ODD METER", status="Protected: Registered/protected", classes=[42],
                        risk=Risk.LOW,
                        why_similar=["Shares the word METER, but the rest of the marks is different."],
                        goods_overlap=GOODS_NOTE.format(c=42),
                        what_to_do="No action needed."),
            SimilarMark(number="2248191", words="AUDOO METER", status="Protected: Registered/protected", classes=[9, 42],
                        risk=Risk.LOW,
                        why_similar=["Shares the word METER, but the rest of the marks is different."],
                        goods_overlap=GOODS_NOTE.format(c=42),
                        what_to_do="No action needed."),
            SimilarMark(number="2505432", words="METERMATE", status="Registered: Registered/protected", classes=[9, 42],
                        risk=Risk.LOW,
                        why_similar=["METER begins this mark, but the rest is different."],
                        goods_overlap=GOODS_NOTE.format(c=42),
                        what_to_do="No action needed."),
        ],
        specification=[
            SpecClass(class_number=35, title="Advertising, business management and administration", terms=[
                SpecTerm(text="business data analysis"),
                SpecTerm(text="strategic business consultancy"),
                SpecTerm(text="social media strategy and marketing consultancy"),
                SpecTerm(text="benchmarking services for business management purposes"),
            ]),
            SpecClass(class_number=42, title="Scientific, technology and software services", terms=[
                SpecTerm(text="software as a service [SaaS]", note="Covers your platform."),
            ], removed=[
                SpecTerm(text="hosting of websites", note="Leave out unless you host websites for others: unused terms "
                                                          "add conflict risk and can later be removed for non-use."),
                SpecTerm(text="design and development of homepages and websites",
                         note="Leave out unless you build websites for clients."),
            ]),
        ],
        specification_notes=[
            "Only claim what you offer or genuinely intend to offer. Fewer, specific terms mean fewer conflicts.",
            "If you narrow later, IP Australia's Trade Marks Manual (Part 27.3) explains how amendments and "
            "limitations are treated.",
        ],
        design_guidance=[
            "The design must be substantial and distinctive in its own right: a stylised font, colour or simple "
            "shape around the words is usually not enough.",
            "Make the design element prominent, not a small symbol beside large words.",
            "Avoid images of what your services are about (charts, gauges, upward arrows); they add descriptive "
            "meaning instead of distinctiveness.",
            "Use the logo exactly as filed. The registration protects that combination.",
        ],
        filing=Filing(
            classes=2, headstart_part1=400, headstart_part2=260, standard=500, all_picklist=True,
            steps=["Create an IP Australia online services account (portal.ipaustralia.gov.au).",
                   "Start a TM Headstart request: choose the kind of mark (composite: upload your logo), enter the "
                   "words in it, and paste your goods and services from section 5.",
                   "Pay Part 1. The examiner's assessment usually arrives within about 5 business days.",
                   "If the assessment is favourable, pay Part 2 to convert it into an application. That date is "
                   "your filing date.",
                   "Watch for the examination report and respond by its deadline."],
            adverse_headstart=["You have 5 working days to amend the request (changing the mark itself needs a new "
                               "representation and an extra fee).",
                               "Or pay Part 2 and respond to the formal examination report within 15 months, with "
                               "amendments, arguments or evidence of use.",
                               "Or start again with a different mark."]),
        attorney_reasons=[],
        limitations=[
            "This report is general information produced by software, not legal advice. It is not a clearance search "
            "for using the brand.",
            "It is based on the register on the date above; marks filed later, or not yet published, are not included.",
            "Examiners decide each case on its facts, and other traders can oppose; no outcome is guaranteed.",
        ],
    )


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "sample_report.pdf"
    report = sample_report()
    out.with_suffix(".html").write_text(render_html(report), encoding="utf-8")
    render_pdf(report, out)
    print(f"Wrote {out} and {out.with_suffix('.html')}")


if __name__ == "__main__":
    main()
