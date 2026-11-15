"""REQ-31 (e): exchange rates and gold carry a null change when the source gives none.

Before this, a rate without a Yahoo previous close and a gold row without a change
cell were stored and served as 0.0 %, a move that was not observed.
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import workers  # noqa: E402
from data_sources import turkish_market  # noqa: E402
from database import Base  # noqa: E402
from models import ExchangeRate, TurkishGold  # noqa: E402

RECORDED_TCMB = Path(BACKEND_DIR, "tests", "fixtures", "tcmb_today_2026-11-13.xml").read_bytes()


class _RecordedClient:
    """Serves the recorded TCMB bulletin."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return SimpleNamespace(content=RECORDED_TCMB, raise_for_status=lambda: None)


def _ticker(previous_close):
    return lambda symbol: SimpleNamespace(fast_info=SimpleNamespace(last_price=50.5, previous_close=previous_close))


@pytest.mark.parametrize("previous_close, expected", [(None, None), (0, None), (50.0, 1.0)])
def test_a_rate_change_needs_a_previous_close(monkeypatch, previous_close, expected):
    monkeypatch.setattr(turkish_market.httpx, "Client", _RecordedClient)
    monkeypatch.setattr(turkish_market.yf, "Ticker", _ticker(previous_close))

    rates = turkish_market.fetch_exchange_rates()

    assert rates and all(rate["change_pct"] == expected for rate in rates)


GOLD_PAGE = """<table>
<tr><td><a href="/altin/gram-altin-fiyati/">Gram</a></td><td>3.050,25</td><td>3.051,10</td><td>%0,45</td></tr>
<tr><td><a href="/altin/ceyrek-altin-fiyati/">Çeyrek</a></td><td>5.000,00</td><td>5.100,00</td></tr>
<tr><td><a href="/altin/yarim-altin-fiyati/">Yarım</a></td><td>10.000,00</td><td>10.200,00</td><td>-</td></tr>
</table>"""


class _GoldClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return SimpleNamespace(text=GOLD_PAGE, raise_for_status=lambda: None)


def test_a_gold_row_without_a_change_has_a_null_change(monkeypatch):
    monkeypatch.setattr(turkish_market.httpx, "Client", _GoldClient)

    gold = {row["gold_type"]: row for row in turkish_market.fetch_turkish_gold()}

    assert gold["gram_altin"]["change_pct"] == 0.45
    assert gold["ceyrek_altin"]["change_pct"] is None  # no change column
    assert gold["yarim_altin"]["change_pct"] is None   # unreadable change cell


@pytest.fixture
def factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(workers, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(workers, "_DB_WRITE_LOCK", asyncio.Lock())
    yield sessions
    asyncio.run(engine.dispose())


def _changes(factory, model, key):
    async def run():
        async with factory() as session:
            return {getattr(row, key): row.change_pct for row in (await session.execute(select(model))).scalars()}

    return asyncio.run(run())


def test_the_cache_stores_null_and_replaces_an_old_change(factory, monkeypatch):
    rate = {"pair": "USD/TRY", "display_name": "USD", "buying": 50.1, "selling": 50.2}
    gold = {"gold_type": "gram_altin", "display_name": "Gram", "buying_price": 3050.0, "selling_price": 3051.0}
    for change in (None, 1.25, None):  # insert null, update to a value, update back to null
        monkeypatch.setattr(turkish_market, "fetch_exchange_rates", lambda: [{**rate, "change_pct": change}])
        monkeypatch.setattr(turkish_market, "fetch_turkish_gold", lambda: [{**gold, "change_pct": change}])
        asyncio.run(workers.refresh_exchange_rates())
        asyncio.run(workers.refresh_turkish_gold())
        assert _changes(factory, ExchangeRate, "pair") == {"USD/TRY": change}
        assert _changes(factory, TurkishGold, "gold_type") == {"gram_altin": change}
