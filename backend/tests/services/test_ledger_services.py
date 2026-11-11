"""Service and model rules for the ledger, run against a private in-memory database."""
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import Base  # noqa: E402
from models import Instrument, LedgerImmutableError, Portfolio, Transaction, User  # noqa: E402
from schemas.portfolio import PortfolioCreate  # noqa: E402
from schemas.transaction import TransactionCreate  # noqa: E402
from services import instrument_service, portfolio_service, transaction_service  # noqa: E402
from services.errors import ConflictError, InvalidInputError, NotFoundError  # noqa: E402


@dataclass(frozen=True)
class Seed:
    """Same attributes as the quant layer's InstrumentSeed."""

    symbol: str
    exchange: str
    provider_symbol: str
    currency: str
    asset_class: str
    name: Optional[str]


THYAO = Seed("THYAO", "BIST", "THYAO.IS", "TRY", "equity", "Turk Hava Yollari")
AAPL = Seed("AAPL", "US", "AAPL", "USD", "equity", "Apple")


def run_with_session(scenario):
    """Run `scenario(session)` on a fresh in-memory database."""

    async def _run():
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
                return await scenario(session)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


async def add_user(session: AsyncSession, email: str = "owner@example.com") -> int:
    user = User(email=email, password_hash="unusable", email_verified=True, failed_login_count=0)
    session.add(user)
    await session.commit()
    return user.id


async def add_portfolio(session: AsyncSession, user_id: int, name: str = "Main") -> Portfolio:
    return await portfolio_service.create_portfolio(
        session, user_id, PortfolioCreate(name=name, base_currency="TRY")
    )


def deposit() -> TransactionCreate:
    return TransactionCreate(type="DEPOSIT", quantity="100", currency="TRY", trade_date=date(2026, 3, 10))


def buy(symbol: str, exchange: Optional[str] = None) -> TransactionCreate:
    return TransactionCreate(
        type="BUY", symbol=symbol, exchange=exchange, quantity="1", price="10", trade_date=date(2026, 3, 10)
    )


# ------------------------------------------------------------------
# Append-only ledger
# ------------------------------------------------------------------

def test_a_stored_transaction_cannot_be_updated():
    async def scenario(session):
        user_id = await add_user(session)
        portfolio = await add_portfolio(session, user_id)
        created = await transaction_service.record_transaction(session, user_id, portfolio.id, deposit())
        row = await session.get(Transaction, created.id)
        row.quantity = Decimal("999")
        with pytest.raises(LedgerImmutableError):
            await session.commit()
        await session.rollback()
        return (await session.get(Transaction, created.id)).quantity

    assert run_with_session(scenario) == Decimal("100")


def test_a_stored_transaction_cannot_be_deleted():
    async def scenario(session):
        user_id = await add_user(session)
        portfolio = await add_portfolio(session, user_id)
        created = await transaction_service.record_transaction(session, user_id, portfolio.id, deposit())
        await session.delete(await session.get(Transaction, created.id))
        with pytest.raises(LedgerImmutableError):
            await session.commit()
        await session.rollback()
        return await session.scalar(select(func.count()).select_from(Transaction))

    assert run_with_session(scenario) == 1


def test_recording_stamps_the_acting_user_and_manual_source():
    async def scenario(session):
        user_id = await add_user(session)
        portfolio = await add_portfolio(session, user_id)
        created = await transaction_service.record_transaction(session, user_id, portfolio.id, deposit())
        row = await session.get(Transaction, created.id)
        return row.created_by_user_id == user_id, row.source, row.instrument_id

    assert run_with_session(scenario) == (True, "manual", None)


# ------------------------------------------------------------------
# Ownership
# ------------------------------------------------------------------

def test_services_refuse_a_portfolio_owned_by_someone_else():
    async def scenario(session):
        owner_id = await add_user(session, "owner@example.com")
        stranger_id = await add_user(session, "stranger@example.com")
        portfolio = await add_portfolio(session, owner_id)
        created = await transaction_service.record_transaction(session, owner_id, portfolio.id, deposit())

        with pytest.raises(NotFoundError):
            await portfolio_service.get_portfolio(session, stranger_id, portfolio.id)
        with pytest.raises(NotFoundError):
            await transaction_service.list_transactions(session, stranger_id, portfolio.id, limit=50, offset=0)
        with pytest.raises(NotFoundError):
            await transaction_service.record_transaction(session, stranger_id, portfolio.id, deposit())
        with pytest.raises(NotFoundError):
            await transaction_service.void_transaction(session, stranger_id, portfolio.id, created.id, None)
        return await session.scalar(select(func.count()).select_from(Transaction))

    assert run_with_session(scenario) == 1


