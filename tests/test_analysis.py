from pathlib import Path

import pytest

from tm_advisor.analysis import check
from tm_advisor.models import Application, Risk
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def register():
    return FixtureRegisterClient.load(DATA / "register_fixture.json")


@pytest.fixture(scope="module")
def picklist():
    return Picklist.load(DATA / "picklist_sample.json")


def app(mark, **classes):
    return Application(mark=mark, classes=[{"class_number": int(n[1:]), "terms": t} for n, t in classes.items()])


def test_ecoknit_example_is_high_and_escalates(register, picklist):
    report = check(app("EcoKnit", c25=["Clothing", "Footwear", "Headwear", "Athletic shirts", "Sweaters", "Denim jackets"]),
                   register, picklist)

    assert report.overall_risk == Risk.HIGH
    top = report.conflicts[0]
    assert top.cited_number == "2198432"
    assert top.risk == Risk.HIGH
    assert set(top.overlaps[0].overlapping_terms) == {"Clothing", "Sweaters"}
    # A broad heading ("Clothing") is part of the overlap, yet dropping it and "Sweaters" leaves other terms,
    # so the engine says which terms cause the overlap rather than producing an exclusion string.
    assert "Clothing" in top.option and "Sweaters" in top.option


def test_lapsed_mark_is_information_only(register, picklist):
    report = check(app("EcoKnit", c25=["Hats"]), register, picklist)
    lapsed = next(c for c in report.conflicts if c.cited_number == "2311007")
    assert not lapsed.live
    assert lapsed.risk == Risk.LOW
    assert "Not live" in lapsed.option
    assert report.conflicts[-1] is lapsed  # live conflicts first


def test_overlap_that_narrowing_cannot_fix_escalates(register, picklist):
    report = check(app("EcoKnit", c25=["Sweaters"]), register, picklist)
    assert report.escalate
    assert any("can't be removed by narrowing" in r for r in report.escalation_reasons)


def test_same_class_is_high_related_class_is_medium_unrelated_is_nothing(register, picklist):
    report = check(app("Kwikfix", c42=["Design of computer software"]), register, picklist)
    assert report.conflicts[0].risk == Risk.HIGH  # cited also covers class 42 software

    report = check(app("Kwikfix", c41=["Education services"]), register, picklist)
    assert report.conflicts[0].risk == Risk.MEDIUM  # class 9 software is related to class 41 education

    report = check(app("Kwikfix", c25=["Hats"]), register, picklist)
    assert report.conflicts == []


def test_clean_mark_is_low(register, picklist):
    report = check(app("Zorbly", c25=["Clothing"]), register, picklist)
    assert report.overall_risk == Risk.LOW
    assert report.conflicts == []
    assert not report.escalate
    assert report.picklist_only


def test_picklist_suggestions_for_bespoke_terms(register, picklist):
    report = check(app("Zorbly", c25=["Woollen knitted sweaters for kids", "Hats"]), register, picklist)
    bespoke = report.picklist[0]
    assert not bespoke.on_picklist
    assert "Sweaters" in bespoke.suggestions
    assert report.picklist[1].on_picklist
    assert not report.picklist_only


def test_wholly_descriptive_mark_is_high_and_escalates(register, picklist):
    report = check(app("Best Coffee", c30=["Coffee"]), register, picklist)
    assert report.overall_risk == Risk.HIGH
    assert any("section 41" in r for r in report.escalation_reasons)


def test_disclaimers_always_present(register, picklist):
    report = check(app("Zorbly", c25=["Hats"]), register, picklist)
    assert any("not legal advice" in d for d in report.disclaimers)
