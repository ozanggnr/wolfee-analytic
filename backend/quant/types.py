"""Immutable value types exchanged between ``quant`` and its callers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

_ZERO = Decimal(0)


class LedgerError(ValueError):
    """A transaction ledger that cannot be replayed (invalid or inconsistent rows)."""


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    FEE = "FEE"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    SPLIT = "SPLIT"


class CostBasisMethod(str, Enum):
    FIFO = "fifo"
    WEIGHTED_AVERAGE = "weighted_average"


# Decisions D2 and D3 (2026-11-11).
DEFAULT_COST_BASIS_METHOD = CostBasisMethod.WEIGHTED_AVERAGE
DEFAULT_BASE_CURRENCY = "TRY"


class Freshness(str, Enum):
    REALTIME = "realtime"
    DELAYED = "delayed"
    END_OF_DAY = "end_of_day"
    STALE = "stale"


@dataclass(frozen=True)
class Transaction:
    """One ledger row (DATABASE_CONTRACT §3.3), already mapped to a symbol.

    Field meaning by type:

    * BUY / SELL  — ``quantity`` units at ``price`` each, plus ``fee``.
    * DIVIDEND    — ``quantity`` units paying ``price`` each; ``fee`` is tax or
      charges withheld. Cash received is ``quantity * price - fee``.
    * SPLIT       — ``quantity`` is the ratio of new units per old unit
      (2 for a 2-for-1 split, 0.5 for a 1-for-2 reverse split).
    * DEPOSIT / WITHDRAWAL — ``quantity`` is the cash amount in ``currency``.
    * FEE         — ``fee`` is the amount charged.

    ``fx_rate_to_base`` is the rate stored at trade time: one unit of
    ``currency`` in the portfolio's base currency. A row whose
    ``voids_transaction_id`` is set is a reversal: it and its target are both
    ignored.
    """

    id: int
    type: TransactionType
    trade_date: date
    currency: str
    quantity: Decimal = _ZERO
    price: Decimal | None = None
    fee: Decimal = _ZERO
    symbol: str | None = None
    fx_rate_to_base: Decimal | None = None
    voids_transaction_id: int | None = None


@dataclass(frozen=True)
class Lot:
    """Units still held from one purchase (FIFO) or the pooled holding (weighted average)."""

    quantity: Decimal
    cost: Decimal
    cost_base: Decimal | None
    acquired: date
    transaction_id: int | None


@dataclass(frozen=True)
class Position:
    symbol: str
    currency: str
    quantity: Decimal
    cost_basis: Decimal
    average_cost: Decimal
    cost_basis_base: Decimal | None
    lots: tuple[Lot, ...] = ()


@dataclass(frozen=True)
class RealizedLot:
    """Profit or loss locked in by selling units of one lot."""

    symbol: str
    currency: str
    quantity: Decimal
    acquired: date
    disposed: date
    cost: Decimal
    proceeds: Decimal
    pnl: Decimal
    cost_base: Decimal | None
    proceeds_base: Decimal | None
    pnl_base: Decimal | None
    buy_transaction_id: int | None
    sell_transaction_id: int


@dataclass(frozen=True)
class CurrencyAmount:
    currency: str
    amount: Decimal


@dataclass(frozen=True)
class CashSummary:
    """Cash effects of a ledger, per currency, each sorted by currency code.

    ``fees`` covers BUY, SELL and FEE rows. BUY fees are also part of cost
    basis and SELL fees already reduce proceeds, so do not subtract ``fees``
    from realised P/L again. ``dividends`` is net of the fee on the dividend row.
    """

    balances: tuple[CurrencyAmount, ...]
    dividends: tuple[CurrencyAmount, ...]
    fees: tuple[CurrencyAmount, ...]
    net_deposits: tuple[CurrencyAmount, ...]


@dataclass(frozen=True)
class PriceQuote:
    """A price with its provenance (API_CONTRACT §4)."""

    symbol: str
    price: Decimal
    currency: str
    as_of: datetime
    freshness: Freshness
    source: str


@dataclass(frozen=True)
class FxRate:
    """One unit of ``base`` costs ``rate`` units of ``quote`` on ``as_of``."""

    base: str
    quote: str
    rate: Decimal
    as_of: date
    source: str


@dataclass(frozen=True)
class ValuedPosition:
    symbol: str
    currency: str
    quantity: Decimal
    cost_basis: Decimal
    cost_basis_base: Decimal | None
    quote: PriceQuote | None
    fx_rate: FxRate | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    market_value_base: Decimal | None
    unrealized_pnl_base: Decimal | None
    weight: Decimal | None
    unavailable_reason: str | None


@dataclass(frozen=True)
class PortfolioValuation:
    """Totals in ``base_currency`` over the positions that could be valued.

    When ``is_complete`` is false the totals and weights cover only part of the
    portfolio: ``unvalued_symbols`` names what is left out, and the totals must
    be shown as partial. Nothing is assumed for the positions left out. The
    totals are None when no position could be valued; cost and P/L are also
    None when a valued position has no base-currency cost.
    """

    base_currency: str
    positions: tuple[ValuedPosition, ...]
    total_market_value: Decimal | None
    total_cost_basis: Decimal | None
    total_unrealized_pnl: Decimal | None
    is_complete: bool
    unvalued_symbols: tuple[str, ...]


@dataclass(frozen=True)
class ConvertedAmount:
    """One amount and its value in the base currency (None with a reason when no rate exists)."""

    currency: str
    amount: Decimal
    amount_base: Decimal | None
    fx_rate: FxRate | None
    unavailable_reason: str | None


@dataclass(frozen=True)
class ConvertedAmounts:
    """Amounts converted into ``base_currency``, in input order.

    ``total_base`` sums the amounts that could be converted. It is partial when
    ``is_complete`` is false (``missing_currencies`` names what is left out)
    and None when nothing could be converted.
    """

    base_currency: str
    items: tuple[ConvertedAmount, ...]
    total_base: Decimal | None
    is_complete: bool
    missing_currencies: tuple[str, ...]


@dataclass(frozen=True)
class RealizedSummary:
    """Realised P/L added up per trade currency and in ``base_currency``.

    ``total_base`` uses the FX rates stored on the trades. It is None when any
    lot outside the base currency has no base figure;
    ``missing_base_currencies`` names the currencies of those lots.
    """

    base_currency: str
    by_currency: tuple[CurrencyAmount, ...]
    total_base: Decimal | None
    missing_base_currencies: tuple[str, ...]


@dataclass(frozen=True)
class AllocationSlice:
    group: str
    market_value_base: Decimal
    weight: Decimal


@dataclass(frozen=True)
class Concentration:
    hhi: Decimal
    largest_symbol: str
    largest_weight: Decimal
    effective_holdings: Decimal


@dataclass(frozen=True)
class DatedValue:
    """Portfolio value at the close of ``date``.

    ``net_flow`` is external cash added (positive) or removed (negative) on
    that day, already included in ``value``. The first point's flow is ignored.
    """

    date: date
    value: Decimal
    net_flow: Decimal = _ZERO


@dataclass(frozen=True)
class RiskMetrics:
    observations: int
    start: date | None
    end: date | None
    period_return_pct: Decimal | None
    daily_volatility_pct: Decimal | None
    annualized_volatility_pct: Decimal | None
    max_drawdown_pct: Decimal | None
    max_drawdown_peak: date | None
    max_drawdown_trough: date | None


@dataclass(frozen=True)
class DailyClose:
    """One real end-of-day closing price from a market data provider."""

    date: date
    close: Decimal


@dataclass(frozen=True)
class DailyIndicators:
    """Indicators of the latest close in a daily history; None where history is too short.

    ``as_of`` is the date of the latest close used and ``observations`` the
    number of closes supplied.
    """

    as_of: date | None
    observations: int
    rsi_14: Decimal | None
    sma_20: Decimal | None
    volatility_pct: Decimal | None


@dataclass(frozen=True)
class CanonicalSymbol:
    """One identity per tradable thing (DATABASE_CONTRACT §3.1)."""

    symbol: str
    exchange: str
    provider_symbol: str
    currency: str
    asset_class: str


@dataclass(frozen=True)
class InstrumentSeed:
    symbol: str
    exchange: str
    provider_symbol: str
    currency: str
    asset_class: str
    name: str | None
