"""Technical indicators computed from real closing prices.

Each function takes closes oldest-first and returns ``None`` when there is not
enough history. Nothing here approximates an indicator from a single day's
move (see ``quant.signals`` for the legacy display proxies).
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Sequence

from quant._math import (
    CONTEXT, HUNDRED, ONE, ZERO, divide, fixed_context, require_positive_int, sample_stdev, to_decimal,
)

TRADING_DAYS_PER_YEAR = 252


class RsiMethod(str, Enum):
    WILDER = "wilder"   # Wilder's smoothing, the convention used by charting platforms
    SIMPLE = "simple"   # plain average of the last ``period`` moves (existing Excel export)


@fixed_context()
def rsi(
    closes: Sequence[Decimal], period: int = 14, method: RsiMethod = RsiMethod.WILDER
) -> Decimal | None:
    """Relative Strength Index of the latest close, 0–100.

    None when fewer than ``period + 1`` closes are given, or when the price did
    not move at all over the window (the ratio is undefined).
    """
    require_positive_int(period, "period")
    prices = _prices(closes)
    if len(prices) < period + 1:
        return None

    deltas = [later - earlier for earlier, later in zip(prices, prices[1:])]
    gains = [max(delta, ZERO) for delta in deltas]
    losses = [max(-delta, ZERO) for delta in deltas]
    span = Decimal(period)

    if method is RsiMethod.SIMPLE:
        average_gain = divide(sum(gains[-period:], ZERO), span)
        average_loss = divide(sum(losses[-period:], ZERO), span)
    else:
        average_gain = divide(sum(gains[:period], ZERO), span)
        average_loss = divide(sum(losses[:period], ZERO), span)
        for gain, loss in zip(gains[period:], losses[period:]):
            average_gain = divide(average_gain * (span - ONE) + gain, span)
            average_loss = divide(average_loss * (span - ONE) + loss, span)

    total = average_gain + average_loss
    if total == ZERO:
        return None
    return divide(HUNDRED * average_gain, total)


@fixed_context()
def sma(closes: Sequence[Decimal], window: int) -> Decimal | None:
    """Simple moving average of the last ``window`` closes."""
    require_positive_int(window, "window")
    prices = _prices(closes)
    if len(prices) < window:
        return None
    return divide(sum(prices[-window:], ZERO), Decimal(window))


@fixed_context()
def annualized_volatility_pct(
    closes: Sequence[Decimal], window: int = 20, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> Decimal | None:
    """Annualised volatility in percent.

    Sample standard deviation of the last ``window`` simple returns, scaled by
    ``sqrt(periods_per_year)``. Needs ``window + 1`` closes.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    require_positive_int(periods_per_year, "periods_per_year")
    prices = _prices(closes)
    if len(prices) < window + 1:
        return None

    recent = prices[-(window + 1):]
    returns = [divide(later, earlier) - ONE for earlier, later in zip(recent, recent[1:])]
    deviation = sample_stdev(returns)
    return CONTEXT.multiply(deviation * HUNDRED, CONTEXT.sqrt(Decimal(periods_per_year)))


def _prices(closes: Sequence[Decimal]) -> list[Decimal]:
    prices = [to_decimal(close, "close") for close in closes]
    if any(price <= ZERO for price in prices):
        raise ValueError("closes must be positive")
    return prices

