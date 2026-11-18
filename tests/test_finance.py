from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.finance import CalculationRequest, calculate, parse_calculation


def test_compound_known_result():
    result = calculate(CalculationRequest(kind="compound", principal=10000, annual_rate=5, years=10, monthly_contribution=500))
    # Closed-form reference: P*(1+.05/12)**120 + 500*((1+.05/12)**120-1)/(.05/12).
    assert result["values"]["future_value"] == "94111.23"
    assert result["values"]["total_contributions"] == "70000.00"
    assert len(result["series"]) == 11


def test_zero_interest_contributions():
    result = calculate(CalculationRequest(kind="compound", principal=1000, annual_rate=0, years=2, monthly_contribution=100))
    assert result["values"]["future_value"] == "3400.00"


def test_loan_reference_and_amortization():
    result = calculate(CalculationRequest(kind="loan", principal=100000, annual_rate=6, years=30))
    assert result["values"]["monthly_payment"] == "599.55"
    assert result["values"]["total_interest"] == "115838.19"
    assert result["series"][-1]["balance"] == "0.00"
    assert all(Decimal(a["balance"]) >= Decimal(b["balance"]) for a,b in zip(result["series"], result["series"][1:]))


def test_zero_rate_loan():
    result = calculate(CalculationRequest(kind="loan", principal=1200, annual_rate=0, years=1))
    assert result["values"]["monthly_payment"] == "100.00"
    assert result["values"]["total_interest"] == "0.00"


def test_negative_budget_surplus():
    values = calculate(CalculationRequest(kind="budget", income=5000, expenses=6000))["values"]
    assert values["surplus"] == "-1000.00"
    assert values["savings_rate_percent"] == "-20.00"


@pytest.mark.parametrize("overrides", [{"annual_rate": -1}, {"years": 0}, {"years": 1.5}, {"principal": "NaN"}, {"annual_rate": "Infinity"}, {"years": 51}, {"principal": -10}, {"annual_rate": "1e-100"}, {"principal": "0.001"}])
def test_reject_invalid_calculation(overrides):
    fields = dict(kind="compound", principal=100, annual_rate=5, years=1)
    fields.update(overrides)
    with pytest.raises(ValidationError):
        CalculationRequest(**fields)


def test_budget_zero_income_rejected():
    with pytest.raises(ValidationError):
        CalculationRequest(kind="budget", income=0, expenses=100)


def test_minimum_positive_rate_is_numerically_stable():
    result = calculate(CalculationRequest(kind="loan", principal=1200, annual_rate="0.000001", years=1))
    assert result["values"]["monthly_payment"] == "100.00"


def test_tiny_income_rejected():
    with pytest.raises(ValidationError):
        CalculationRequest(kind="budget", income="1e-100", expenses=1)


def test_explicit_command():
    req = parse_calculation("compound principal=10000 annual_rate=5 years=10 monthly_contribution=500")
    assert req.years == 10 and req.principal == 10000
    assert parse_calculation("What is compound interest?") is None
    with pytest.raises(ValueError):
        parse_calculation("loan principal=100 years=2 annual_rate=3 years=3")


@pytest.mark.parametrize("prefix", ["  ", "\t", "\n "])
def test_explicit_command_accepts_surrounding_whitespace(prefix):
    request = parse_calculation(prefix + "loan principal=1200 annual_rate=0 years=1  ")
    assert calculate(request)["values"]["monthly_payment"] == "100.00"
