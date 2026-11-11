"""The single copy of the legacy quote enrichment (TEAM_STRUCTURE H1).

This reproduces, value for value, the logic previously duplicated in
``analysis.analyze_stock`` and ``workers._enrich_stock_data``. It exists so
that there is one place to change.

WARNING — the ``rsi`` and ``ma_20`` produced here when the data source supplies
none are single-day proxies, not a 14-period RSI or a 20-day average
(IMPLEMENTATION_STATUS R1). They are kept only because changing what the
existing cards show needs the user's decision (D4). Real indicators are in
:mod:`quant.indicators`. Floats are used because this feeds the display cache,
never portfolio arithmetic.
"""
from __future__ import annotations

from typing import Mapping

RSI_PROXY_FLOOR = 5
RSI_PROXY_CEILING = 95
HIGH_VOLATILITY_MOVE_PCT = 5
MEDIUM_VOLATILITY_MOVE_PCT = 2
BUYABLE_MIN_CHANGE_PCT = 0.5
BUYABLE_MAX_RSI = 65


def resolve_rsi(supplied_rsi: float, change_pct: float) -> float:
    """The supplied RSI, or the legacy proxy ``clamp(50 + 3 x change, 5, 95)`` when there is none."""
    if supplied_rsi:
        return supplied_rsi
    return max(RSI_PROXY_FLOOR, min(RSI_PROXY_CEILING, 50 + (change_pct * 3)))


def resolve_ma_20(supplied_ma_20: float, price: float, change_pct: float) -> float:
    """The supplied 20-day average, or the legacy proxy ``price x (1 - change / 200)``."""
    if supplied_ma_20:
        return supplied_ma_20
    return price * (1 - change_pct / 200) if price else 0


def classify_volatility(change_pct: float) -> str:
    """LOW / MEDIUM / HIGH from the size of one day's move (a label, not a volatility measure)."""
    if abs(change_pct) > HIGH_VOLATILITY_MOVE_PCT:
        return "HIGH"
    if abs(change_pct) > MEDIUM_VOLATILITY_MOVE_PCT:
        return "MEDIUM"
    return "LOW"


def signal_text(change_pct: float, rsi: float) -> str:
    """Rule-based label shown as ``prediction`` / ``reason``. Rule order matters."""
    if change_pct > 5 and rsi < 70:
        return f"PURCHASABLE — strong momentum +{change_pct:.1f}%"
    if change_pct > 2 and rsi < 65:
        return f"PURCHASABLE — positive trend +{change_pct:.1f}%"
    if change_pct > 0.5 and rsi < 60:
        return f"PURCHASABLE — rising +{change_pct:.1f}%"
    if rsi < 35:
        return "ACCUMULATE — oversold, potential bounce"
    if change_pct >= 0 and rsi < 55:
        return "ACCUMULATE — steady upward movement"
    if change_pct >= 0 and rsi < 65:
        return "WATCH TO BUY — conditions improving"
    if rsi > 72 and change_pct > 3:
        return f"TAKE PROFITS — up {change_pct:.1f}%, overbought"
    if rsi > 65:
        return "WATCH TO BUY — slightly overbought, wait for pullback"
    if change_pct < -2:
        return f"AVOID FOR NOW — declining {change_pct:.1f}%"
    if change_pct < 0 and rsi > 40:
        return "WATCH TO BUY — minor dip, monitor closely"
    if change_pct < 0 and rsi < 40:
        return "ACCUMULATE — dip into value zone"
    return "WATCH TO BUY — neutral, awaiting direction"


def is_favorable(change_pct: float) -> bool:
    return change_pct > 0


def is_buyable(change_pct: float, rsi: float) -> bool:
    return change_pct > BUYABLE_MIN_CHANGE_PCT and rsi < BUYABLE_MAX_RSI


def enrich_quote(data: Mapping[str, object], market_type: str, currency: str) -> dict:
    """Return a copy of a raw provider quote with the analysis fields added.

    Drop-in replacement for ``workers._enrich_stock_data`` except that the
    input is not modified.
    """
    price = data.get("price", 0)
    change_pct = data.get("change_pct", 0)
    rsi = resolve_rsi(data.get("rsi", 0), change_pct)
    ma_20 = resolve_ma_20(data.get("ma_20", 0), price, change_pct)
    prediction = signal_text(change_pct, rsi)

    return {
        **data,
        "currency": currency,
        "market_type": market_type,
        "rsi": round(rsi, 2),
        "ma_20": round(ma_20, 2) if ma_20 else 0,
        "volatility": classify_volatility(change_pct),
        "prediction": prediction,
        "reason": prediction,
        "is_favorable": is_favorable(change_pct),
        "is_buyable": is_buyable(change_pct, rsi),
    }
