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


def test_similar_marks_in_unrelated_classes_are_not_conflicts():
    register = FixtureRegisterClient([
        mark("1", "RE/MAX", 35, ["Business strategic planning services"], image="https://cdn.example/1.jpg", logo=True),
        mark("2", "REMAX", 36, ["Real estate agency services"]),
        mark("3", "RevLab", 1, ["Industrial chemicals"]),
    ])
    report = check(Application(mark="Revmax", classes=[ClassSpec(class_number=35, terms=["business strategic planning"])]),
                   register, Picklist.load(DATA / "picklist_sample.json"))
    assert [c.cited_number for c in report.conflicts] == ["1"]
    assert report.conflicts[0].cited_image == "https://cdn.example/1.jpg" and report.conflicts[0].cited_logo


def test_a_shared_word_in_a_much_longer_mark_is_low():
    long_mark = compare("Success Meter", "Q QLD ACCOUNTING GROUP BUILDING FINANCIALLY SUCCESSFUL BUSINESS")
    assert long_mark.score < 0.7 and "rest of the marks is different" in long_mark.reasons[0]
    assert compare("Success Meter", "Success Business Coaching Group").score < 0.7
    assert compare("Success Meter", "SUCCESSMAKER").score >= 0.7
    assert compare("Success Meter", "The Success Meter Group").score >= 0.7
    assert compare("Bondi Bakery Fresh Bread", "BONDI").score >= 0.7  # their whole mark inside yours stays serious


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


def test_marks_sharing_only_one_ordinary_word_are_low():
    # Marks TM Headstart listed for SUCCESS METER (classes 35 and 42) without raising any of them as a conflict.
    for other in ("RETAIL METER", "AUDOO METER", "imeter", "METERMATE", "MeterTrac", "Meter Mode",
                  "YOUR MEASURE OF SUCCESS", "ODD METER"):
        assert compare("Success Meter", other).score < 0.7, other
    for other in ("SUCCESSCX", "SUCCESS BOX", "SUCCESS"):  # same leading word, short marks: worth a closer look
        assert compare("Success Meter", other).score >= 0.7, other
