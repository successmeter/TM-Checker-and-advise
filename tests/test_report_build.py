from pathlib import Path

from tm_advisor.analysis import check, with_ai_distinctiveness
from tm_advisor.explain import Explanation, ExplainedConflict, ExplainedPart, ExplanationUnavailable
from tm_advisor.models import AiDistinctiveness, Application, ClassSpec, RegisterClass, RegisterMark, Risk
from tm_advisor.picklist import Picklist, load_classes
from tm_advisor.register import FixtureRegisterClient
from tm_advisor.report.build import build_report
from tm_advisor.report.render import render_html

DATA = Path(__file__).resolve().parents[1] / "data"
CLASSES = load_classes(DATA / "classes.json")
PICKLIST = Picklist.load(DATA / "picklist_sample.json")


def mark(number, words, cls, terms, **kw):
    return RegisterMark(number=number, words=words, status="Registered: Registered/protected",
                        status_group="REGISTERED", classes=[RegisterClass(class_number=cls, terms=terms)], **kw)


REGISTER = FixtureRegisterClient([
    mark("2536546", "SUCCESS+", 35, ["retail services for bicycles"], owner="Plus Co"),
    mark("2390609", "ODD METER", 42, ["software as a service"]),
])
APP = Application(mark="Success Meter", applicant="Example Pty Ltd", classes=[
    ClassSpec(class_number=35, terms=["business consultancy"]),
    ClassSpec(class_number=42, terms=["software as a service", "hosting of websites"])])
AI = AiDistinctiveness(likelihood="likely", meaning="A measure of success.", reasoning="Others need these words.",
                       affected_terms=["business consultancy"], options=["Use a composite mark."])
KW = dict(classes=CLASSES, reference="TA-1", created="7 October 2026", register_searched="7 October 2026, 10:00",
          sources=["Register (test)"])


class FakeExplainer:
    def __init__(self, fail=False):
        self.fail, self.efforts = fail, []

    def explain(self, report, excerpts, effort=None):
        self.efforts.append(effort)
        if self.fail:
            raise ExplanationUnavailable("down")
        return Explanation(overview="Written overview.", next_steps=["Do this first."], model="m",
                           conflicts=[ExplainedConflict(cited_number="2536546", explanation="It leads with SUCCESS.",
                                                        citations=[]),
                                      ExplainedConflict(cited_number="999", explanation="invented", citations=[])],
                           distinctiveness=ExplainedPart(explanation="x", citations=[]))


def checked():
    return with_ai_distinctiveness(check(APP, REGISTER, PICKLIST), AI)


def test_report_follows_the_check_and_uses_claude_only_for_wording():
    report = checked()
    explainer = FakeExplainer()
    doc = build_report(APP, report, explainer=explainer, **KW)
    assert explainer.efforts == ["high"]
    assert doc.summary == "Written overview." and "Do this first." in doc.uncertainties
    assert doc.route is None and doc.design_guidance
    assert doc.overall_risk == report.overall_risk
    assert [m.number for m in doc.similar_marks] == [c.cited_number for c in report.conflicts]
    plus = next(m for m in doc.similar_marks if m.number == "2536546")
    assert plus.what_to_do.startswith("It leads with SUCCESS.") and plus.owner == "Plus Co" and plus.open_questions
    assert doc.distinctiveness.likelihood == "likely" and doc.distinctiveness.meaning == "A measure of success."
    assert doc.filing.headstart_part1 == 400 and doc.filing.headstart_part2 == 260
    assert doc.prepared_for == "Example Pty Ltd"
    html = render_html(doc)
    assert "Success Meter" in html and "#2536546" in html


def test_report_is_complete_without_claude():
    doc = build_report(APP, checked(), explainer=FakeExplainer(fail=True), **KW)
    assert "Overall review priority" in doc.summary and doc.key_findings and doc.research_paths
    assert render_html(doc)


def test_non_picklist_terms_cost_more_and_are_labelled():
    app = APP.model_copy(update={"classes": [ClassSpec(class_number=35, terms=["bespoke success measuring"])]})
    doc = build_report(app, check(app, REGISTER, PICKLIST), **KW)
    term = doc.specification[0].terms[0]
    assert not term.on_picklist and "A$400" in term.note
    assert doc.filing.standard == 400 and not doc.filing.all_picklist


def test_narrow_goods_route_moves_overlapping_terms_out():
    register = FixtureRegisterClient([mark("1", "SUCCESS METER", 42, ["hosting of websites"])])
    app = Application(mark="Success Meter", classes=[
        ClassSpec(class_number=42, terms=["hosting of websites", "software as a service"])])
    report = check(app, register, PICKLIST)
    doc = build_report(app, report, **KW)
    if report.route.recommended == "narrow_goods":
        assert [t.text for t in doc.specification[0].removed] == ["hosting of websites"]
    else:
        assert any("Overlaps" in t.note for t in doc.specification[0].terms)


