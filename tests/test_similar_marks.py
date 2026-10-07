from pathlib import Path

from tm_advisor.analysis import check
from tm_advisor.mark_similarity import compare
from tm_advisor.models import Application, ClassSpec, RegisterClass, RegisterMark, Risk
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient
from tm_advisor.register.ipaustralia import _advanced_queries, _to_register_mark

DATA = Path(__file__).resolve().parents[1] / "data"


def mark(number, words, cls, terms, group="REGISTERED", **kw):
    return RegisterMark(number=number, words=words, status="Registered", status_group=group,
                        classes=[RegisterClass(class_number=cls, terms=terms)], **kw)


def test_two_letters_apart_or_same_start_counts_as_similar_but_low():
    for other in ("NEOMAX", "REOMAT", "RevMed", "RevLab", "Revstar"):
        assert 0.5 <= compare("Revmax", other).score < 0.7, other
    for other in ("Revolution", "Bondi", "Max"):
        assert compare("Revmax", other).score < 0.5, other


def test_similar_marks_in_unrelated_classes_are_listed_separately():
    register = FixtureRegisterClient([
        mark("1", "RE/MAX", 35, ["Business strategic planning services"]),
        mark("2", "REMAX", 36, ["Real estate agency services"], image="https://cdn.example/2.jpg", logo=True),
        mark("3", "RevLab", 1, ["Industrial chemicals"]),
        mark("4", "Bondi", 36, ["Real estate agency services"]),
    ])
    report = check(Application(mark="Revmax", classes=[ClassSpec(class_number=35, terms=["business strategic planning"])]),
                   register, Picklist.load(DATA / "picklist_sample.json"))
    assert [c.cited_number for c in report.conflicts] == ["1"]
    assert [o.number for o in report.other_marks] == ["2", "3"]  # most alike first; Bondi isn't alike at all
    assert report.other_marks[0].classes == [36] and report.other_marks[0].logo
    assert report.other_marks[0].image == "https://cdn.example/2.jpg"
    assert report.overall_risk == Risk.MEDIUM  # marks in other classes don't raise the risk


def test_register_records_carry_the_logo_picture_and_kind():
    m = _to_register_mark({"number": "1129102", "words": ["P PODICURE"], "kind": ["Figurative"],
                           "images": {"description": ["LTR P"], "images": ["https://cdn.example/T.MEDIUM.JPG"]},
                           "statusGroup": "REGISTERED", "goodsAndServices": []}, "1129102")
    assert m.image == "https://cdn.example/T.MEDIUM.JPG" and m.logo
    plain = _to_register_mark({"number": "5", "words": ["X"], "kind": ["Word"]}, "5")
    assert plain.image is None and not plain.logo


def test_search_also_asks_for_marks_starting_the_same_way():
    assert ("rev", "PREFIX") in _advanced_queries("Revmax")
    assert not any(kind == "PREFIX" for _, kind in _advanced_queries("Rev"))
