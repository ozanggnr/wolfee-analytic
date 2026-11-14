"""REQ-30 (user decision 2026-11-14): a missing open / previous_close is null, not 0.0.

Before this, the data sources wrote 0.0 when the provider gave no value, the history
fallback used today's price as the previous close when only one day came back, and
the StockData model defaulted both columns to 0, so the cards showed 0.
"""
import asyncio
import math
import os
import sys
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import workers  # noqa: E402
from data_sources import global_market, turkish_market  # noqa: E402
from data_sources.provided import provided_price  # noqa: E402
from database import Base  # noqa: E402
from models import StockData  # noqa: E402
from services.market_display import stock_card  # noqa: E402


@pytest.mark.parametrize("value", [None, 0, 0.0, -1.5, math.nan, math.inf, "n/a", True])
def test_a_missing_or_impossible_price_is_none(value):
    assert provided_price(value) is None


def test_a_supplied_price_is_kept_exactly():
    assert provided_price(301.123456) == 301.123456 and provided_price("12.5") == 12.5


class FakeTicker:
    def __init__(self, fast_info=None, history=None):
        self._fast_info, self._history = fast_info, history

    @property
    def fast_info(self):
        if self._fast_info is None:
            raise KeyError("currentTradingPeriod")
        return self._fast_info

    def history(self, period):
        return self._history if self._history is not None else pd.DataFrame()


def _fast_info(**overrides):
    values = dict(last_price=320.25, previous_close=None, day_high=323.5, day_low=315.0, open=0.0,
                  last_volume=1e6, market_cap=1e9, fifty_day_average=300.0, currency="USD")
    return SimpleNamespace(**{**values, **overrides})


ONE_DAY = pd.DataFrame({"Open": [float("nan")], "High": [323.5], "Low": [315.0], "Close": [320.25],
                        "Volume": [1e6]})

FETCHERS = [
    (global_market, "fetch_global_stock", "AAPL"),
    (global_market, "fetch_commodity_data", "GC=F"),
    (turkish_market, "fetch_bist_stock", "THYAO"),
]


@pytest.mark.parametrize("module, function, symbol", FETCHERS)
def test_fast_info_without_open_or_previous_close_gives_none(monkeypatch, module, function, symbol):
    monkeypatch.setattr(module.yf, "Ticker", lambda s: FakeTicker(fast_info=_fast_info()))

    quote = getattr(module, function)(symbol)

    assert (quote["open"], quote["previous_close"]) == (None, None)
    assert quote["price"] == 320.25 and quote["change_pct"] == 0.0


@pytest.mark.parametrize("module, function, symbol", FETCHERS)
def test_a_single_history_day_does_not_turn_the_price_into_the_previous_close(monkeypatch, module, function,
                                                                              symbol):
    monkeypatch.setattr(module.yf, "Ticker",
                        lambda s: FakeTicker(fast_info=None, history=ONE_DAY))  # fast_info raises

    quote = getattr(module, function)(symbol)

    assert quote["price"] == 320.25
    assert (quote["open"], quote["previous_close"]) == (None, None)  # was open NaN, previous_close 320.25


@pytest.mark.parametrize("module, function, symbol", FETCHERS)
def test_supplied_values_pass_through(monkeypatch, module, function, symbol):
    monkeypatch.setattr(module.yf, "Ticker",
                        lambda s: FakeTicker(fast_info=_fast_info(previous_close=310.0, open=315.75)))

    quote = getattr(module, function)(symbol)

    assert (quote["open"], quote["previous_close"], quote["change_pct"]) == (315.75, 310.0, 3.31)


def test_finnhub_zero_open_and_previous_close_are_none(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"c": 101.0, "pc": 0, "o": 0, "h": 102.0, "l": 100.0}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            return Response()

    monkeypatch.setattr(global_market.httpx, "Client", Client)

    quote = global_market.fetch_global_stock_finnhub("AAPL", "test-key")

    assert (quote["open"], quote["previous_close"]) == (None, None)


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
            return (await session.execute(select(StockData))).scalar_one()

    return asyncio.run(run())


def test_the_cache_stores_null_and_the_card_shows_null(factory):
    row = _upsert_then_read(factory, {"symbol": "THYAO", "price": 320.25, "open": None, "previous_close": None})

    assert (row.open_price, row.previous_close) == (None, None)  # was 0 from the model default
    card = stock_card(row)
    assert (card["open"], card["previous_close"]) == (None, None)


def test_a_missing_value_replaces_a_stale_one(factory):
    row = _upsert_then_read(factory,
                            {"symbol": "THYAO", "price": 320.25, "open": 315.75, "previous_close": 310.0},
                            {"symbol": "THYAO", "price": 321.0, "open": None, "previous_close": None})

    assert (row.open_price, row.previous_close, row.price) == (None, None, 321.0)


def test_a_legacy_zero_in_the_cache_is_shown_as_null(factory):
    row = _upsert_then_read(factory, {"symbol": "THYAO", "price": 320.25, "open": 0.0, "previous_close": 0.0})

    card = stock_card(row)
    assert (card["open"], card["previous_close"]) == (None, None)
