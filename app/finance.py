"""Deterministic Decimal calculations; rates are nominal annual percentages."""
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal["compound", "loan", "budget"]
    principal: Decimal | None = Field(None, ge=0, le=Decimal("1000000000000"), max_digits=18, decimal_places=2)
    annual_rate: Decimal | None = Field(None, ge=0, le=100, max_digits=10, decimal_places=6)
    years: int | None = Field(None, ge=1, le=50, strict=True)
    monthly_contribution: Decimal = Field(Decimal(0), ge=0, le=Decimal("1000000000"), max_digits=18, decimal_places=2)
    income: Decimal | None = Field(None, ge=Decimal("0.01"), le=Decimal("1000000000000"), max_digits=18, decimal_places=2)
    expenses: Decimal | None = Field(None, ge=0, le=Decimal("1000000000000"), max_digits=18, decimal_places=2)

    @model_validator(mode="after")
    def required_fields(self):
        keys = ("income", "expenses") if self.kind == "budget" else ("principal", "annual_rate", "years")
        for key in keys:
            if getattr(self, key) is None:
                raise ValueError(f"{key} is required for {self.kind}")
        if self.kind == "loan" and self.principal == 0:
            raise ValueError("Loan principal must be greater than zero")
        return self


def money(x: Decimal) -> str:
    return str(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate(req: CalculationRequest) -> dict:
    with localcontext() as ctx:
        ctx.prec = 60
        if req.kind == "budget":
            surplus = req.income - req.expenses
            values = {"income": money(req.income), "expenses": money(req.expenses), "surplus": money(surplus),
                      "savings_rate_percent": money(surplus / req.income * 100)}
            return dict(kind="budget", summary=f"月度结余 / Monthly surplus: {money(surplus)}; 储蓄率 / Savings rate: {values['savings_rate_percent']}%",
                        values=values, series=[], formula="surplus = income - expenses; savings_rate = surplus / income × 100%",
                        assumptions=["Income and expenses must use the same currency and monthly period.", "Savings rate may be negative."])
        r = req.annual_rate / 1200
        n = req.years * 12
        series = [{"period": 0, "balance": money(req.principal)}]
        balance = req.principal
        if req.kind == "compound":
            for month in range(1, n + 1):
                balance = balance * (1 + r) + req.monthly_contribution
                if month % 12 == 0:
                    series.append({"period": month // 12, "balance": money(balance)})
            contributed = req.principal + req.monthly_contribution * n
            values = {"future_value": money(balance), "total_contributions": money(contributed),
                      "interest": money(balance - contributed), "months": n}
            return dict(kind="compound", summary=f"期末金额 / Future value: {money(balance)}; 利息 / Interest: {values['interest']}",
                        values=values, series=series, formula="FV = P(1+r)^n + C × ((1+r)^n - 1) / r; r=annual_rate/1200; n=12×years; r=0: FV=P+C×n",
                        assumptions=["Fixed nominal annual rate, compounded monthly; contributions at month-end.",
                                     "Same currency throughout; no inflation, tax, fees, or market volatility. This is a scenario, not a guaranteed return.",
                                     "Only final display values are rounded half-up to two decimals."])
        payment = req.principal / n if r == 0 else req.principal * r / (1 - (1 + r) ** (-n))
        for month in range(1, n + 1):
            balance = max(Decimal(0), balance * (1 + r) - payment)
            if month % 12 == 0:
                series.append({"period": month // 12, "balance": money(balance)})
        total = payment * n
        values = {"monthly_payment": money(payment), "total_payment": money(total), "total_interest": money(total - req.principal), "months": n}
        return dict(kind="loan", summary=f"每月还款 / Monthly payment: {money(payment)}; 总利息 / Total interest: {values['total_interest']}",
                    values=values, series=series, formula="A=P×r/(1-(1+r)^(-n)); r=annual_rate/1200; n=12×years; r=0: A=P/n",
                    assumptions=["Fixed-rate monthly annuity, payments at month-end; no fees, early repayment, or rate changes.",
                                 "Uses nominal annual rate, not an all-in APR; bank schedules may differ due to monthly rounding.",
                                 "Full precision internally; total payment uses unrounded monthly payment."])


def parse_calculation(message: str) -> CalculationRequest | None:
    """Explicit tool commands, not arbitrary language-to-financial-parameter guessing."""
    message = message.strip()
    match = re.match(r"^/?(compound|loan|budget|复利|贷款|预算)(?:\s|$)", message, re.I)
    if not match:
        return None
    kind = {"复利": "compound", "贷款": "loan", "预算": "budget"}.get(match[1].lower(), match[1].lower())
    tail = message[match.end():].strip()
    pairs = re.findall(r"([a-z_]+)\s*=\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))", tail, re.I)
    residue = re.sub(r"([a-z_]+)\s*=\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))", "", tail, flags=re.I).strip(" ,，;")
    if residue or not pairs or len({k.lower() for k, _ in pairs}) != len(pairs):
        raise ValueError("Use the calculator panel or: compound principal=10000 annual_rate=5 years=10 monthly_contribution=500")
    params = {k.lower(): v for k, v in pairs}
    if "years" in params:
        if not params["years"].isdigit():
            raise ValueError("years must be a whole number from 1 to 50")
        params["years"] = int(params["years"])
    return CalculationRequest(kind=kind, **params)
