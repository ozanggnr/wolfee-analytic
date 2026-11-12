"""Mark positions to market and convert them into the portfolio's base currency.

Nothing is estimated: a position or amount without a usable quote or FX rate
keeps ``None`` for the affected figures and names the reason. Totals add up
what could be valued and are flagged as partial (``is_complete`` false) when
something is left out (decision D3).
"""
from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from typing import Mapping, Sequence

from quant._math import ZERO, fixed_context, to_decimal, weights_summing_to_one
from quant.types import (
    DEFAULT_BASE_CURRENCY,
    ConvertedAmount,
    ConvertedAmounts,
    CurrencyAmount,
    FxRate,
    PortfolioValuation,
    Position,
    PriceQuote,
    ValuedPosition,
)

_CURRENCY_CODE = re.compile(r"[A-Z]{3}")

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
    counted = [v for v in valued if v.market_value_base is not None]
    nothing_valued = bool(valued) and not counted
    total_value = None if nothing_valued else sum((v.market_value_base for v in counted), ZERO)
    total_cost = None if nothing_valued else _sum_or_none([v.cost_basis_base for v in counted])
    total_pnl = None if total_value is None or total_cost is None else total_value - total_cost

    return PortfolioValuation(
        base_currency=base_currency,
        positions=_with_weights(valued),
        total_market_value=total_value,
        total_cost_basis=total_cost,
        total_unrealized_pnl=total_pnl,
        is_complete=not unvalued,
        unvalued_symbols=unvalued,
    )


@fixed_context()
def convert_amounts(
    amounts: Sequence[CurrencyAmount],
    fx: Mapping[str, FxRate],
    base_currency: str = DEFAULT_BASE_CURRENCY,
) -> ConvertedAmounts:
    """Convert ``amounts`` into ``base_currency`` with the rates in ``fx``.

    ``fx`` has the same shape as for :func:`value_positions`. An amount whose
    currency has no rate is marked ``missing_fx_rate`` and left out of the
    total; the other amounts are still converted and totalled. Amounts may be
    negative. Items keep the order of ``amounts``.
    """
    _validate_fx(fx, base_currency)
    items = tuple(_convert_one(amount, fx, base_currency) for amount in amounts)

    converted = [item.amount_base for item in items if item.amount_base is not None]
    missing = tuple(sorted({item.currency for item in items if item.amount_base is None}))
    return ConvertedAmounts(
        base_currency=base_currency,
        items=items,
        total_base=None if items and not converted else sum(converted, ZERO),
        is_complete=not missing,
        missing_currencies=missing,
    )


def _convert_one(
    amount: CurrencyAmount, fx: Mapping[str, FxRate], base_currency: str
) -> ConvertedAmount:
    if not isinstance(amount.currency, str) or not _CURRENCY_CODE.fullmatch(amount.currency):
        raise ValueError("currency must be a 3-letter upper-case code")
    value = to_decimal(amount.amount, "amount")
    if amount.currency == base_currency:
        return ConvertedAmount(amount.currency, value, value, None, None)
    rate = fx.get(amount.currency)
    if rate is None:
        return ConvertedAmount(amount.currency, value, None, None, MISSING_FX_RATE)
    return ConvertedAmount(amount.currency, value, value * rate.rate, rate, None)


def _validate_fx(fx: Mapping[str, FxRate], base_currency: str) -> None:
    if not isinstance(base_currency, str) or not _CURRENCY_CODE.fullmatch(base_currency):
        raise ValueError("base currency must be a 3-letter upper-case code")
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
    """Each valued position's share of the valued total; unvalued positions keep ``None``."""
    counted = [v for v in valued if v.market_value_base is not None]
    weights = weights_summing_to_one([v.market_value_base for v in counted])
    if weights is None:
        return tuple(valued)
    weight_of = {v.symbol: weight for v, weight in zip(counted, weights)}
    return tuple(replace(v, weight=weight_of.get(v.symbol)) for v in valued)
