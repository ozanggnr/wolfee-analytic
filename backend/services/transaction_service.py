"""Ledger rules: append and void only, scoped to the caller's portfolio.

This module stores what the user recorded. It does no portfolio arithmetic:
holdings, cost basis and profit or loss are derived from these rows by the quant layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import Instrument, Transaction
from repositories import instrument_repository, transaction_repository
from schemas.common import Page
from schemas.transaction import TransactionCreate, TransactionOut
from services import portfolio_service
from services.errors import ConflictError, InvalidInputError, NotFoundError, is_unique_violation

ONE = Decimal(1)
SOURCE_MANUAL = "manual"
# The instrument's own currency is the only valid trade currency for these types.
INSTRUMENT_CURRENCY_TYPES = frozenset({"BUY", "SELL", "SPLIT"})

NOT_FOUND = "Transaction not found."
ALREADY_VOIDED = "This transaction has already been voided."
REVERSAL_NOT_VOIDABLE = "A reversal cannot be voided. Record the transaction again instead."


def _to_schema(row: Transaction, voided_by: Optional[int] = None) -> TransactionOut:
    instrument = row.instrument
    return TransactionOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        type=row.type,
        symbol=instrument.symbol if instrument else None,
        exchange=instrument.exchange if instrument else None,
        quantity=row.quantity,
        price=row.price,
        fee=row.fee,
        currency=row.currency,
        fx_rate_to_base=row.fx_rate_to_base,
        trade_date=row.trade_date,
        executed_at=row.executed_at,
        note=row.note,
        source=row.source,
        voids_transaction_id=row.voids_transaction_id,
        voided_by_transaction_id=voided_by,
        created_at=row.created_at,
    )


async def _resolve_instrument(db: AsyncSession, symbol: str, exchange: Optional[str]) -> Instrument:
    """Exactly one active instrument, or an error. A symbol is never guessed."""
    matches = await instrument_repository.find_active(db, symbol, exchange)
    if not matches:
        where = f" on {exchange}" if exchange else ""
        raise InvalidInputError(f"Unknown or inactive instrument: {symbol}{where}.")
    if len(matches) > 1:
        exchanges = ", ".join(sorted({match.exchange for match in matches}))
        raise InvalidInputError(f"{symbol} is listed on several exchanges ({exchanges}); specify exchange.")
    return matches[0]


def _trade_currency(payload: TransactionCreate, instrument: Optional[Instrument]) -> str:
    if instrument is None:
        return payload.currency  # the schema guarantees it is present without a symbol
    if payload.currency is None:
        return instrument.currency
    if payload.type in INSTRUMENT_CURRENCY_TYPES and payload.currency != instrument.currency:
        raise InvalidInputError(
            f"{instrument.symbol} trades in {instrument.currency}, not {payload.currency}."
        )
    return payload.currency


def _fx_rate_to_base(given: Optional[Decimal], currency: str, base_currency: str) -> Optional[Decimal]:
    """The rate stored with the row. A missing foreign rate stays unknown; it is never looked up."""
    if currency != base_currency:
        return given
    if given is not None and given != ONE:
        raise InvalidInputError(
            f"fx_rate_to_base must be 1 when the trade currency equals the base currency ({base_currency})."
        )
    return ONE


async def list_transactions(
    db: AsyncSession, user_id: int, portfolio_id: int, *, limit: int, offset: int
) -> Page[TransactionOut]:
    await portfolio_service.load_owned(db, user_id, portfolio_id)
    rows, total = await transaction_repository.list_for_portfolio(
        db, user_id, portfolio_id, limit=limit, offset=offset
    )
    reversals = await transaction_repository.reversals_of(db, [row.id for row in rows])
    items = [_to_schema(row, reversals.get(row.id)) for row in rows]
    return Page[TransactionOut](items=items, total=total, limit=limit, offset=offset)


async def record_transaction(
    db: AsyncSession, user_id: int, portfolio_id: int, payload: TransactionCreate
) -> TransactionOut:
    portfolio = await portfolio_service.load_writable(db, user_id, portfolio_id)
    instrument = (
        await _resolve_instrument(db, payload.symbol, payload.exchange) if payload.symbol else None
    )
    currency = _trade_currency(payload, instrument)
    row = Transaction(
        portfolio_id=portfolio.id,
        instrument=instrument,
        type=payload.type,
        quantity=payload.quantity,
        price=payload.price,
        fee=payload.fee,
        currency=currency,
        fx_rate_to_base=_fx_rate_to_base(payload.fx_rate_to_base, currency, portfolio.base_currency),
        trade_date=payload.trade_date,
        executed_at=payload.executed_at,
        note=payload.note,
        source=SOURCE_MANUAL,
        created_at=datetime.now(timezone.utc),
        created_by_user_id=user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_schema(row)


async def void_transaction(
    db: AsyncSession, user_id: int, portfolio_id: int, transaction_id: int, note: Optional[str]
) -> TransactionOut:
    """Append a reversal row. The original row is never edited or deleted."""
    portfolio = await portfolio_service.load_writable(db, user_id, portfolio_id)
    original = await transaction_repository.get_in_portfolio(db, user_id, portfolio.id, transaction_id)
    if original is None:
        raise NotFoundError(NOT_FOUND)
    if original.voids_transaction_id is not None:
        raise ConflictError(REVERSAL_NOT_VOIDABLE)
    if await transaction_repository.reversals_of(db, [original.id]):
        raise ConflictError(ALREADY_VOIDED)

    reversal = Transaction(
        portfolio_id=original.portfolio_id,
        instrument=original.instrument,
        type=original.type,
        quantity=original.quantity,
        price=original.price,
        fee=original.fee,
        currency=original.currency,
        fx_rate_to_base=original.fx_rate_to_base,
        trade_date=original.trade_date,
        executed_at=original.executed_at,
        note=note,
        source=SOURCE_MANUAL,
        voids_transaction_id=original.id,
        created_at=datetime.now(timezone.utc),
        created_by_user_id=user_id,
    )
    db.add(reversal)
    try:
        await db.commit()
    except IntegrityError as exc:  # a concurrent request voided it first
        await db.rollback()
        if not is_unique_violation(
            exc, "uq_transactions_voids_transaction_id", "transactions.voids_transaction_id"
        ):
            raise
        raise ConflictError(ALREADY_VOIDED) from exc
    await db.refresh(reversal)
    return _to_schema(reversal)
