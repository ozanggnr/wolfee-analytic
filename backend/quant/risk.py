"""Portfolio risk metrics from a series of daily portfolio values.

Returns are time-weighted: cash deposited or withdrawn on a day is removed
before that day's return is measured, so adding money is not counted as
performance. A flow is treated as arriving at the close of the day it is
recorded on, so it earns nothing that day:
``return = (value - net_flow) / previous value - 1``.

Every value except the last must be positive. A history that passes through
zero (everything sold, money added later) has to be split by the caller into
separate funded periods.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from quant._math import (
    CONTEXT, HUNDRED, ONE, ZERO, divide, fixed_context, require_positive_int, sample_stdev, to_decimal,
)
from quant.indicators import TRADING_DAYS_PER_YEAR
from quant.types import DatedValue, RiskMetrics


@fixed_context()
def risk_metrics(
    daily_values: Sequence[DatedValue], periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> RiskMetrics:
    """Period return, volatility and maximum drawdown of ``daily_values``.

    Fields that need more history than supplied are None: a return needs two
    values, volatility needs three.
    """
    require_positive_int(periods_per_year, "periods_per_year")
    series = _validated(daily_values)
    if len(series) < 2:
        return _empty(series)

    returns = [
        divide(today.value - today.net_flow, yesterday.value) - ONE
        for yesterday, today in zip(series, series[1:])
    ]
    index = [ONE]
    for period_return in returns:
        index.append(CONTEXT.multiply(index[-1], ONE + period_return))

    drawdown, peak_date, trough_date = _max_drawdown(index, [point.date for point in series])
    deviation = sample_stdev(returns)
    annual_factor = CONTEXT.sqrt(Decimal(periods_per_year))

    return RiskMetrics(
        observations=len(series),
        start=series[0].date,
        end=series[-1].date,
        period_return_pct=(index[-1] - ONE) * HUNDRED,
        daily_volatility_pct=None if deviation is None else deviation * HUNDRED,
        annualized_volatility_pct=(
            None if deviation is None else CONTEXT.multiply(deviation * HUNDRED, annual_factor)
        ),
        max_drawdown_pct=drawdown * HUNDRED,
        max_drawdown_peak=peak_date,
        max_drawdown_trough=trough_date,
    )


def _validated(daily_values: Sequence[DatedValue]) -> list[DatedValue]:
    series = sorted(daily_values, key=lambda point: point.date)
    for earlier, later in zip(series, series[1:]):
        if earlier.date == later.date:
            raise ValueError(f"more than one value for {earlier.date}")
    for position, point in enumerate(series):
        value = to_decimal(point.value, "value")
        to_decimal(point.net_flow, "net_flow")
        is_last = position == len(series) - 1
        if value < ZERO or (value == ZERO and not is_last):
            raise ValueError(f"portfolio value on {point.date} must be positive to measure a return")
        if position > 0 and value - point.net_flow < ZERO:
            raise ValueError(f"net_flow on {point.date} is larger than the portfolio value that day")
    return series


def _empty(series: Sequence[DatedValue]) -> RiskMetrics:
    return RiskMetrics(
        observations=len(series),
        start=series[0].date if series else None,
        end=series[-1].date if series else None,
        period_return_pct=None,
        daily_volatility_pct=None,
        annualized_volatility_pct=None,
        max_drawdown_pct=None,
        max_drawdown_peak=None,
        max_drawdown_trough=None,
    )


def _max_drawdown(
    index: Sequence[Decimal], dates: Sequence[date]
) -> tuple[Decimal, date | None, date | None]:
    """Largest peak-to-trough fall of the return index, as a positive fraction."""
    worst = ZERO
    worst_peak: date | None = None
    worst_trough: date | None = None
    peak = index[0]
    peak_date = dates[0]

    for level, day in zip(index, dates):
        if level > peak:
            peak, peak_date = level, day
        fall = divide(peak - level, peak)
        if fall > worst:
            worst, worst_peak, worst_trough = fall, peak_date, day

    return worst, worst_peak, worst_trough
