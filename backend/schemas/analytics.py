"""Holdings and performance responses (API_CONTRACT §5.2).

Every figure is computed by the quant package from the transaction ledger; this
module only fixes the JSON shape. Amounts are decimal strings, and a figure that
cannot be computed is null, never estimated.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel

from schemas.common import UtcDateTime, fixed_scale

CostBasisMethodName = Literal["fifo", "weighted_average"]
FreshnessName = Literal["realtime", "delayed", "end_of_day", "stale"]

Quantity = Annotated[Decimal, fixed_scale(8)]
Money = Annotated[Decimal, fixed_scale(6)]
Rate = Annotated[Decimal, fixed_scale(8)]
Ratio = Annotated[Decimal, fixed_scale(10)]


class QuoteOut(BaseModel):
    price: Money
    currency: str
    as_of: UtcDateTime
    freshness: FreshnessName
    source: str


class FxRateOut(BaseModel):
    base: str
    quote: str
    rate: Rate
    as_of: date
    source: str


class CurrencyAmountOut(BaseModel):
    currency: str
    amount: Money


class HoldingOut(BaseModel):
    symbol: str
    exchange: str
    name: Optional[str] = None
    currency: str
    quantity: Quantity
    average_cost: Money
    cost_basis: Money
    cost_basis_base: Optional[Money] = None
    market_value: Optional[Money] = None
    unrealized_pnl: Optional[Money] = None
    market_value_base: Optional[Money] = None
    unrealized_pnl_base: Optional[Money] = None
    weight: Optional[Ratio] = None
    quote: Optional[QuoteOut] = None
    fx_rate: Optional[FxRateOut] = None
    unavailable_reason: Optional[str] = None


class AnalyticsHeader(BaseModel):
    portfolio_id: int
    base_currency: str
    cost_basis_method: CostBasisMethodName
    computed_at: UtcDateTime
    is_complete: bool
    unvalued_symbols: List[str]


class HoldingsOut(AnalyticsHeader):
    positions: List[HoldingOut]
    total_market_value: Optional[Money] = None
    total_cost_basis: Optional[Money] = None
    total_unrealized_pnl: Optional[Money] = None


class RealizedLotOut(BaseModel):
    symbol: str
    exchange: str
    currency: str
    quantity: Quantity
    acquired: date
    disposed: date
    cost: Money
    proceeds: Money
    pnl: Money
    cost_base: Optional[Money] = None
    proceeds_base: Optional[Money] = None
    pnl_base: Optional[Money] = None
    buy_transaction_id: Optional[int] = None
    sell_transaction_id: int


class PerformanceOut(AnalyticsHeader):
    realized_pnl: List[CurrencyAmountOut]
    realized_pnl_base: Optional[Money] = None
    unrealized_pnl_base: Optional[Money] = None
    dividends: List[CurrencyAmountOut]
    fees: List[CurrencyAmountOut]
    net_deposits: List[CurrencyAmountOut]
    cash_balances: List[CurrencyAmountOut]
    realized_lots: List[RealizedLotOut]
