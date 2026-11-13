"""Holdings and performance of one portfolio, computed by the quant package.

This module loads the caller's ledger, cached quotes and FX rates, hands them to
quant, and shapes the results. Realised P/L is summed by quant.sum_realized
(REQ-17). The only arithmetic left here is the portfolio totals over the positions
that could be valued; nothing is estimated.

FX (decision D3): foreign positions convert into TRY at the cached TCMB rate. A
position without a usable quote or rate is reported unvalued, and the totals
cover the remaining positions only, with `is_complete` false.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from models import Instrument, Portfolio
from quant.positions import build_positions, cash_summary, realized_pnl, sum_realized
from quant.types import (
    CostBasisMethod, CurrencyAmount, FxRate, LedgerError, PortfolioValuation, PriceQuote,
    RealizedLot, ValuedPosition,
)
from quant.valuation import value_positions
from repositories import transaction_repository
from schemas.analytics import (
    CurrencyAmountOut, FxRateOut, HoldingOut, HoldingsOut, PerformanceOut, QuoteOut, RealizedLotOut,
)
from services import fx_service, ledger_adapter, portfolio_service, quote_service
from services.errors import ConflictError

# Decision D2: weighted average by default, FIFO as a parameter.
DEFAULT_COST_BASIS_METHOD = CostBasisMethod.WEIGHTED_AVERAGE

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Computed:
    portfolio: Portfolio
    method: CostBasisMethod
    computed_at: datetime
    instruments: Mapping[str, Instrument]
    average_costs: Mapping[str, Decimal]
    valuation: PortfolioValuation
    realized: tuple[RealizedLot, ...]
    cash: object  # quant.types.CashSummary


def _replay(ledger: ledger_adapter.Ledger, method: CostBasisMethod):
    positions = build_positions(ledger.transactions, method)
    return positions, tuple(realized_pnl(ledger.transactions, method)), cash_summary(ledger.transactions)


async def _compute(
    db: AsyncSession, user_id: int, portfolio_id: int, method: CostBasisMethod, clock: Clock
) -> _Computed:
    portfolio = await portfolio_service.load_owned(db, user_id, portfolio_id)
    rows = await transaction_repository.all_for_portfolio(db, user_id, portfolio.id)
    ledger = ledger_adapter.to_ledger(rows)
    now = clock()
    try:
        positions, realized, cash = await asyncio.to_thread(_replay, ledger, method)
    except LedgerError as exc:  # writes are checked, so only data written outside the API gets here
        raise ConflictError(f"The stored ledger cannot be replayed: {exc}") from exc

    held = {p.symbol: ledger.instruments[p.symbol] for p in positions}
    base_currency = portfolio.base_currency.strip()
    quotes = await quote_service.latest_quotes(db, held, now)
    fx = await fx_service.rates_to_base(db, {p.currency for p in positions}, base_currency)
    valuation = await asyncio.to_thread(value_positions, positions, quotes, fx, base_currency)
    average_costs = {p.symbol: p.average_cost for p in positions}
    return _Computed(portfolio, method, now, ledger.instruments, average_costs, valuation, realized, cash)


@dataclass(frozen=True)
class _Totals:
    market_value: Optional[Decimal]
    cost_basis: Optional[Decimal]
    unrealized_pnl: Optional[Decimal]


def _sum_or_none(values: Sequence[Optional[Decimal]]) -> Optional[Decimal]:
    if any(v is None for v in values):
        return None
    return sum(values, Decimal(0))


def _totals(valuation: PortfolioValuation) -> _Totals:
    """Quant's totals when every position is valued; otherwise the sum over valued positions."""
    if valuation.is_complete:
        return _Totals(valuation.total_market_value, valuation.total_cost_basis, valuation.total_unrealized_pnl)
    valued = [v for v in valuation.positions if v.market_value_base is not None]
    if not valued:  # nothing could be valued: no total, rather than a misleading zero
        return _Totals(None, None, None)
    return _Totals(
        market_value=_sum_or_none([v.market_value_base for v in valued]),
        cost_basis=_sum_or_none([v.cost_basis_base for v in valued]),
        unrealized_pnl=_sum_or_none([v.unrealized_pnl_base for v in valued]),
    )


