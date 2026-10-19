"""A sample report (SUCCESS METER) to design and preview the paid report.

  py -m tm_advisor.report.sample                 writes data/sample_report.pdf and data/sample_report.html

The similar marks are real entries from the register (number, status and classes as at October 2026); everything
else is illustrative. The page carries a "Sample report" banner.
"""

import sys
from pathlib import Path

from ..models import Risk
from .build import ADVERSE_HEADSTART, DESIGN_GUIDANCE, LIMITATIONS
from .render import render_html, render_pdf
from .schema import DistinctivenessSection, Filing, FormatNote, ReportDoc, SimilarMark, SpecClass, SpecTerm

ROOT = Path(__file__).resolve().parents[2]

GOODS_NOTE = "Both cover class {c}. Their exact goods and services are compared term by term in a real report."


def sample_report() -> ReportDoc:
    return ReportDoc(
        reference="BI-SAMPLE-0001", created="7 October 2026", sample=True,
        prepared_for="Example Pty Ltd",
        register_searched="7 October 2026, 10:42 AEDT",
        sources=["Australian Trade Mark Search API (IP Australia), production register, searched 7 October 2026.",
                 "IP Australia goods and services picklist (tmgns.search.ipaustralia.gov.au), copied 6 October 2026.",
                 "IP Australia Trade Marks Manual of Practice and Procedure, downloaded 1 October 2026."],
        mark="SUCCESS METER", mark_kind="word", classes=[35, 42],
        overall_risk=Risk.HIGH,
        summary=("Read as a whole, SUCCESS METER may be seen as describing what the services do (measuring business "
                 "success), which bears on section 41. Two earlier marks that lead with SUCCESS in class 35 were given "
                 "a medium review priority. The main uncertainties are how an examiner reads the phrase as a whole, "
                 "and what those earlier marks' services actually are."),
        key_findings=[
            "Distinctiveness (section 41): read as a whole, the mark is likely to be seen as describing your goods or "
            "services (section 2).",
            "Earlier marks (section 44): 2 of the 238 marks screened were given a medium review priority: SUCCESS+ "
            "(2536546), SUCCESSCULTURE (2580382) (section 3).",
            "Goods and services: every term is on IP Australia's picklist (section 4).",
        ],
        format_notes=[
            FormatNote(kind="Word mark", protects="The words themselves, independent of font or styling. Not a logo design.",
                       findings="The distinctiveness finding applies directly: the words are assessed on their own. "
                                "Your words would be compared with the 2 earlier marks in section 3."),
            FormatNote(kind="Composite mark (design and words)", protects="One particular combination of design and words.",
                       findings="Examiners consider whether a substantial, distinctive design gives the mark as a whole "
                                "the distinctiveness the words lack; the words on their own stay unprotected. Against "
                                "the 2 earlier marks in section 3, the words are often the main feature compared."),
            FormatNote(kind="Logo mark", protects="The design only. Your name is not protected.",
                       findings="This report compares words, not designs: IP Australia's image search covers similar logos."),
        ],
        uncertainties=[
            "Review priorities are screening signals from an automated search, not predictions. Examiners assess each "
            "application as a whole and on its own facts, and other traders can oppose.",
            "The distinctiveness assessment is an automated reading of what the words mean for your goods and "
            "services. It doesn't take account of any use you have made of the mark, which can be relevant.",
            "Whether SUCCESS+ and SUCCESSCULTURE are used for business consultancy or analysis isn't shown in this "
            "sample; their full records list their services.",
            "The register doesn't show whether or how owners use their marks, and unregistered use by others isn't "
            "covered by this search.",
            "Logos and other designs were not compared; only words. Marks filed very recently may not be searchable yet.",
        ],
        research_paths=[
            "The full register records of the marks in section 3 (linked), including every class, the full goods and "
            "services, status history and owner.",
            "Unregistered use of similar names: ASIC's business names register, ABN Lookup, domain names and a general "
            "web search.",
            "IP Australia's TM Headstart: an examiner's preliminary assessment of your application, usually within "
            "about 5 business days, before a full application (fees in section 7).",
            "A registered trade marks attorney or lawyer, for advice on your circumstances: because potentially "
            "relevant earlier registrations were identified, professional review may be useful before committing to "
            "an application or adopting the brand.",
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
            options=["Some applicants file a composite mark, where a substantial, distinctive design can give the "
                     "mark as a whole its distinctiveness (section 1).",
                     "Some add or substitute an invented or unusual word.",
                     "Where a mark has been used for some time, evidence of that use (sales, advertising, customers) "
                     "can be relevant."],
        ),
        marks_reviewed=238,
        similar_marks=[
            SimilarMark(number="2536546", words="SUCCESS+", status="Protected: Registered/protected", classes=[35, 41],
                        risk=Risk.MEDIUM,
                        why_similar=["Your mark starts with the whole of this mark (SUCCESS).",
                                     "Short marks that lead with the same word are compared closely."],
                        goods_overlap=GOODS_NOTE.format(c=35),
                        what_to_do=("SUCCESS+ consists of the word your mark starts with. Its class 35 services "
                                    "aren't shown in this sample; if they are business consultancy or analysis, the "
                                    "overlap would be direct."),
                        open_questions=["What are its class 35 services, and are they like yours in purpose and users?",
                                        "Is the mark in use, and how? The register doesn't say."]),
            SimilarMark(number="2580382", words="SUCCESSCULTURE", status="Registered: Registered/protected",
                        classes=[35, 41], risk=Risk.MEDIUM,
                        why_similar=["Both marks begin with SUCCESS, which people tend to notice first."],
                        goods_overlap=GOODS_NOTE.format(c=35),
                        what_to_do="Both marks begin with SUCCESS; the second words differ.",
                        open_questions=["How much weight does the shared word SUCCESS carry, given it is a common, "
                                        "praising word?",
                                        "Is the mark in use, and how? The register doesn't say."]),
            SimilarMark(number="2451395", words="P PRACTICE SUCCESS", logo=True, status="Registered: Registered/protected",
                        classes=[35, 42], risk=Risk.LOW,
                        why_similar=["Shares the word SUCCESS, but the rest of the marks is different."],
                        goods_overlap=GOODS_NOTE.format(c="35 and 42"),
                        what_to_do=""),
            SimilarMark(number="2390609", words="ODD METER", status="Protected: Registered/protected", classes=[42],
                        risk=Risk.LOW,
                        why_similar=["Shares the word METER, but the rest of the marks is different."],
                        goods_overlap=GOODS_NOTE.format(c=42),
                        what_to_do=""),
            SimilarMark(number="2248191", words="AUDOO METER", status="Protected: Registered/protected", classes=[9, 42],
                        risk=Risk.LOW,
                        why_similar=["Shares the word METER, but the rest of the marks is different."],
                        goods_overlap=GOODS_NOTE.format(c=42),
                        what_to_do=""),
            SimilarMark(number="2505432", words="METERMATE", status="Registered: Registered/protected", classes=[9, 42],
                        risk=Risk.LOW,
                        why_similar=["METER begins this mark, but the rest is different."],
                        goods_overlap=GOODS_NOTE.format(c=42),
                        what_to_do=""),
        ],
        specification=[
            SpecClass(class_number=35, title="Advertising, business management and administration", terms=[
                SpecTerm(text="business data analysis"),
                SpecTerm(text="strategic business consultancy"),
                SpecTerm(text="social media strategy and marketing consultancy"),
                SpecTerm(text="benchmarking services for business management purposes"),
            ]),
            SpecClass(class_number=42, title="Scientific, technology and software services", terms=[
                SpecTerm(text="software as a service [SaaS]"),
            ], removed=[
                SpecTerm(text="hosting of websites", note="Do you host websites for others? Unused terms add overlap "
                                                          "with other marks and can later be removed for non-use."),
                SpecTerm(text="design and development of homepages and websites",
                         note="Do you build websites for clients? Unused terms add overlap with other marks."),
            ]),
        ],
        specification_notes=[
            "An application claims goods and services the applicant uses or intends to use. Terms that are never used "
            "can later be removed for non-use, and each term claimed is a term that can overlap other marks.",
            "IP Australia's Trade Marks Manual (Part 27.3) explains how amendments and limitations are treated.",
        ],
        design_guidance=DESIGN_GUIDANCE,
        filing=Filing(
            classes=2, headstart_part1=400, headstart_part2=260, standard=500, all_picklist=True,
            steps=["Requests and applications are made online, through an IP Australia online services account "
                   "(portal.ipaustralia.gov.au).",
                   "A TM Headstart request for a word mark sets out the words exactly, and the goods and services "
                   "(section 4).",
                   "Once Part 1 is paid, an examiner's assessment usually arrives within about 5 business days.",
                   "Paying Part 2 turns the request into an application; that date becomes the filing date.",
                   "The application is then examined; an examination report, if issued, sets a deadline to respond."],
            adverse_headstart=ADVERSE_HEADSTART),
        attorney_reasons=[],
        limitations=LIMITATIONS,
    )


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "sample_report.pdf"
    report = sample_report()
    out.with_suffix(".html").write_text(render_html(report), encoding="utf-8")
    render_pdf(report, out)
    print(f"Wrote {out} and {out.with_suffix('.html')}")


if __name__ == "__main__":
    main()
