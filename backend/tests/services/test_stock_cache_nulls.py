"""REQ-24 support (decision D4): a null indicator from the enrichment reaches the
stock_data cache as NULL, on insert and on update, replacing any earlier estimate.

Before this, the ORM column defaults turned an explicit None into rsi 50, ma_20 0,
volatility "LOW" on insert, and the update path skipped None, so an estimated RSI
would have stayed in the cache indefinitely.
"""
import asyncio
import os
import sys

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import workers  # noqa: E402
from database import Base  # noqa: E402
from models import StockData  # noqa: E402

NULL_INDICATORS = {"rsi": None, "ma_20": None, "day_high": None, "day_low": None, "volatility": None,
                   "is_favorable": None, "is_buyable": None}
ESTIMATES = {"rsi": 53.75, "ma_20": 99.4, "day_high": 101.0, "day_low": 99.0, "volatility": "LOW",
             "is_favorable": True, "is_buyable": True}


@pytest.fixture
def factory():
    engine = create_async_engine("sqlite+aiosqlite://")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    asyncio.run(engine.dispose())


def _upsert_then_read(factory, *quotes):
    async def run():
        for quote in quotes:
            async with factory() as session:
                await workers._upsert_stock(session, dict(quote))
                await session.commit()
        async with factory() as session:
            row = (await session.execute(select(StockData))).scalar_one()
        return {key: getattr(row, key) for key in NULL_INDICATORS} | {"price": row.price}

    return asyncio.run(run())


def test_a_new_row_stores_null_indicators_as_null(factory):
    stored = _upsert_then_read(factory, {"symbol": "THYAO.IS", "price": 300.0, **NULL_INDICATORS})

    assert stored == {**NULL_INDICATORS, "price": 300.0}


def test_a_new_row_without_indicator_keys_stores_null_rather_than_defaults(factory):
    stored = _upsert_then_read(factory, {"symbol": "THYAO.IS", "price": 300.0})

    assert stored == {**NULL_INDICATORS, "price": 300.0}


def test_null_indicators_replace_earlier_estimates(factory):
    stored = _upsert_then_read(factory,
                               {"symbol": "THYAO.IS", "price": 300.0, **ESTIMATES},
                               {"symbol": "THYAO.IS", "price": 301.0, **NULL_INDICATORS})

    assert stored == {**NULL_INDICATORS, "price": 301.0}


def test_an_update_without_indicator_keys_keeps_the_stored_values(factory):
    stored = _upsert_then_read(factory,
                               {"symbol": "THYAO.IS", "price": 300.0, **ESTIMATES},
                               {"symbol": "THYAO.IS", "price": 301.0})

    assert stored == {**ESTIMATES, "price": 301.0}


def test_a_null_price_still_does_not_overwrite_the_stored_price(factory):
    stored = _upsert_then_read(factory,
                               {"symbol": "THYAO.IS", "price": 300.0, **ESTIMATES},
                               {"symbol": "THYAO.IS", "price": None, **NULL_INDICATORS})

    assert stored == {**ESTIMATES, "price": 300.0}  # the whole update is skipped, as before
