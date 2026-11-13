"""The single copy of the quote enrichment behind market cards (TEAM_STRUCTURE H1).

Decision D4: nothing here is estimated. RSI, the 20-day average and volatility
come from real daily closes through :mod:`quant.indicators`, or they are
``None``. A missing day high or low stays ``None``. Every label built on those
figures (``prediction`` / ``reason``, ``is_buyable``, ``is_favorable``) is
``None`` whenever the RSI it needs is unavailable.

Output values are floats because this feeds the display cache, never portfolio
arithmetic.
"""
from __future__ import annotations

from decimal import Decimal
from numbers import Real
from typing import Mapping, Sequence

from quant.indicators import INDICATOR_METHOD, daily_indicators
from quant.types import DailyClose

# Annualised volatility, in percent, at which the label changes.
MEDIUM_VOLATILITY_PCT = 25
HIGH_VOLATILITY_PCT = 50
BUYABLE_MIN_CHANGE_PCT = 0.5
BUYABLE_MAX_RSI = 65


def classify_volatility(volatility_pct: float | Decimal | None) -> str | None:
    """LOW / MEDIUM / HIGH from annualised volatility in percent; None when it is unknown."""
    if volatility_pct is None:
        return None
    if volatility_pct >= HIGH_VOLATILITY_PCT:
        return "HIGH"
    if volatility_pct >= MEDIUM_VOLATILITY_PCT:
        return "MEDIUM"
    return "LOW"


def signal_text(change_pct: float | None, rsi: float | None) -> str | None:
    """Rule-based label shown as ``prediction`` / ``reason``; None without a real RSI.

    Rule order matters.
    """
    if change_pct is None or rsi is None:
        return None
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


def is_favorable(change_pct: float | None, rsi: float | None) -> bool | None:
    """Whether the day's move is positive; None without a real RSI (D4: labels follow their inputs)."""
    if change_pct is None or rsi is None:
        return None
    return change_pct > 0


def is_buyable(change_pct: float | None, rsi: float | None) -> bool | None:
    if change_pct is None or rsi is None:
        return None
    return change_pct > BUYABLE_MIN_CHANGE_PCT and rsi < BUYABLE_MAX_RSI


def enrich_quote(
    data: Mapping[str, object],
    market_type: str,
    currency: str,
    history: Sequence[DailyClose] | None = None,
) -> dict:
    """Return a copy of a raw provider quote with the analysis fields added.

    ``history`` is the instrument's real daily closes (any order, one per
    date). Without it ``rsi``, ``ma_20``, ``volatility``, ``volatility_pct``,
    ``prediction``, ``reason``, ``is_favorable`` and ``is_buyable`` are all
    None. Any ``rsi`` or ``ma_20`` already present in ``data`` is ignored: it
    may be an old estimate. ``day_high`` and ``day_low`` are None unless the
    provider supplied them. The input is not modified.
    """
    indicators = daily_indicators(history)
    rsi = _rounded(indicators.rsi_14)
    volatility_pct = _rounded(indicators.volatility_pct)
    change_pct = _number(data.get("change_pct"))
    prediction = signal_text(change_pct, rsi)
    has_indicator = any(
        value is not None for value in (indicators.rsi_14, indicators.sma_20, indicators.volatility_pct)
    )

    return {
        **data,
        "currency": currency,
        "market_type": market_type,
        "day_high": _number(data.get("day_high")) or None,
        "day_low": _number(data.get("day_low")) or None,
        "rsi": rsi,
        "ma_20": _rounded(indicators.sma_20),
        "volatility": classify_volatility(volatility_pct),
        "volatility_pct": volatility_pct,
        "prediction": prediction,
        "reason": prediction,
        "is_favorable": is_favorable(change_pct, rsi),
        "is_buyable": is_buyable(change_pct, rsi),
        "indicators_as_of": indicators.as_of.isoformat() if has_indicator else None,
        "indicator_method": INDICATOR_METHOD if has_indicator else None,
    }


def _rounded(value: Decimal | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _number(value: object) -> float | None:
    """``value`` if it is a real, finite number; otherwise None."""
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None