def test_duplicate_active_portfolio_name_is_a_conflict():
    async def scenario(session):
        user_id = await add_user(session)
        await add_portfolio(session, user_id, "Main")
        with pytest.raises(ConflictError):
            await add_portfolio(session, user_id, "Main")

    run_with_session(scenario)


# ------------------------------------------------------------------
# Instrument resolution
# ------------------------------------------------------------------

def test_a_symbol_listed_on_two_exchanges_needs_an_explicit_exchange():
    async def scenario(session):
        user_id = await add_user(session)
        portfolio = await add_portfolio(session, user_id)
        await instrument_service.sync_instruments(
            session, [Seed("DUAL", "BIST", "DUAL.IS", "TRY", "equity", None),
                      Seed("DUAL", "US", "DUAL", "USD", "equity", None)]
        )
        with pytest.raises(InvalidInputError, match="exchange"):
            await transaction_service.record_transaction(session, user_id, portfolio.id, buy("DUAL"))
        chosen = await transaction_service.record_transaction(session, user_id, portfolio.id, buy("DUAL", "US"))
        return chosen.exchange, chosen.currency

    assert run_with_session(scenario) == ("US", "USD")


# ------------------------------------------------------------------
# Instrument sync
# ------------------------------------------------------------------

def test_sync_inserts_missing_instruments_and_is_idempotent():
    async def scenario(session):
        first = await instrument_service.sync_instruments(session, [THYAO, AAPL])
        second = await instrument_service.sync_instruments(session, [THYAO, AAPL])
        count = await session.scalar(select(func.count()).select_from(Instrument))
        return first, second, count

    first, second, count = run_with_session(scenario)

    assert (first.inserted, first.updated) == (2, 0)
    assert (second.inserted, second.updated) == (0, 0)
    assert count == 2


def test_sync_refreshes_descriptive_fields_but_never_identity_or_currency():
    async def scenario(session):
        await instrument_service.sync_instruments(session, [THYAO])
        renamed = Seed("THYAO", "BIST", "THYAO.IS", "USD", "equity", "THY A.O.")
        result = await instrument_service.sync_instruments(session, [renamed])
        row = await session.scalar(select(Instrument).where(Instrument.symbol == "THYAO"))
        return result, row.name, row.currency

    result, name, currency = run_with_session(scenario)

    assert (result.inserted, result.updated) == (0, 1)
    assert name == "THY A.O."
    assert currency == "TRY"


def test_sync_never_removes_or_reactivates_instruments():
    async def scenario(session):
        await instrument_service.sync_instruments(session, [THYAO, AAPL])
        row = await session.scalar(select(Instrument).where(Instrument.symbol == "AAPL"))
        row.is_active = False
        await session.commit()
        await instrument_service.sync_instruments(session, [THYAO])
        rows = (await session.scalars(select(Instrument).order_by(Instrument.symbol))).all()
        return [(r.symbol, r.is_active) for r in rows]

    assert run_with_session(scenario) == [("AAPL", False), ("THYAO", True)]


# ------------------------------------------------------------------
# Integrity errors raised at commit (the path two racing requests take)
# ------------------------------------------------------------------

def _failing_commit(session, message: str):
    from sqlalchemy.exc import IntegrityError

    async def commit():
        raise IntegrityError("INSERT", {}, Exception(message))

    session.commit = commit


def test_losing_a_race_for_a_portfolio_name_is_a_conflict():
    async def scenario(session):
        user_id = await add_user(session)
        _failing_commit(session, "UNIQUE constraint failed: portfolios.user_id, portfolios.name")
        with pytest.raises(ConflictError):
            await add_portfolio(session, user_id)

    run_with_session(scenario)


def test_losing_a_race_to_void_is_a_conflict():
    async def scenario(session):
        user_id = await add_user(session)
        portfolio = await add_portfolio(session, user_id)
        created = await transaction_service.record_transaction(session, user_id, portfolio.id, deposit())
        _failing_commit(
            session, 'duplicate key value violates unique constraint "uq_transactions_voids_transaction_id"'
        )
        with pytest.raises(ConflictError):
            await transaction_service.void_transaction(session, user_id, portfolio.id, created.id, None)

    run_with_session(scenario)


def test_other_integrity_failures_are_not_disguised_as_conflicts():
    from sqlalchemy.exc import IntegrityError

    async def scenario(session):
        user_id = await add_user(session)
        portfolio = await add_portfolio(session, user_id)
        created = await transaction_service.record_transaction(session, user_id, portfolio.id, deposit())
        _failing_commit(session, "FOREIGN KEY constraint failed")
        with pytest.raises(IntegrityError):
            await add_portfolio(session, user_id, "Second")
        with pytest.raises(IntegrityError):
            await transaction_service.void_transaction(session, user_id, portfolio.id, created.id, None)

    run_with_session(scenario)
