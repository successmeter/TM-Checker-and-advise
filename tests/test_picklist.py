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
    assert classes == {25, 35}
    assert all(i.class_number == 35 for i in picklist.search("clothing", 35))
