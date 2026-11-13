"""Technical indicators computed from real closing prices.

Each function takes closes oldest-first and returns ``None`` when there is not
enough history. Nothing here approximates an indicator from a single day's
move (see ``quant.signals`` for the legacy display proxies).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Sequence

from quant._math import (
    CONTEXT, HUNDRED, ONE, ZERO, divide, fixed_context, require_positive_int, sample_stdev, to_decimal,
)
from quant.types import DailyClose, DailyIndicators

TRADING_DAYS_PER_YEAR = 252

# The windows behind the figures shown on market cards (decision D4).
RSI_PERIOD = 14
SMA_WINDOW = 20
VOLATILITY_WINDOW = 20
INDICATOR_METHOD = (
    "RSI 14 (Wilder), 20-day simple average and 20-day volatility annualised over 252 days, "
    "from daily closing prices"
)


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


@fixed_context()
def daily_indicators(history: Sequence[DailyClose] | None) -> DailyIndicators:
    """RSI 14 (Wilder), SMA 20 and 20-day annualised volatility of the latest daily close.

    ``history`` is real end-of-day closes in any order, one per date. With no
    history every indicator is None; an indicator is also None when the history
    is too short for it (15 closes for RSI, 20 for the average, 21 for
    volatility). Nothing is derived from a single day's move.
    """
    if not history:
        return DailyIndicators(as_of=None, observations=0, rsi_14=None, sma_20=None, volatility_pct=None)

    for point in history:
        if not isinstance(point.date, date) or isinstance(point.date, datetime):
            raise ValueError("history dates must be calendar dates")
    ordered = sorted(history, key=lambda point: point.date)
    if any(earlier.date == later.date for earlier, later in zip(ordered, ordered[1:])):
        raise ValueError("history has more than one close for the same date")

    closes = [point.close for point in ordered]
    return DailyIndicators(
        as_of=ordered[-1].date,
        observations=len(ordered),
        rsi_14=rsi(closes, RSI_PERIOD, RsiMethod.WILDER),
        sma_20=sma(closes, SMA_WINDOW),
        volatility_pct=annualized_volatility_pct(closes, VOLATILITY_WINDOW),
    )


def _prices(closes: Sequence[Decimal]) -> list[Decimal]:
    prices = [to_decimal(close, "close") for close in closes]
    if any(price <= ZERO for price in prices):
        raise ValueError("closes must be positive")
    return prices

