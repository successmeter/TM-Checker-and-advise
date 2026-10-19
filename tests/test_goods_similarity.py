from tm_advisor.goods_similarity import relate
from tm_advisor.models import GoodsLevel


def test_shared_word_in_same_class_is_same():
    result = relate(25, ["Sweaters", "Denim jackets"], 25, ["Knitted sweaters", "Cardigans"])
    assert result.level == GoodsLevel.SAME
    assert result.overlapping_terms == ["Sweaters"]
    assert result.narrowing_helps


def test_broad_user_heading_overlaps_specific_cited_goods():
    result = relate(25, ["Clothing", "Sweaters", "Hats"], 25, ["Knitted sweaters"])
    assert result.level == GoodsLevel.SAME
    assert set(result.overlapping_terms) == {"Clothing", "Sweaters"}
    assert "Broad headings" in result.note


def test_broad_cited_heading_overlaps_everything():
    result = relate(25, ["Hats"], 25, ["Clothing"])
    assert result.level == GoodsLevel.SAME
    assert result.overlapping_terms == ["Hats"]
    assert not result.narrowing_helps


def test_no_narrowing_hint_when_cited_heading_is_broad():
    result = relate(25, ["Clothing", "Hats"], 25, ["Clothing"])
    assert "narrower list" not in result.note


def test_same_class_without_shared_words_is_related():
    result = relate(25, ["Hats"], 25, ["Socks"])
    assert result.level == GoodsLevel.RELATED
    assert result.overlapping_terms == []


def test_clothing_and_clothing_retail_are_related():
    result = relate(25, ["T-shirts"], 35, ["Retail services in relation to clothing"])
    assert result.level == GoodsLevel.RELATED


def test_retail_of_something_else_is_not_related_to_clothing():
    result = relate(25, ["T-shirts"], 35, ["Retail services in relation to hardware"])
    assert result.level == GoodsLevel.NONE


def test_unrelated_classes():
    assert relate(25, ["Hats"], 9, ["Computer software"]).level == GoodsLevel.NONE


def test_class_9_non_software_goods_not_related_to_saas():
    result = relate(42, ["software as a service [SaaS]"], 9, ["Protective clothing", "Safety footwear", "Safety helmets"])
    assert result.level == GoodsLevel.NONE


def test_class_9_software_related_to_saas_and_names_their_goods():
    result = relate(42, ["software as a service [SaaS]", "Engineering services"], 9, ["Safety helmets", "Downloadable software"])
    assert result.level == GoodsLevel.RELATED
    assert "Downloadable software" in result.note and "Safety helmets" not in result.note
    assert result.overlapping_terms == ["software as a service [SaaS]"]


def test_related_pair_needs_software_on_the_users_side_too():
    assert relate(42, ["Engineering services"], 9, ["Computer software"]).level == GoodsLevel.NONE


def test_class_35_food_retail_not_related_to_saas():
    result = relate(42, ["software as a service [SaaS]"], 35,
                    ["Retail and wholesale services including retail and wholesale of food products",
                     "Online retail store services"])
    assert result.level == GoodsLevel.NONE
