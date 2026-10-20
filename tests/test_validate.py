from tests.test_report_build import BIZ_APP, BIZ_REGISTER, KW, PICKLIST
from tm_advisor.analysis import check
from tm_advisor.explain import Explanation, ExplainedConflict, ExplainedPart
from tm_advisor.models import Risk
from tm_advisor.report.build import build_report
from tm_advisor.report.validate import checked, problems

REPORT = check(BIZ_APP, BIZ_REGISTER, PICKLIST)  # IMPRINT 1939908 Medium, BIZY 2574 Low


def explanation(overview="The search found two marks that share part of the name.", mark_text="IMPRINT shares wording.",
                distinct="No descriptive meaning was found.", steps=("Whether IMPRINT is used for business software.",)):
    return Explanation(overview=overview, model="m", next_steps=list(steps),
                       conflicts=[ExplainedConflict(cited_number="1939908", explanation=mark_text, citations=[])],
                       distinctiveness=ExplainedPart(explanation=distinct, citations=[]))


def test_good_narrative_passes_unchanged():
    e = explanation()
    assert checked(e, REPORT) == e


def test_advice_and_promises_are_removed():
    assert problems("You should file a word mark.", REPORT)
    assert problems("This will be accepted.", REPORT)
    assert not problems("No format is recommended, and no outcome is guaranteed.", REPORT)
    e = checked(explanation(overview="We recommend a composite mark.", mark_text="You must avoid this mark."), REPORT)
    assert e.overview == "" and e.conflicts == []


def test_priorities_must_match_the_check():
    assert REPORT.overall_risk == Risk.MEDIUM
    e = checked(explanation(overview="Overall review priority: High.", mark_text="IMPRINT has a high review priority."), REPORT)
    assert e.overview == "" and e.conflicts == []
    ok = checked(explanation(mark_text="IMPRINT has a medium review priority."), REPORT)
    assert len(ok.conflicts) == 1


def test_unknown_trade_mark_numbers_are_removed():
    e = checked(explanation(mark_text="It resembles 1234567 and 1939908."), REPORT)
    assert e.conflicts == []
    assert not problems("Fees are A$250 for 1 class.", REPORT)


def test_a_summary_that_contradicts_the_findings_is_removed():
    e = checked(explanation(overview="No similar marks were found on the register."), REPORT)
    assert e.overview == ""


def test_report_falls_back_to_plain_wording():
    class Explainer:
        def explain(self, report, excerpts, effort=None):
            return explanation(overview="You should file now; it will be accepted.",
                               mark_text="IMPRINT is a low priority.")
    doc = build_report(BIZ_APP, REPORT, explainer=Explainer(), **KW)
    assert doc.summary.startswith("Overall review priority: Medium")
    imprint = next(m for m in doc.similar_marks if m.number == "1939908")
    assert imprint.what_to_do == "" and imprint.open_questions


def test_distinctiveness_assessment_is_checked_too():
    from tm_advisor.analysis import with_ai_distinctiveness
    from tm_advisor.models import AiDistinctiveness
    ai = AiDistinctiveness(likelihood="possible", meaning="", reasoning="You should add an invented word.",
                           affected_terms=[], options=["You must file a composite mark.", "Some applicants add a word."])
    doc = build_report(BIZ_APP, with_ai_distinctiveness(REPORT, ai), **KW)
    assert "should" not in doc.distinctiveness.reasoning
    assert doc.distinctiveness.options == ["Some applicants add a word."]
