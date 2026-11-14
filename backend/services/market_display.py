"""Null-safe display of market indicators (decision D4, REQ-24 support).

rsi, ma_20, the day range and volatility are None until they are computed from
real price history (Agent 3's REQ-24). These helpers keep None as None in JSON
responses and write "Not available" in exports. Nothing is estimated here: a
missing or malformed value is reported as missing.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Union

NOT_AVAILABLE = "Not available"

ExportCell = Union[float, str]

RSI_OVERSOLD_BELOW = 30
RSI_OVERBOUGHT_ABOVE = 70


def number(value: Any) -> Optional[float]:
    """A finite int or float as float; anything else (None, text, NaN, bool) is None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def rounded(value: Any, digits: int) -> Optional[float]:
    found = number(value)
    return None if found is None else round(found, digits)


def price_level(value: Any, digits: int = 2) -> Optional[float]:
    """A day high/low or moving average. The legacy cache stored 0 for "missing", and
    no traded price is 0 or below, so those are None as well."""
    found = rounded(value, digits)
    return found if found is not None and found > 0 else None


def cell(value: Optional[float]) -> ExportCell:
    return NOT_AVAILABLE if value is None else value


def rsi_status(rsi: Any) -> str:
    found = number(rsi)
    if found is None:
        return NOT_AVAILABLE
    if found < RSI_OVERSOLD_BELOW:
        return "Oversold"
    return "Overbought" if found > RSI_OVERBOUGHT_ABOVE else "Neutral"


def volatility_cell(value: Any) -> ExportCell:
    """A computed volatility (a number) or a legacy label; otherwise not available."""
    found = rounded(value, 2)
    if found is not None:
        return found
    return value.strip() if isinstance(value, str) and value.strip() else NOT_AVAILABLE


def _trend(prediction: Any, change_pct: float) -> str:
    if prediction:
        return str(prediction)
    if change_pct > 0:
        return f"📈 UP +{change_pct:.1f}%"
    if change_pct < 0:
        return f"📉 DOWN {change_pct:.1f}%"
    return "➖ Stable"


def portfolio_export_row(stock: Mapping[str, Any], period: str, today: str, symbol: str = "") -> dict:
    """One row of the portfolio Excel export from a quote/analysis dict."""
    symbol = str(stock.get("symbol") or stock.get("ticker") or symbol)
    price = number(stock.get("price")) or 0.0
    change_pct = number(stock.get("change_pct")) or 0.0
    change_amt = price * (change_pct / 100) if price else 0.0
    previous_close = number(stock.get("previous_close"))
    start_price = previous_close if previous_close else price - change_amt
    rsi = rounded(stock.get("rsi"), 2)
    return {
        "Symbol": symbol,
        "Currency": stock.get("currency") or "USD",
        "Name": stock.get("name") or symbol,
        "Report Period": period.capitalize(),
        "Analysis Date": today,
        "Trend": _trend(stock.get("prediction"), change_pct),
        "Current Price": round(price, 2),
        "Start Price": round(start_price, 2),
        "Change %": round(change_pct, 2),
        "Change Amt": round(change_amt, 2),
        "Period High": cell(price_level(stock.get("day_high")) or price_level(stock.get("high"))),
        "High Date": today,
        "Period Low": cell(price_level(stock.get("day_low")) or price_level(stock.get("low"))),
        "Low Date": today,
        "RSI (14)": cell(rsi),
        "RSI Status": rsi_status(rsi),
        "Volatility %": volatility_cell(stock.get("volatility")),
        "MA(20)": cell(price_level(stock.get("ma_20"))),
        "Volume (Period)": number(stock.get("volume")) or 0,
    }


def unavailable_export_row(symbol: str, period: str, today: str) -> dict:
    """The row for a symbol whose data could not be fetched: every value not available."""
    row = portfolio_export_row({"symbol": symbol}, period, today)
    numeric = ("Current Price", "Start Price", "Change %", "Change Amt", "Volume (Period)")
    return {**row, **{column: NOT_AVAILABLE for column in numeric},
            "Currency": NOT_AVAILABLE, "Trend": NOT_AVAILABLE}


_PROVENANCE_FIELDS = ("indicators_as_of", "indicator_method", "volatility_pct")


def stock_card(stock: Any) -> dict:
    """The ``Stock`` object of API_CONTRACT §2.2 from a ``stock_data`` row.

    rsi, ma_20, the day range, volatility and the labels built on them stay null
    until computed from real history (D4); they are never filled in here. The
    indicator provenance is read from ``extra_data``, where the workers keep it.
    """
    stored = stock.extra_data if isinstance(stock.extra_data, dict) else {}
    return {
        "symbol": stock.symbol,
        "name": stock.name or stock.symbol,
        "price": stock.price or 0,
        "change_pct": stock.change_pct or 0,
        "volume": stock.volume or 0,
        "day_high": stock.day_high,
        "day_low": stock.day_low,
        "open": stock.open_price or 0,
        "previous_close": stock.previous_close or 0,
        "bid": stock.bid or 0,
        "ask": stock.ask or 0,
        "rsi": stock.rsi,
        "ma_20": stock.ma_20,
        "volatility": stock.volatility,
        **{field: stored.get(field) for field in _PROVENANCE_FIELDS},
        # Cache rows are enriched from real history only (REQ-10), so nothing is estimated.
        "estimated_fields": [],
        "currency": stock.currency or "USD",
        "market_type": stock.market_type or "GLOBAL",
        "prediction": stock.prediction,
        "reason": stock.reason,
        "is_favorable": stock.is_favorable,
        "is_buyable": stock.is_buyable,
        "market_cap": stock.market_cap or 0,
    }
