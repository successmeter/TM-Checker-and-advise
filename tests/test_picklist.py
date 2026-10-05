from pathlib import Path

import pytest

from tm_advisor.picklist import Picklist

DATA = Path(__file__).resolve().parents[1] / "data" / "picklist_sample.json"


@pytest.fixture(scope="module")
def picklist():
    return Picklist.load(DATA)


def test_exact_match_ignores_case_and_plural(picklist):
    assert picklist.match(25, "clothing").description == "Clothing"
    assert picklist.match(25, "SWEATER").description == "Sweaters"


def test_match_is_per_class(picklist):
    assert picklist.match(9, "Clothing") is None


def test_suggest_for_bespoke_term(picklist):
    suggestions = picklist.suggest(25, "woollen knitted sweaters for kids")
    assert "Sweaters" in suggestions
    assert "Knitted garments" in suggestions


def test_suggest_nothing_when_no_words_shared(picklist):
    assert picklist.suggest(25, "quantum widgets") == []


def test_search_across_classes(picklist):
    classes = {i.class_number for i in picklist.search("clothing")}
    assert {25, 35} <= classes
    assert all(i.class_number == 35 for i in picklist.search("clothing", 35))


def test_find_groups_by_class_best_first(picklist):
    from tm_advisor.picklist import load_classes
    classes = load_classes(DATA.parent / "classes.json")
    groups = picklist.find("coffee", "similar", classes=classes)
    assert groups[0][0] == 30
    assert groups[0][1][0].description == "Coffee"
    assert {cls for cls, _ in groups} >= {30, 43, 35}
    assert all(cls >= 35 for cls, _ in picklist.find("coffee", kinds={"services"}, classes=classes))


def test_find_exact_needs_every_word(picklist):
    exact = picklist.find("retail clothing", "exact")
    assert [cls for cls, _ in exact] == [35]
    similar = picklist.find("retail clothing", "similar")
    assert 25 in [cls for cls, _ in similar]


def test_find_similar_matches_longer_word_forms(picklist):
    groups = dict(picklist.find("knit", "similar"))
    assert "Knitted garments" in [i.description for i in groups[25]]


def test_sample_is_flagged(picklist):
    assert picklist.is_sample
