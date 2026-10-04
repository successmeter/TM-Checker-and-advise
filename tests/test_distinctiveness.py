from tm_advisor.distinctiveness import screen


def test_invented_word_is_not_flagged():
    flags, wholly = screen("Zorbly", ["Clothing"])
    assert flags == []
    assert not wholly


def test_word_that_names_the_goods_is_flagged():
    flags, wholly = screen("Sweater Hub", ["Sweaters", "Cardigans"])
    reasons = {f.word: f.reason for f in flags}
    assert "Describes" in reasons["sweater"]
    assert "hub" in reasons
    assert wholly


def test_laudatory_and_place_words():
    flags, wholly = screen("Best Bondi Brew", ["Coffee"])
    assert {f.word for f in flags} == {"best", "bondi"}
    assert not wholly


def test_glue_words_ignored():
    flags, wholly = screen("The Best Coffee", ["Coffee"])
    assert wholly
    assert "the" not in {f.word for f in flags}
