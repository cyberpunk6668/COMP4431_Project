"""Interpretation denials are local; factual negative directions remain claims."""
import pytest

from app.options_claims import direction_statements


@pytest.mark.parametrize("text", [
    "不可比，不能当作增加或减少。",
    "配对行权价集合改变而不可比，不能称为上升或下降。",
    "不能解释为成交量增加或减少。",
    "不能描述为价格上升或下降。",
    "The difference cannot be described as an increase or decrease.",
    "不能当成增加或减少来解读。",
    "这些差异不应视为成交量增加或减少。",
    "无法解读为价格上升或下降。",
    "不能把它当成增加或减少。",
    "不能将这些差异视为真实的增加或减少。",
    "该差异不能被当成增加或减少。",
    "不能将这一变化解读为增加或减少。",
    "不可比，不能当作保持相同或持平。",
    "These totals are incomparable and cannot be read as an increase or a decrease.",
    "The difference cannot be interpreted as a real increase or decrease.",
    "This should not be taken as higher volume or lower volume.",
    "The counts must not be regarded as increased activity.",
    "It cannot be read as evidence of an increase.",
    "This cannot be directly interpreted as an increase or decrease.",
    "It should not be interpreted as unchanged.",
])
def test_local_read_as_denial_is_not_an_observed_direction(text):
    assert direction_statements(text) == []


@pytest.mark.parametrize("text,expected", [
    ("不能预测未来，但成交量增加。", [("increased", False)]),
    ("无法比较这些指标，但成交量增加。", [("increased", False)]),
    ("不可比，不能当作增加或减少；但另一项成交量增加。", [("increased", False)]),
    ("These data cannot predict the future, but volume increased.", [("increased", False)]),
    ("These values cannot be compared, but volume increased.", [("increased", False)]),
    ("It cannot be read as a forecast and volume increased.", [("increased", False)]),
    ("不能将其解读为预测并且成交量增加。", [("increased", False)]),
])
def test_unrelated_disclaimer_does_not_hide_a_direction(text, expected):
    assert direction_statements(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("成交量没有增加。", [("increased", True)]),
    ("成交量并未减少。", [("decreased", True)]),
    ("Volume did not increase.", [("increased", True)]),
    ("Volume never decreased.", [("decreased", True)]),
])
def test_factual_negative_is_still_a_historical_assertion(text, expected):
    assert direction_statements(text) == expected


@pytest.mark.parametrize("text", [
    "不能确认成交量增加。",
    "没有充分证据认定成交量增加。",
    "We cannot establish whether volume increased.",
    "An increase cannot be established.",
])
def test_existing_explicit_inference_denials_are_retained(text):
    assert direction_statements(text) == []


@pytest.mark.parametrize("text", [
    "并非不能当作增加。",
    "不是不能视为增加。",
    "It cannot not be interpreted as an increase.",
    "Not only can it be read as an increase.",
])
def test_affirmative_double_negation_does_not_exempt_the_claim(text):
    assert direction_statements(text), "An affirmative construction must remain a claim"