def _quote_out(quote: Optional[PriceQuote]) -> Optional[QuoteOut]:
    if quote is None:
        return None
    return QuoteOut(price=quote.price, currency=quote.currency, as_of=quote.as_of,
                    freshness=quote.freshness.value, source=quote.source)


def _fx_out(rate: Optional[FxRate]) -> Optional[FxRateOut]:
    if rate is None:
        return None
    return FxRateOut(base=rate.base, quote=rate.quote, rate=rate.rate, as_of=rate.as_of, source=rate.source)


def _holding_out(valued: ValuedPosition, instrument: Instrument, average_cost: Decimal) -> HoldingOut:
    return HoldingOut(
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        name=instrument.name,
        currency=valued.currency,
        quantity=valued.quantity,
        average_cost=average_cost,
        cost_basis=valued.cost_basis,
        cost_basis_base=valued.cost_basis_base,
        market_value=valued.market_value,
        unrealized_pnl=valued.unrealized_pnl,
        market_value_base=valued.market_value_base,
        unrealized_pnl_base=valued.unrealized_pnl_base,
        weight=valued.weight,
        quote=_quote_out(valued.quote),
        fx_rate=_fx_out(valued.fx_rate),
        unavailable_reason=valued.unavailable_reason,
    )


def _header(computed: _Computed) -> dict:
    instruments = computed.instruments
    return {
        "portfolio_id": computed.portfolio.id,
        "base_currency": computed.portfolio.base_currency.strip(),
        "cost_basis_method": computed.method.value,
        "computed_at": computed.computed_at,
        "is_complete": computed.valuation.is_complete,
        "unvalued_symbols": [instruments[key].symbol for key in computed.valuation.unvalued_symbols],
    }


def _amounts(amounts: Sequence[CurrencyAmount]) -> list[CurrencyAmountOut]:
    return [CurrencyAmountOut(currency=a.currency, amount=a.amount) for a in amounts]


def _lot_out(lot: RealizedLot, instrument: Instrument) -> RealizedLotOut:
    return RealizedLotOut(
        symbol=instrument.symbol, exchange=instrument.exchange, currency=lot.currency,
        quantity=lot.quantity, acquired=lot.acquired, disposed=lot.disposed,
        cost=lot.cost, proceeds=lot.proceeds, pnl=lot.pnl,
        cost_base=lot.cost_base, proceeds_base=lot.proceeds_base, pnl_base=lot.pnl_base,
        buy_transaction_id=lot.buy_transaction_id, sell_transaction_id=lot.sell_transaction_id,
    )


async def holdings(
    db: AsyncSession, user_id: int, portfolio_id: int, method: CostBasisMethod = DEFAULT_COST_BASIS_METHOD,
    clock: Clock = utc_now,
) -> HoldingsOut:
    computed = await _compute(db, user_id, portfolio_id, method, clock)
    valuation = computed.valuation
    totals = _totals(valuation)
    return HoldingsOut(
        **_header(computed),
        positions=[
            _holding_out(v, computed.instruments[v.symbol], computed.average_costs[v.symbol])
            for v in valuation.positions
        ],
        total_market_value=totals.market_value,
        total_cost_basis=totals.cost_basis,
        total_unrealized_pnl=totals.unrealized_pnl,
    )


async def performance(
    db: AsyncSession, user_id: int, portfolio_id: int, method: CostBasisMethod = DEFAULT_COST_BASIS_METHOD,
    clock: Clock = utc_now,
) -> PerformanceOut:
    computed = await _compute(db, user_id, portfolio_id, method, clock)
    cash = computed.cash
    realized = sum_realized(computed.realized, computed.portfolio.base_currency.strip())
    return PerformanceOut(
        **_header(computed),
        realized_pnl=_amounts(realized.by_currency),
        realized_pnl_base=realized.total_base,
        unrealized_pnl_base=_totals(computed.valuation).unrealized_pnl,
        dividends=_amounts(cash.dividends),
        fees=_amounts(cash.fees),
        net_deposits=_amounts(cash.net_deposits),
        cash_balances=_amounts(cash.balances),
        realized_lots=[_lot_out(lot, computed.instruments[lot.symbol]) for lot in computed.realized],
    )
