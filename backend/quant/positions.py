"""Holdings, cost basis, realised P/L and cash, derived by replaying the ledger.

Transactions are the only input and are never modified. Conventions:

* rows are replayed in ``(trade_date, id)`` order, whatever order they arrive in;
* a BUY fee is part of the cost basis; a SELL fee reduces the proceeds;
* base-currency amounts use the FX rate stored on each trade and are ``None``
  when a contributing trade has no stored rate — they are never recomputed
  from today's rate;
* selling more than is held is an error (no short positions);
* ``symbol`` is an opaque key here: callers normalise it first with
  ``quant.symbols.normalize_symbol``.

Replay is linear in the number of rows. It is CPU-bound: call it through
``asyncio.to_thread`` from async code and cap ledger size at the boundary.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from quant._math import ZERO, divide, fixed_context, proportion, scaled, to_decimal
from quant.types import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_COST_BASIS_METHOD,
    CashSummary,
    CostBasisMethod,
    CurrencyAmount,
    LedgerError,
    Lot,
    Position,
    RealizedLot,
    RealizedSummary,
    Transaction,
    TransactionType,
)

_T = TransactionType
_NEEDS_SYMBOL = frozenset({_T.BUY, _T.SELL, _T.DIVIDEND, _T.SPLIT})
_NEEDS_PRICE = frozenset({_T.BUY, _T.SELL, _T.DIVIDEND})

_CURRENCY_CODE = re.compile(r"[A-Z]{3}")


@fixed_context(LedgerError)
def build_positions(
    transactions: Sequence[Transaction], method: CostBasisMethod = DEFAULT_COST_BASIS_METHOD
) -> list[Position]:
    """Open positions implied by the ledger, sorted by symbol."""
    books, currencies, _ = _replay(transactions, method)
    return [
        _to_position(symbol, currencies[symbol], lots)
        for symbol, lots in sorted(books.items())
        if lots
    ]


@fixed_context(LedgerError)
def realized_pnl(
    transactions: Sequence[Transaction], method: CostBasisMethod = DEFAULT_COST_BASIS_METHOD
) -> list[RealizedLot]:
    """Realised profit and loss, one entry per lot consumed by each SELL, in replay order."""
    _, _, realized = _replay(transactions, method)
    return list(realized)


@fixed_context(LedgerError)
def realized_summary(
    transactions: Sequence[Transaction],
    method: CostBasisMethod = DEFAULT_COST_BASIS_METHOD,
    base_currency: str = DEFAULT_BASE_CURRENCY,
) -> RealizedSummary:
    """Realised P/L of the ledger per trade currency and in ``base_currency``.

    Weighted average cost unless ``method`` says FIFO (decision D2). Same as
    ``sum_realized(realized_pnl(transactions, method), base_currency)``.
    """
    _require_currency(base_currency, "base currency")
    _, _, realized = _replay(transactions, method)
    return _sum_realized(realized, base_currency)


@fixed_context()
def sum_realized(
    lots: Iterable[RealizedLot], base_currency: str = DEFAULT_BASE_CURRENCY
) -> RealizedSummary:
    """Add up realised lots per trade currency and in ``base_currency``.

    The base-currency total uses each lot's ``pnl_base``, which comes from the
    FX rates stored on the trades (never today's rate). A lot already in the
    base currency counts at exactly 1. If any other lot has no ``pnl_base`` the
    total is None and ``missing_base_currencies`` names its currency; the
    per-currency sums are always returned.
    """
    _require_currency(base_currency, "base currency")
    return _sum_realized(lots, base_currency)


def _sum_realized(lots: Iterable[RealizedLot], base_currency: str) -> RealizedSummary:
    per_currency: dict[str, Decimal] = defaultdict(lambda: ZERO)
    total_base = ZERO
    missing: set[str] = set()

    for lot in lots:
        _require_currency(lot.currency, "lot currency")
        pnl = _computed(lot.pnl, "pnl")
        per_currency[lot.currency] += pnl
        if lot.currency == base_currency:
            total_base += pnl
        elif lot.pnl_base is None:
            missing.add(lot.currency)
        else:
            total_base += _computed(lot.pnl_base, "pnl_base")

    return RealizedSummary(
        base_currency=base_currency,
        by_currency=_amounts(per_currency),
        total_base=None if missing else total_base,
        missing_base_currencies=tuple(sorted(missing)),
    )


def _computed(value: object, name: str) -> Decimal:
    """A figure produced by the replay: a finite Decimal (it may carry more places than an input)."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def _require_currency(value: object, name: str) -> None:
    if not isinstance(value, str) or not _CURRENCY_CODE.fullmatch(value):
        raise ValueError(f"{name} must be a 3-letter upper-case code")


@fixed_context(LedgerError)
def cash_summary(transactions: Sequence[Transaction]) -> CashSummary:
    """Cash balance, net dividends, fees and net deposits per currency."""
    balances: dict[str, Decimal] = defaultdict(lambda: ZERO)
    dividends: dict[str, Decimal] = defaultdict(lambda: ZERO)
    fees: dict[str, Decimal] = defaultdict(lambda: ZERO)
    deposits: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for tx in _effective(transactions):
        gross = tx.quantity * tx.price if tx.price is not None else ZERO
        if tx.type is _T.BUY:
            balances[tx.currency] -= gross + tx.fee
            fees[tx.currency] += tx.fee
        elif tx.type is _T.SELL:
            balances[tx.currency] += gross - tx.fee
            fees[tx.currency] += tx.fee
        elif tx.type is _T.DIVIDEND:
            balances[tx.currency] += gross - tx.fee
            dividends[tx.currency] += gross - tx.fee
        elif tx.type is _T.FEE:
            balances[tx.currency] -= tx.fee
            fees[tx.currency] += tx.fee
        elif tx.type is _T.DEPOSIT:
            balances[tx.currency] += tx.quantity
            deposits[tx.currency] += tx.quantity
        elif tx.type is _T.WITHDRAWAL:
            balances[tx.currency] -= tx.quantity
            deposits[tx.currency] -= tx.quantity

    return CashSummary(
        balances=_amounts(balances),
        dividends=_amounts(dividends),
        fees=_amounts(fees),
        net_deposits=_amounts(deposits),
    )


def _amounts(totals: Mapping[str, Decimal]) -> tuple[CurrencyAmount, ...]:
    return tuple(CurrencyAmount(currency, amount) for currency, amount in sorted(totals.items()))


# --------------------------------------------------------------------------
# Ledger preparation
# --------------------------------------------------------------------------

def _effective(transactions: Sequence[Transaction]) -> list[Transaction]:
    """Validated rows that are neither reversals nor reversed, in replay order."""
    by_id: dict[int, Transaction] = {}
    for tx in transactions:
        if tx.id in by_id:
            raise LedgerError(f"duplicate transaction id {tx.id}")
        by_id[tx.id] = tx

    voided: set[int] = set()
    for tx in transactions:
        if tx.voids_transaction_id is None:
            continue
        target = by_id.get(tx.voids_transaction_id)
        if target is None:
            raise LedgerError(f"transaction {tx.id} voids unknown transaction {tx.voids_transaction_id}")
        if target.voids_transaction_id is not None:
            raise LedgerError(f"transaction {tx.id} voids {target.id}, which is itself a reversal")
        if target.id in voided:
            raise LedgerError(f"transaction {target.id} is voided more than once")
        voided.add(target.id)

    live = [tx for tx in transactions if tx.voids_transaction_id is None and tx.id not in voided]
    for tx in live:
        _validate(tx)
    return sorted(live, key=lambda tx: (tx.trade_date, tx.id))


def _validate(tx: Transaction) -> None:
    where = f"transaction {tx.id} ({getattr(tx.type, 'value', tx.type)})"
    if not isinstance(tx.type, TransactionType):
        raise LedgerError(f"{where}: unknown transaction type")
    try:
        quantity = to_decimal(tx.quantity, "quantity")
        fee = to_decimal(tx.fee, "fee")
        price = None if tx.price is None else to_decimal(tx.price, "price")
        fx_rate = None if tx.fx_rate_to_base is None else to_decimal(tx.fx_rate_to_base, "fx_rate_to_base")
    except ValueError as exc:
        raise LedgerError(f"{where}: {exc}") from exc

    if not isinstance(tx.currency, str) or not _CURRENCY_CODE.fullmatch(tx.currency):
        raise LedgerError(f"{where}: currency must be a 3-letter upper-case code")
    if fee < ZERO:
        raise LedgerError(f"{where}: fee must not be negative")
    if fx_rate is not None and fx_rate <= ZERO:
        raise LedgerError(f"{where}: fx_rate_to_base must be positive")
    if tx.type in _NEEDS_SYMBOL and not tx.symbol:
        raise LedgerError(f"{where}: symbol is required")
    if tx.type is _T.SPLIT:
        if quantity <= ZERO:
            raise LedgerError(f"{where}: split ratio must be positive")
        return
    if tx.type is _T.FEE:
        return
    if quantity <= ZERO:
        raise LedgerError(f"{where}: quantity must be positive")
    if tx.type in _NEEDS_PRICE:
        if price is None:
            raise LedgerError(f"{where}: price is required")
        if price < ZERO:
            raise LedgerError(f"{where}: price must not be negative")


# --------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------

class _Book:
    """Working state for one symbol while a ledger is replayed (never leaves this module)."""

    __slots__ = ("currency", "lots", "held")

    def __init__(self, currency: str) -> None:
        self.currency = currency
        self.lots: deque[Lot] = deque()
        self.held = ZERO


def _replay(
    transactions: Sequence[Transaction], method: CostBasisMethod
) -> tuple[Mapping[str, tuple[Lot, ...]], Mapping[str, str], list[RealizedLot]]:
    if not isinstance(method, CostBasisMethod):
        raise LedgerError(f"unknown cost basis method: {method!r}")

    books: dict[str, _Book] = {}
    realized: list[RealizedLot] = []

    for tx in _effective(transactions):
        if tx.type not in (_T.BUY, _T.SELL, _T.SPLIT):
            continue
        if tx.type is _T.SPLIT:
            if tx.symbol in books:
                _split(books[tx.symbol], tx.quantity)
            continue
        book = books.setdefault(tx.symbol, _Book(tx.currency))
        if book.currency != tx.currency:
            raise LedgerError(
                f"transaction {tx.id}: {tx.symbol} trades in {book.currency}, got currency {tx.currency}"
            )
        if tx.type is _T.BUY:
            _buy(book, tx, method)
        else:
            realized.extend(_sell(book, tx))

    lots = {symbol: tuple(book.lots) for symbol, book in books.items()}
    currencies = {symbol: book.currency for symbol, book in books.items()}
    return lots, currencies, realized


def _buy(book: _Book, tx: Transaction, method: CostBasisMethod) -> None:
    cost = tx.quantity * tx.price + tx.fee
    cost_base = None if tx.fx_rate_to_base is None else cost * tx.fx_rate_to_base
    book.held += tx.quantity
    if method is CostBasisMethod.FIFO:
        book.lots.append(Lot(tx.quantity, cost, cost_base, tx.trade_date, tx.id))
        return
    if not book.lots:
        book.lots.append(Lot(tx.quantity, cost, cost_base, tx.trade_date, None))
        return
    pool = book.lots[0]
    book.lots[0] = Lot(
        quantity=pool.quantity + tx.quantity,
        cost=pool.cost + cost,
        cost_base=_add(pool.cost_base, cost_base),
        acquired=pool.acquired,
        transaction_id=None,
    )


def _sell(book: _Book, tx: Transaction) -> list[RealizedLot]:
    if tx.quantity > book.held:
        raise LedgerError(
            f"transaction {tx.id}: SELL of {tx.quantity} {tx.symbol} exceeds the {book.held} held"
        )

    net_proceeds = tx.quantity * tx.price - tx.fee
    to_sell = tx.quantity
    unallocated = net_proceeds
    realized: list[RealizedLot] = []

    while to_sell > ZERO:
        lot = book.lots[0]
        taken = min(lot.quantity, to_sell)
        to_sell -= taken
        sold, kept = _take(lot, taken)
        # The final slice takes whatever is left so slices add up to the net proceeds exactly.
        proceeds = unallocated if to_sell == ZERO else proportion(net_proceeds, taken, tx.quantity)
        unallocated -= proceeds
        realized.append(_realize(tx, sold, proceeds))
        if kept is None:
            book.lots.popleft()
        else:
            book.lots[0] = kept

    book.held -= tx.quantity
    return realized


def _split(book: _Book, ratio: Decimal) -> None:
    book.lots = deque(
        Lot(lot.quantity * ratio, lot.cost, lot.cost_base, lot.acquired, lot.transaction_id)
        for lot in book.lots
    )
    book.held *= ratio


def _take(lot: Lot, quantity: Decimal) -> tuple[Lot, Lot | None]:
    """Split ``lot`` into the part sold and the part kept; costs are conserved."""
    if quantity == lot.quantity:
        return lot, None
    cost = proportion(lot.cost, quantity, lot.quantity)
    cost_base = None if lot.cost_base is None else proportion(lot.cost_base, quantity, lot.quantity)
    sold = Lot(quantity, cost, cost_base, lot.acquired, lot.transaction_id)
    kept = Lot(
        quantity=lot.quantity - quantity,
        cost=lot.cost - cost,
        cost_base=None if cost_base is None else lot.cost_base - cost_base,
        acquired=lot.acquired,
        transaction_id=lot.transaction_id,
    )
    return sold, kept


def _realize(tx: Transaction, sold: Lot, proceeds: Decimal) -> RealizedLot:
    proceeds_base = None if tx.fx_rate_to_base is None else proceeds * tx.fx_rate_to_base
    pnl_base = (
        None if proceeds_base is None or sold.cost_base is None else proceeds_base - sold.cost_base
    )
    return RealizedLot(
        symbol=tx.symbol,
        currency=tx.currency,
        quantity=sold.quantity,
        acquired=sold.acquired,
        disposed=tx.trade_date,
        cost=sold.cost,
        proceeds=proceeds,
        pnl=proceeds - sold.cost,
        cost_base=sold.cost_base,
        proceeds_base=proceeds_base,
        pnl_base=pnl_base,
        buy_transaction_id=sold.transaction_id,
        sell_transaction_id=tx.id,
    )


def _add(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left + right


def _to_position(symbol: str, currency: str, lots: tuple[Lot, ...]) -> Position:
    quantity = sum((lot.quantity for lot in lots), ZERO)
    cost = sum((lot.cost for lot in lots), ZERO)
    cost_base = ZERO
    for lot in lots:
        cost_base = _add(cost_base, lot.cost_base)
    return Position(
        symbol=symbol,
        currency=currency,
        quantity=quantity,
        cost_basis=cost,
        average_cost=scaled(divide(cost, quantity)),
        cost_basis_base=cost_base,
        lots=lots,
    )
