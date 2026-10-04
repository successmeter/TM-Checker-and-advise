import pytest
from pydantic import ValidationError

from tm_advisor.models import Application, RegisterMark
from tm_advisor.text import edit_similarity, phonetic_key, squash, stem


def test_application_cleans_mark_and_terms():
    app = Application(mark="  Eco   Knit ", classes=[{"class_number": 25, "terms": [" Clothing ", "clothing", "Hats"]}])
    assert app.mark == "Eco Knit"
    assert app.classes[0].terms == ["Clothing", "Hats"]


@pytest.mark.parametrize("number", [0, 46])
def test_class_number_must_be_nice_class(number):
    with pytest.raises(ValidationError):
        Application(mark="X", classes=[{"class_number": number, "terms": ["a"]}])


def test_blank_mark_and_empty_terms_rejected():
    with pytest.raises(ValidationError):
        Application(mark="   ", classes=[{"class_number": 25, "terms": ["a"]}])
    with pytest.raises(ValidationError):
        Application(mark="X", classes=[{"class_number": 25, "terms": ["  "]}])


def test_duplicate_classes_rejected():
    with pytest.raises(ValidationError):
        Application(mark="X", classes=[{"class_number": 25, "terms": ["a"]}, {"class_number": 25, "terms": ["b"]}])


def test_live_status():
    assert RegisterMark(number="1", words="A", status="Registered", classes=[]).is_live
    assert not RegisterMark(number="1", words="A", status="Lapsed/Not Protected", classes=[]).is_live


def test_squash_ignores_spacing_and_punctuation():
    assert squash("Eco-Knit") == squash("ECO KNIT") == "ecoknit"


def test_stem_plurals():
    assert stem("sweaters") == "sweater"
    assert stem("accessories") == "accessory"
    assert stem("dresses") == "dress"
    assert stem("glass") == "glass"


def test_phonetic_key_sound_alikes():
    assert phonetic_key("Kwik") == phonetic_key("Quick")
    assert phonetic_key("Fone") == phonetic_key("Phone")
    assert phonetic_key("Kool") == phonetic_key("Cool")
    assert phonetic_key("Apple") != phonetic_key("Orange")


def test_edit_similarity_bounds():
    assert edit_similarity("abc", "abc") == 1.0
    assert edit_similarity("abc", "xyz") == 0.0
    assert 0.8 < edit_similarity("ecoknit", "ecoknot") < 1.0