def test_report_describes_formats_without_recommending_one():
    doc = build_report(APP, checked(), explainer=FakeExplainer(fail=True), **KW)
    assert [f.kind.split(" ")[0] for f in doc.format_notes] == ["Word", "Composite", "Logo"]
    html = render_html(doc)
    assert "No format is recommended" in html
    for phrase in ("Option to consider first", "Options worth considering", "Things to consider", "you should",
                   "we recommend"):
        assert phrase not in html, phrase


def test_marks_to_review_make_the_route_neutral_about_filing_format():
    register = FixtureRegisterClient([mark("1", "RE/MAX", 35, ["business consultancy"])])
    app = Application(mark="Revmax", classes=[ClassSpec(class_number=35, terms=["business consultancy"])])
    report = check(app, register, PICKLIST)
    assert [c.risk for c in report.conflicts] == [Risk.MEDIUM]
    assert report.route.recommended == "review"
    assert "RE/MAX" in report.route.reasons[0] and "before you choose a filing format" in report.route.reasons[0]
    assert not any("any style" in r or "logo" in r and "protects the words in" in r for r in report.route.reasons)


def test_claude_sees_only_the_marks_that_need_attention():
    register = FixtureRegisterClient([mark(str(n), f"SUCCESSMAKER{n}", 35, ["business consultancy"]) for n in range(20)]
                                     + [mark("x", "ODD METER", 42, ["software as a service"])])
    report = check(APP, register, PICKLIST)
    seen = []

    class Recorder(FakeExplainer):
        def explain(self, report, excerpts, effort=None):
            seen.append(report)
            return super().explain(report, excerpts, effort)

    build_report(APP, report, explainer=Recorder(), **KW)
    assert len(seen[0].conflicts) <= 8 and all(c.risk != Risk.LOW for c in seen[0].conflicts)
    html = render_html(build_report(APP, report, **KW))
    assert "Appendix: lower-priority marks" in html


def test_citations_are_not_repeated_and_marks_have_one_what_to_do():
    from tm_advisor.explain import Citation as Cited
    from tm_advisor.report.build import _unique_citations
    cites = [Cited(id="1", title="22.9. Words", heading="22.9. Words", url="u"),
             Cited(id="2", title="22.7. Examination", heading="22.7.8 Honest desire", url="u"),
             Cited(id="3", title="22.7. Examination", heading="22.7.8 Honest desire", url="u")]
    out = _unique_citations(cites)
    assert [(c.title, c.heading) for c in out] == [("22.9. Words", ""), ("22.7. Examination", "22.7.8 Honest desire")]
    doc = build_report(APP, checked(), explainer=FakeExplainer(), **KW)
    plus = next(m for m in doc.similar_marks if m.number == "2536546")
    assert plus.what_to_do == "It leads with SUCCESS."



FORBIDDEN = ["you should", "you must", "file as", "ready to paste", "safe to", "will be accepted", "no risk",
             "don't need a lawyer", "guarantee that", "option to consider first", "we recommend", "consider a word mark",
             "consider a composite", "things to consider"]


def test_report_reads_as_options_not_instructions():
    """Risk assessment §4.1: research and options, never instructions or conclusions."""
    for explainer in (None, FakeExplainer(fail=True)):
        doc = build_report(APP, checked(), explainer=explainer, **KW)
        text = render_html(doc).lower()
        for phrase in FORBIDDEN:
            assert phrase not in text, phrase
    assert "uncertainty:" in render_html(build_report(APP, checked(), **KW)).lower()


BIZ_REGISTER = FixtureRegisterClient([
    mark("1939908", "IMPRINT", 42, ["Software as a service (SaaS) featuring software for controlling connected devices"]),
    mark("2574", "BIZY", 42, ["Providing temporary use of non-downloadable collaboration software"])])
BIZ_APP = Application(mark="BizImprint", classes=[ClassSpec(class_number=42, terms=["software as a service [SaaS]"])])


def test_report_with_marks_to_review_is_neutral_and_points_to_professional_review():
    doc = build_report(BIZ_APP, check(BIZ_APP, BIZ_REGISTER, PICKLIST), **KW)
    html = render_html(doc)
    assert doc.route is None
    assert "Nothing in this report suggests you need one" not in html
    assert "professional review may be useful before committing to an application or adopting the brand" in html
    assert "in any style, font or logo" not in html


def test_goods_links_say_what_they_are_based_on():
    doc = build_report(BIZ_APP, check(BIZ_APP, BIZ_REGISTER, PICKLIST), **KW)
    imprint = next(m for m in doc.similar_marks if m.words == "IMPRINT")
    assert imprint.goods_points and imprint.goods_points[0].startswith("Shared wording:")
    assert "Shared words alone don't make the services similar" in imprint.goods_points[0]
    assert "compare what" not in imprint.goods_points[0]


def test_findings_link_to_the_act_and_low_marks_go_to_the_appendix():
    html = render_html(build_report(BIZ_APP, check(BIZ_APP, BIZ_REGISTER, PICKLIST), **KW))
    assert "Relevant IP Australia guidance" in html and "Trade Marks Act 1995, section 44" in html
    assert "section 41" in html
    assert html.index("About this report</h2>") < html.index("Appendix: lower-priority marks</h2>")
    assert "BIZY" in html[html.index("Appendix: lower-priority marks</h2>"):]
