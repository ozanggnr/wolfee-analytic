"""REQ-20: no AI market insight is generated or stored from empty or partial stock data.

Smoke test: the daily insight was generated before the first refresh finished and
said "0 stocks, +0.00%". The worker stored an insight from whatever rows existed,
and /api/insight generated one on the fly from the first 50 rows.
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

import ai_service  # noqa: E402
import workers  # noqa: E402
from database import Base  # noqa: E402
from models import AIInsight, StockData  # noqa: E402
from quant.universe import BIST_SYMBOLS, GLOBAL_SYMBOLS  # noqa: E402
from services import insight_readiness  # noqa: E402


def _rows(market_type, symbols):
    return [(market_type, symbol) for symbol in symbols]


HALF_BIST = len(BIST_SYMBOLS) // 2 + len(BIST_SYMBOLS) % 2  # rounded up: exactly 50 %
HALF_GLOBAL = len(GLOBAL_SYMBOLS) // 2 + len(GLOBAL_SYMBOLS) % 2


@pytest.mark.parametrize("rows, ready", [
    ([], False),
    (_rows("BIST", BIST_SYMBOLS), False),                                   # Global still missing
    (_rows("GLOBAL", GLOBAL_SYMBOLS), False),                               # BIST still missing
    (_rows("BIST", BIST_SYMBOLS[:HALF_BIST - 1]) + _rows("GLOBAL", GLOBAL_SYMBOLS), False),
    (_rows("BIST", BIST_SYMBOLS[:HALF_BIST]) + _rows("GLOBAL", GLOBAL_SYMBOLS[:HALF_GLOBAL]), True),
    (_rows("BIST", BIST_SYMBOLS) + _rows("GLOBAL", GLOBAL_SYMBOLS) + _rows("COMMODITY", ["GC=F"]), True),
])
def test_an_insight_needs_half_of_both_stock_universes(rows, ready):
    assert insight_readiness.is_ready(insight_readiness.coverage(rows)) is ready


def test_duplicate_cache_rows_count_once():
    rows = _rows("BIST", [BIST_SYMBOLS[0]] * len(BIST_SYMBOLS)) + _rows("GLOBAL", GLOBAL_SYMBOLS)

    assert insight_readiness.coverage(rows)["BIST"] == 1
    assert not insight_readiness.is_ready(insight_readiness.coverage(rows))


@pytest.fixture
def factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(workers, "AsyncSessionLocal", sessions)
    yield sessions
    asyncio.run(engine.dispose())


def _cache(factory, rows):
    async def run():
        async with factory() as session:
            session.add_all(StockData(symbol=s, name=s, price=10.0, change_pct=1.0, market_type=m) for m, s in rows)
            await session.commit()

    asyncio.run(run())


def _stored_insights(factory):
    async def run():
        async with factory() as session:
            return (await session.execute(select(AIInsight))).scalars().all()

    return asyncio.run(run())


@pytest.fixture
def fake_insight(monkeypatch):
    calls = []

    def generate(market_data, opportunities=None):
        calls.append(len(market_data))
        return f"insight over {len(market_data)} rows"

    monkeypatch.setattr(ai_service, "get_market_insight", generate)
    return calls


@pytest.mark.parametrize("rows", [[], _rows("BIST", BIST_SYMBOLS)])
def test_the_worker_stores_no_insight_from_incomplete_data(factory, fake_insight, rows, caplog):
    _cache(factory, rows)

    generated = asyncio.run(workers.refresh_ai_insight(force=True))

    assert generated is False
    assert fake_insight == []
    assert _stored_insights(factory) == []
    assert any("stock data incomplete" in r.getMessage() for r in caplog.records)


def test_the_worker_stores_an_insight_once_both_markets_are_loaded(factory, fake_insight):
    _cache(factory, _rows("BIST", BIST_SYMBOLS) + _rows("GLOBAL", GLOBAL_SYMBOLS))

    generated = asyncio.run(workers.refresh_ai_insight(force=True))

    assert generated is True
    total = len(BIST_SYMBOLS) + len(GLOBAL_SYMBOLS)
    assert fake_insight == [total]
    assert [i.insight_text for i in _stored_insights(factory)] == [f"insight over {total} rows"]
