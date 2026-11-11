"""Historical option research over an explicit, fixed contract sample.

No broker or model calls. User imports are claims about data provenance, never
verified IBKR data. Trade bars are not simultaneous executable bid/ask quotes.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HistoryRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    trading_date: str
    strike: float = Field(gt=0, le=1000000, strict=True)
    right: Literal["C", "P"]
    open: float | None = Field(None, ge=0, le=1000000, strict=True)
    high: float | None = Field(None, ge=0, le=1000000, strict=True)
    low: float | None = Field(None, ge=0, le=1000000, strict=True)
    close: float | None = Field(None, ge=0, le=1000000, strict=True)
    volume: float | None = Field(None, ge=0, le=1e12, strict=True)
    open_interest: float | None = Field(None, ge=0, le=1e12, strict=True)
    oi_asof_date: str | None = None

    @field_validator("trading_date", "oi_asof_date")
    @classmethod
    def calendar_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use ISO YYYY-MM-DD dates")
        return value

    @model_validator(mode="after")
    def consistent_fields(self):
        if self.oi_asof_date and self.oi_asof_date > self.trading_date:
            raise ValueError("OI as-of date cannot be later than the observation date")
        values = (self.open, self.high, self.low, self.close)
        if self.high is not None and any(value is not None and value > self.high for value in (self.open, self.low, self.close)):
            raise ValueError("Observed price exceeds the reported high")
        if self.low is not None and any(value is not None and value < self.low for value in (self.open, self.high, self.close)):
            raise ValueError("Observed price is below the reported low")
        if all(value is not None for value in values):
            if self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.high < self.low:
                raise ValueError("Inconsistent trade OHLC values")
        if self.volume is not None and not self.volume.is_integer():
            raise ValueError("Option volume must be a whole reported contract count")
        if self.open_interest is not None and not self.open_interest.is_integer():
            raise ValueError("Open interest must be a whole contract count")
        return self


class HistoryDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    label: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=12, pattern=r"^[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?$")
    expiry: str
    currency: Literal["USD"] = "USD"
    multiplier: Literal[100] = 100
    source_label: str = Field(default="User supplied file; provenance not independently verified", max_length=200)
    exported_at: str | None = Field(None, max_length=50)
    bar_basis: Literal["trade_ohlc", "derived_from_intraday_trades"] = "trade_ohlc"
    rows: list[HistoryRow] = Field(min_length=2, max_length=300)

    @field_validator("symbol", mode="before")
    @classmethod
    def ticker(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("expiry")
    @classmethod
    def expiry_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use an ISO expiration date")
        return value

    @field_validator("exported_at")
    @classmethod
    def export_time(cls, value):
        if value is not None and datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("Export time requires a timezone")
        return value

    @model_validator(mode="after")
    def unique_observations(self):
        identities = [(row.trading_date, row.strike, row.right) for row in self.rows]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate contract/date observations; aggregate intraday trades first")
        if any(row.trading_date > self.expiry for row in self.rows):
            raise ValueError("Observation date is after contract expiration")
        return self


def _change(key, label, before, after, unit, enough):
    comparable = enough and before is not None and after is not None
    delta = after - before if comparable else None
    if delta is not None and unit == "fraction":
        delta *= 100
    return {"id": "h.change." + key, "label": label, "value": after,
            "before": before, "after": after, "delta": delta, "unit": unit,
            "delta_unit": "percentage_points" if unit == "fraction" else unit,
            "status": "comparable" if comparable else "incomparable",
            "reason": None if comparable else "insufficient_days_or_common_sample" if not enough else "missing_value_or_oi_asof",
            "direction": "unavailable" if delta is None else "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged"}


def analyze_history(dataset: HistoryDataset, *, source_kind="import", now=None, language="zh"):
    if source_kind not in {"import", "demo", "ibkr_historical"}:
        raise ValueError("Unsupported source kind")
    clock = now or datetime.now(UTC)
    if clock.utcoffset() is None:
        raise ValueError("A timezone-aware clock is required")
    today = clock.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    if any(row.trading_date >= today for row in dataset.rows):
        raise ValueError("Historical review requires dates before today in New York; unfinished sessions are excluded")
    days = sorted({row.trading_date for row in dataset.rows})
    observations = {day: {(row.strike, row.right): row for row in dataset.rows if row.trading_date == day} for day in days}
    all_keys = set().union(*(set(rows) for rows in observations.values()))
    common = set.intersection(*(set(rows) for rows in observations.values()))
    # Retain complete C/P strike pairs across the entire period. Missing rows do
    # not silently change the denominator on individual dates.
    common = {key for key in common if (key[0], "P" if key[1] == "C" else "C") in common}
    daily, evidence = [], []
    for index, day in enumerate(days):
        selected = [observations[day][key] for key in sorted(common)]
        volume_known = bool(selected) and all(row.volume is not None for row in selected)
        volume = sum(row.volume for row in selected) if volume_known else None
        put_volume = sum(row.volume for row in selected if row.right == "P") if volume_known else None
        oi_dates = {row.oi_asof_date for row in selected}
        oi_known = bool(selected) and len(oi_dates) == 1 and None not in oi_dates and all(row.open_interest is not None for row in selected)
        oi = sum(row.open_interest for row in selected) if oi_known else None
        put_oi = sum(row.open_interest for row in selected if row.right == "P") if oi_known else None
        item = {"date": day, "received_contracts": len(observations[day]), "common_contracts": len(common),
                "volume_total": volume, "put_volume_share": put_volume / volume if volume is not None and volume > 0 else None,
                "oi_total": oi, "put_oi_share": put_oi / oi if oi is not None and oi > 0 else None,
                "oi_asof_date": next(iter(oi_dates)) if oi_known else None}
        daily.append(item)
        for key, label, unit in (("volume_total", "配对样本报告成交计数", "contracts"),
                                 ("put_volume_share", "配对样本看跌成交占比", "fraction"),
                                 ("oi_total", "配对样本未平仓量", "contracts"),
                                 ("put_oi_share", "配对样本看跌持仓占比", "fraction")):
            evidence.append({"id": f"h.day.{index}.{key}", "label": label, "value": item[key], "unit": unit,
                             "trading_date": day, "oi_asof_date": item["oi_asof_date"] if key.startswith("oi") or key == "put_oi_share" else None,
                             "description": f"{day}；固定共同配对样本。缺失不同于零；持仓有独立统计时点。"})
    enough = len(days) >= 2 and bool(common)
    changes = [_change(key, label, daily[0][key], daily[-1][key], unit, enough) for key, label, unit in (
        ("volume_total", "样本成交计数的首尾变化", "contracts"), ("put_volume_share", "样本看跌成交占比的首尾变化", "fraction"),
        ("oi_total", "样本未平仓量的首尾变化", "contracts"), ("put_oi_share", "样本看跌持仓占比的首尾变化", "fraction"))]
    if dataset.bar_basis == "derived_from_intraday_trades":
        for item in changes:
            if "volume" in item["id"]:
                item.update(status="incomparable", reason="historical_bar_coverage_unverified", delta=None, direction="unavailable")
    # Independent OI reporting dates must actually advance before their totals
    # are compared. Repeated reports are not new daily positioning.
    for item in changes:
        if "oi" in item["id"] and item["status"] == "comparable" and daily[-1]["oi_asof_date"] <= daily[0]["oi_asof_date"]:
            item.update(status="incomparable", reason="oi_asof_not_advanced", delta=None, direction="unavailable")
    contract_changes = []
    for strike, right in sorted(common):
        first, last = observations[days[0]][(strike, right)].close, observations[days[-1]][(strike, right)].close
        eligible = enough and first is not None and first > 0 and last is not None
        change_pct = (last / first - 1) * 100 if eligible else None
        if change_pct is not None and not math.isfinite(change_pct):
            change_pct = None
        contract_changes.append({"strike": strike, "right": right, "before": first, "after": last,
                                 "change_pct": change_pct,
                                 "status": "comparable" if change_pct is not None else "incomparable"})
        price_change = _change(f"contract_{len(contract_changes)-1}_trade_close", f"{strike:g}{right} 所收成交记录末值变化", first, last, "USD", eligible)
        price_change.update(id=f"h.contract.{len(contract_changes)-1}.trade_close", trading_date=days[-1], previous_trading_date=days[0],
                            description="只比较同一份合约的首尾所收成交记录末值；每股报价单位，不是结算价、同步报价或当前价格。")
        evidence.append(price_change)
    source = {"kind": source_kind, "label": "Synthetic teaching example / 合成教学示例" if source_kind == "demo" else dataset.source_label,
              "verified": source_kind == "ibkr_historical", "exported_at": dataset.exported_at}
    limits = ["这段数据只用于历史复盘，不能代表当前市场，也不能预测收益。",
              "仅代表所选合约；不等于整个市场或完整历史期权链，选样可能存在偏差。",
              "看涨/看跌成交不是多空人数；每笔成交都有买方和卖方。",
              "历史成交 OHLC 不是同步双边报价，不用于判断当前可成交价差。",
              "未平仓量有独立报告周期，不能将变化解释成资金流入或新开仓方向。"]
    if source_kind == "import":
        limits.insert(0, "文件由用户提供，来源、交易所日历与数据完整性未独立核验。")
    elif source_kind == "demo":
        limits.insert(0, "这是明确标注的合成教学样本，不是真实市场记录。")
    if dataset.bar_basis == "derived_from_intraday_trades":
        limits.append("交易日摘要由收到的盘中成交 bars 汇总，不是官方期权 EOD/结算价，也不保证覆盖完整交易时段。")
    if len(common) < len(all_keys):
        limits.append("跨日期存在缺失合约；联合比较仅保留全期共同的看涨/看跌配对，未把缺失当作零。")
    if any(item["oi_total"] is None for item in daily):
        limits.append("部分未平仓量或独立 as-of 日期缺失；对应指标不生成变化结论。")
    if len(days) < 2:
        limits.append("只有一个日期，无法计算跨日变化。")
    brief = [f"复盘区间 {days[0]} 至 {days[-1]}，共 {len(days)} 个提供数据的日期。",
             f"固定共同样本包含 {len(common)} 份合约；所有首尾比较使用相同合约范围。",
             "先看样本成交是否更活跃及分布如何变化，再查看每份合约的历史成交价格。",
             "成交结构与价格变化不能单独证明市场情绪；专家依据和限制可继续追问。"]
    if language == "en":
        brief = [f"Historical period: {days[0]} to {days[-1]}, across {len(days)} supplied dates.",
                 f"The fixed common sample contains {len(common)} contracts; endpoint comparisons use the same paired contracts.",
                 "Review reported activity and individual contract trade-price changes before drawing conclusions.",
                 "Activity is not market sentiment. Ask about expert evidence and the limitations."]
    digest = hashlib.sha256(dataset.model_dump_json().encode()).hexdigest()
    for item in evidence + changes:
        item.update(symbol=dataset.symbol, expiry=dataset.expiry, scope="history")
    return {"analysis_kind": "historical_options", "label": dataset.label, "symbol": dataset.symbol,
            "expiry": dataset.expiry, "currency": dataset.currency, "multiplier": dataset.multiplier,
            "ingested_at": clock.isoformat(), "analyzed_at": clock.isoformat(), "source": source,
            "dataset_fingerprint": digest, "bar_basis": dataset.bar_basis,
            "period": {"start": days[0], "end": days[-1]}, "daily": daily, "changes": changes,
            "contract_changes": contract_changes, "evidence": evidence + changes, "limitations": limits,
            "brief": brief, "rows": [row.model_dump() for row in dataset.rows],
            "quality": {"status": "descriptive" if enough else "limited", "provided_contracts": len(all_keys),
                        "common_contracts": len(common), "provided_dates": len(days), "realtime_guaranteed": False}}


def demo_dataset(now=None):
    """Small, explicitly artificial training example, never presented as quotes."""
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo("America/New_York")).date()
    days, cursor = [], today - timedelta(days=1)
    while len(days) < 3:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    rows = []
    for index, day in enumerate(sorted(days)):
        for strike in (100, 105):
            for right in ("C", "P"):
                close = (5 if right == "C" else 4) + index * .2 + (strike - 100) * .05
                rows.append({"trading_date": day.isoformat(), "strike": strike, "right": right,
                             "open": close + .1, "high": close + .4, "low": close - .3, "close": close,
                             "volume": (100 + index * 20) if right == "C" else (80 + index * 40),
                             "open_interest": (700 + index * 10) if right == "C" else (600 + index * 15),
                             "oi_asof_date": day.isoformat()})
    return {"label": "合成教学：历史数据不等于当前行情", "symbol": "DEMO", "expiry": (today + timedelta(days=14)).isoformat(),
            "source_label": "Synthetic teaching example; not market observations", "currency": "USD", "rows": rows}
