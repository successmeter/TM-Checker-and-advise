from tm_advisor.mark_similarity import compare


def test_identical():
    assert compare("EcoKnit", "ecoknit").score >= 0.97
    assert compare("ECOKNIT", "ECOKNIT").score == 1.0


def test_spacing_and_punctuation_only():
    result = compare("Eco-Knit", "ECO KNIT")
    assert result.score == 0.97


def test_one_letter_change_is_similar():
    assert compare("Ecoknit", "Ecoknot").score >= 0.85


def test_sound_alike():
    result = compare("Kwikfix", "Quickfix")
    assert result.score >= 0.85
    assert any("sound" in r for r in result.reasons)


def test_containment_at_start():
    result = compare("EcoKnit", "ECO KNITWEAR")
    assert result.score >= 0.85
    assert any("ECOKNIT" in r for r in result.reasons)


def test_shared_word():
    result = compare("Bondi Brew", "Bondi Bakery")
    assert result.score >= 0.7
    assert any("BONDI" in r for r in result.reasons)


def test_weak_shared_word_does_not_count():
    assert compare("The Lab", "The Garden").score < 0.7


def test_unrelated_marks_score_low():
    assert compare("EcoKnit", "Thunderbolt").score < 0.5


def test_distinctive_word_inside_other_mark_despite_extra_words():
    result = compare("Best EcoKnit", "ECO KNITWEAR")
    assert result.score >= 0.75
    assert any("ECOKNIT" in r for r in result.reasons)
