"""REQ-18: exchange rates reach the exchange_rates table, or the failure is loud.

The smoke test saw /api/exchange-rates empty for a whole run. Reproduced: the
TCMB fetch succeeded, but the insert failed with "database is locked" because
refresh_commodities held a SQLite write transaction open across its network
fetches. The error was swallowed and the refresh reported 0 items.
"""
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import workers  # noqa: E402
from data_sources import turkish_market  # noqa: E402
from database import Base  # noqa: E402
from models import ExchangeRate, StockData  # noqa: E402

RECORDED_TCMB = Path(BACKEND_DIR, "tests", "fixtures", "tcmb_today_2026-11-13.xml")
RECORDED_RATES = {  # ForexBuying / ForexSelling in the recorded bulletin 2026/214
    "USD/TRY": (50.1926, 50.2830),
    "EUR/TRY": (55.5033, 55.6033),
    "GBP/TRY": (66.3009, 66.6466),
}


class _RecordedResponse:
    content = RECORDED_TCMB.read_bytes()

    def raise_for_status(self):
        return None


class _RecordedClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        assert url == "https://www.tcmb.gov.tr/kurlar/today.xml"
        return _RecordedResponse()


class _NoYahoo:
    def __init__(self, symbol):
        raise RuntimeError("network disabled in tests")


@pytest.fixture
def recorded_tcmb(monkeypatch):
    monkeypatch.setattr(turkish_market.httpx, "Client", _RecordedClient)
    monkeypatch.setattr(turkish_market.yf, "Ticker", _NoYahoo)


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    """The workers' session factory pointed at an empty SQLite file (one writer at a time)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'refresh.db').as_posix()}")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(workers, "AsyncSessionLocal", factory)
    monkeypatch.setattr(workers, "_DB_WRITE_LOCK", asyncio.Lock())
    yield factory
    asyncio.run(engine.dispose())


async def _stored_rates(factory):
    async with factory() as session:
        rows = (await session.execute(select(ExchangeRate))).scalars().all()
    return {row.pair: (row.buying, row.selling) for row in rows}


def test_the_parser_reads_the_recorded_tcmb_response(recorded_tcmb):
    rates = turkish_market.fetch_exchange_rates()

    assert {r["pair"]: (r["buying"], r["selling"]) for r in rates} == RECORDED_RATES
    assert all(r["change_pct"] == 0.0 for r in rates)  # Yahoo unavailable: no change figure


def test_the_refresh_stores_the_recorded_rates(recorded_tcmb, sessions):
    stored = asyncio.run(workers.refresh_exchange_rates())

    assert stored == 3
    assert asyncio.run(_stored_rates(sessions)) == RECORDED_RATES


def test_rates_are_stored_while_the_commodity_refresh_is_still_fetching(recorded_tcmb, sessions, monkeypatch):
    """The collision from the smoke test: the commodity refresh is mid-way through slow
    fetches when the exchange-rate refresh writes. Before the fix the commodity session
    began its write transaction at the second upsert (about 2 s) and held it until all
    twelve fetches finished (about 12 s); the exchange insert at 3 s outlasted SQLite's
    5 s busy timeout and failed with "database is locked"."""
    import analysis
    from data_sources import global_market

    symbols = {f"C{i}=F": f"Commodity {i}" for i in range(12)}

    def slow_commodity(symbol):
        time.sleep(1)
        return {"symbol": symbol, "price": 10.0, "change_pct": 0.0}

    def exchange_after_first_commodity():
        time.sleep(3)  # lands while the old commodity refresh held its write transaction
        return [{"pair": pair, "display_name": pair, "buying": b, "selling": s, "change_pct": 0.0}
                for pair, (b, s) in RECORDED_RATES.items()]

    monkeypatch.setattr(analysis, "COMMODITIES_SYMBOLS", symbols)
    monkeypatch.setattr(global_market, "fetch_commodity_data", slow_commodity)
    monkeypatch.setattr(turkish_market, "fetch_exchange_rates", exchange_after_first_commodity)

    async def both():
        return await asyncio.gather(workers.refresh_commodities(), workers.refresh_exchange_rates())

    commodities, rates = asyncio.run(both())

    assert (commodities, rates) == (12, 3)
    assert asyncio.run(_stored_rates(sessions)) == RECORDED_RATES

    async def commodity_rows():
        async with sessions() as session:
            return len((await session.execute(select(StockData))).scalars().all())

    assert asyncio.run(commodity_rows()) == 12


def test_an_unreachable_source_is_logged_and_nothing_is_filled_in(sessions, monkeypatch, caplog):
    def unreachable(*args, **kwargs):
        raise turkish_market.httpx.ConnectError("TCMB unreachable")

    monkeypatch.setattr(turkish_market.httpx.Client, "get", unreachable)

    with caplog.at_level(logging.ERROR):
        stored = asyncio.run(workers.refresh_exchange_rates())

    assert stored == 0
    assert asyncio.run(_stored_rates(sessions)) == {}
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("TCMB" in m and "unreachable" in m for m in messages)
    assert any("exchange_rates left unchanged" in m for m in messages)
