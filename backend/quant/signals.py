"""The single copy of the quote enrichment behind market cards (TEAM_STRUCTURE H1).

Decision D4: nothing here is estimated. RSI, the 20-day average and volatility
come from real daily closes through :mod:`quant.indicators`, or they are
``None``. A missing day high or low stays ``None``. Every label built on those
figures (``prediction`` / ``reason``, ``is_buyable``, ``is_favorable``) is
``None`` whenever the RSI it needs is unavailable.

``prediction`` / ``reason`` describe the indicators ("RSI above 70
(overbought)", "Near 20-day average"); they never tell the reader to buy, hold
or sell. ``is_buyable`` and ``is_favorable`` remain as data fields.

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
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
# Price within this many percent of the 20-day average is described as "near" it.
NEAR_AVERAGE_PCT = 2
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


def indicator_label(
    rsi: float | None, price: float | None = None, ma_20: float | None = None
) -> str | None:
    """Descriptive label shown as ``prediction`` / ``reason``; None without a real RSI.

    It states what the indicators are and recommends nothing. The RSI bands
    come first; inside them the label places the price against the 20-day
    average when both are known.
    """
    if rsi is None:
        return None
    if rsi < RSI_OVERSOLD:
        return f"RSI below {RSI_OVERSOLD} (oversold)"
    if rsi > RSI_OVERBOUGHT:
        return f"RSI above {RSI_OVERBOUGHT} (overbought)"
    if not price or not ma_20:
        return f"RSI between {RSI_OVERSOLD} and {RSI_OVERBOUGHT}"
    if abs(price - ma_20) <= ma_20 * NEAR_AVERAGE_PCT / 100:
        return "Near 20-day average"
    return "Above 20-day average" if price > ma_20 else "Below 20-day average"


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
    None. ``prediction`` / ``reason`` need the RSI; the two flags need the
    day's change as well. Any ``rsi`` or ``ma_20`` already present in ``data`` is ignored: it
    may be an old estimate. ``day_high`` and ``day_low`` are None unless the
    provider supplied them. The input is not modified.
    """
    indicators = daily_indicators(history)
    rsi = _rounded(indicators.rsi_14)
    volatility_pct = _rounded(indicators.volatility_pct)
    change_pct = _number(data.get("change_pct"))
    ma_20 = _rounded(indicators.sma_20)
    prediction = indicator_label(rsi, _number(data.get("price")), ma_20)
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
        "ma_20": ma_20,
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
