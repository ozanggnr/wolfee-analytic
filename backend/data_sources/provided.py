"""Values exactly as a provider supplied them (REQ-30, user decision 2026-11-14).

A missing, zero, negative or non-finite open / previous close is ``None``: it is
never replaced by 0.0, by the current price, or by anything derived from the
day's change. The day's change itself is ``None`` without a previous close.
"""
from __future__ import annotations

import math
from typing import Any, Optional


def provided_price(value: Any) -> Optional[float]:
    """A positive, finite price as float; None when the provider gave none."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


CHART_DECIMALS = 4


def chart_level(value: Any) -> Optional[float]:
    """One open / high / low / close of a chart bar, rounded; None when the provider gave none.

    A missing open, high or low is never filled with the bar's close: a bar
    drawn from a repeated close would show a range that was not observed.
    """
    number = provided_price(value)
    return None if number is None else round(number, CHART_DECIMALS)


def chart_row(time: str, open_: Any, high: Any, low: Any, close: Any, volume: Any) -> Optional[dict]:
    """A chart bar, or None when it has no close. A missing volume is 0, as before."""
    close_level = chart_level(close)
    if close_level is None:
        return None
    return {
        "time": time,
        "open": chart_level(open_),
        "high": chart_level(high),
        "low": chart_level(low),
        "close": close_level,
        "volume": int(volume) if provided_price(volume) is not None else 0,
    }


def daily_change_pct(price: Any, previous_close: Any) -> Optional[float]:
    """The day's change in percent against the previous close, to two decimals.

    None when there is no previous close (or no price): the change is unknown
    then, which is not the same as 0.0.
    """
    current, previous = provided_price(price), provided_price(previous_close)
    if current is None or previous is None:
        return None
    return round((current - previous) / previous * 100, 2)
