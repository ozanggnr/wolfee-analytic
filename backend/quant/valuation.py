"""Mark positions to market and convert them into the portfolio's base currency.

Nothing is estimated: a position without a usable quote or FX rate keeps
``None`` for the affected figures and names the reason, and portfolio totals
are ``None`` until every position can be valued.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Mapping, Sequence

from quant._math import ZERO, fixed_context, to_decimal, weights_summing_to_one
from quant.types import FxRate, PortfolioValuation, Position, PriceQuote, ValuedPosition

MISSING_QUOTE = "missing_quote"
QUOTE_CURRENCY_MISMATCH = "quote_currency_mismatch"
MISSING_FX_RATE = "missing_fx_rate"
QUOTE_SYMBOL_MISMATCH = "quote_symbol_mismatch"
INVALID_QUOTE_PRICE = "invalid_quote_price"


@fixed_context()
def value_positions(
    positions: Sequence[Position],
    quotes: Mapping[str, PriceQuote],
    fx: Mapping[str, FxRate],
    base_currency: str,
) -> PortfolioValuation:
    """Value ``positions`` with ``quotes`` (keyed by symbol).

    ``fx`` maps a currency code to the rate that converts it into
    ``base_currency`` (``FxRate(base=currency, quote=base_currency)``).
    Positions already in the base currency need no rate. Unrealised P/L in base
    currency compares today's converted value with the cost converted at each
    trade's stored rate, so it includes the currency effect.

    Quotes are used whatever their ``freshness``; the label travels with each
    valued position so the caller can show it.
    """
    _validate_fx(fx, base_currency)
    valued = [
        _value_one(position, quotes.get(position.symbol), fx, base_currency)
        for position in sorted(positions, key=lambda p: p.symbol)
    ]

    unvalued = tuple(v.symbol for v in valued if v.market_value_base is None)
    is_complete = not unvalued
    total_value = _sum_or_none([v.market_value_base for v in valued]) if is_complete else None
    total_cost = _sum_or_none([v.cost_basis_base for v in valued])
    total_pnl = None if total_value is None or total_cost is None else total_value - total_cost

    return PortfolioValuation(
        base_currency=base_currency,
        positions=_with_weights(valued) if is_complete else tuple(valued),
        total_market_value=total_value,
        total_cost_basis=total_cost,
        total_unrealized_pnl=total_pnl,
        is_complete=is_complete,
        unvalued_symbols=unvalued,
    )


def _validate_fx(fx: Mapping[str, FxRate], base_currency: str) -> None:
    for currency, rate in fx.items():
        if rate.base != currency or rate.quote != base_currency:
            raise ValueError(
                f"FX rate for {currency} must be quoted as {currency}/{base_currency}, "
                f"got {rate.base}/{rate.quote}"
            )
        if to_decimal(rate.rate, "fx rate") <= ZERO:
            raise ValueError(f"FX rate {currency}/{base_currency} must be positive")


def _value_one(
    position: Position, quote: PriceQuote | None, fx: Mapping[str, FxRate], base_currency: str
) -> ValuedPosition:
    in_base = position.currency == base_currency
    # A base-currency position converts at exactly 1, stored rate or not.
    cost_base = position.cost_basis if in_base else position.cost_basis_base
    result = ValuedPosition(
        symbol=position.symbol,
        currency=position.currency,
        quantity=position.quantity,
        cost_basis=position.cost_basis,
        cost_basis_base=cost_base,
        quote=quote,
        fx_rate=None,
        market_value=None,
        unrealized_pnl=None,
        market_value_base=None,
        unrealized_pnl_base=None,
        weight=None,
        unavailable_reason=None,
    )

    if quote is None:
        return replace(result, unavailable_reason=MISSING_QUOTE)
    if quote.symbol != position.symbol:
        return replace(result, unavailable_reason=QUOTE_SYMBOL_MISMATCH)
    if quote.currency != position.currency:
        return replace(result, unavailable_reason=QUOTE_CURRENCY_MISMATCH)
    price = to_decimal(quote.price, "quote price")
    if price <= ZERO:
        return replace(result, unavailable_reason=INVALID_QUOTE_PRICE)

    market_value = position.quantity * price
    result = replace(
        result, market_value=market_value, unrealized_pnl=market_value - position.cost_basis
    )

    rate = None if in_base else fx.get(position.currency)
    if not in_base and rate is None:
        return replace(result, unavailable_reason=MISSING_FX_RATE)

    value_base = market_value if in_base else market_value * rate.rate
    return replace(
        result,
        fx_rate=rate,
        market_value_base=value_base,
        unrealized_pnl_base=None if cost_base is None else value_base - cost_base,
    )


def _sum_or_none(values: Sequence[Decimal | None]) -> Decimal | None:
    if any(value is None for value in values):
        return None
    return sum(values, ZERO)


def _with_weights(valued: Sequence[ValuedPosition]) -> tuple[ValuedPosition, ...]:
    weights = weights_summing_to_one([v.market_value_base for v in valued])
    if weights is None:
        return tuple(valued)
    return tuple(replace(v, weight=weight) for v, weight in zip(valued, weights))
