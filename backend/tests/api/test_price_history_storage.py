"""REQ-26: price_history storage on the configured database.

Runs on SQLite by default and on PostgreSQL 16 when WOLFEE_TEST_POSTGRES_URL is set,
where the table comes from the migration: the dialect-specific upsert, the NUMERIC
round trip and the CHECK constraint are exercised on both.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import AsyncSessionLocal
from models import Instrument, PriceHistory
from repositories import price_history_repository

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)


def _bar(day, close, **extra):
    return {"date": day, "open": None, "high": None, "low": None, "close": Decimal(close), "volume": None, **extra}


async def _instrument_id(symbol):
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(Instrument.id).where(Instrument.symbol == symbol))).scalar_one()


async def _write(instrument_id, bars, fetched_at=NOW):
    async with AsyncSessionLocal() as session:
        written = await price_history_repository.upsert_bars(session, instrument_id, "TRY", "yahoo_chart", bars,
                                                             fetched_at=fetched_at)
        await session.commit()
        return written


async def _read(instrument_id):
    async with AsyncSessionLocal() as session:
        closes = await price_history_repository.daily_closes(session, instrument_id)
        latest = await price_history_repository.latest_by_instrument(session, [instrument_id])
    return closes, latest


def test_bars_are_upserted_per_day_and_read_back_oldest_first(instrument):
    instrument_id = asyncio.run(_instrument_id(instrument["symbol"]))
    first = [_bar(date(2026, 11, 13), "320.25", open=Decimal("315.75"), high=Decimal("323.5"),
                  low=Decimal("315"), volume=Decimal("29607838")),
             _bar(date(2026, 11, 12), "319.123456")]
    correction = [_bar(date(2026, 11, 13), "321")]

    asyncio.run(_write(instrument_id, first))
    asyncio.run(_write(instrument_id, correction, fetched_at=NOW + timedelta(days=1)))
    closes, latest = asyncio.run(_read(instrument_id))

    assert [(c.date, c.close) for c in closes] == [(date(2026, 11, 12), Decimal("319.123456")),
                                                   (date(2026, 11, 13), Decimal("321"))]
    fetched_at = latest[instrument_id].fetched_at
    if fetched_at.tzinfo is None:  # SQLite keeps no offset; Postgres returns an aware value
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    assert (latest[instrument_id].date, fetched_at) == (date(2026, 11, 13), NOW + timedelta(days=1))


def test_the_corrected_day_keeps_only_supplied_values(instrument):
    instrument_id = asyncio.run(_instrument_id(instrument["symbol"]))
    asyncio.run(_write(instrument_id, [_bar(date(2026, 11, 13), "320", high=Decimal("330"), low=Decimal("310"))]))

    asyncio.run(_write(instrument_id, [_bar(date(2026, 11, 13), "321")]))

    async def stored():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(PriceHistory).where(
                PriceHistory.instrument_id == instrument_id))).scalar_one()

    row = asyncio.run(stored())
    assert (row.close, row.high, row.low, row.currency, row.source) == (Decimal("321"), None, None, "TRY",
                                                                         "yahoo_chart")


def test_the_database_refuses_a_non_positive_close(instrument):
    instrument_id = asyncio.run(_instrument_id(instrument["symbol"]))

    with pytest.raises(IntegrityError):
        asyncio.run(_write(instrument_id, [_bar(date(2026, 11, 13), "0")]))
