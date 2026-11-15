"""REQ-10 (REQ-24/26): the market cards are enriched by quant.signals.enrich_quote with
real price_history closes, and carry no single-day estimates.

Before this, workers._enrich_stock_data (a second copy of the enrichment) estimated
RSI as 50 + 3 x change_pct, the 20-day average from the day's change, volatility from
one day's move, and advice labels ("PURCHASABLE", "TAKE PROFITS") on top of them.
"""
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import analysis  # noqa: E402
import workers  # noqa: E402
from data_sources import global_market, turkish_market  # noqa: E402
from database import Base  # noqa: E402
from main import _stock_to_dict  # noqa: E402
from models import Instrument, PriceHistory, StockData  # noqa: E402
from quant.signals import enrich_quote  # noqa: E402
from quant.types import DailyClose  # noqa: E402
from services import card_history  # noqa: E402

LAST_CLOSE_DAY = date(2026, 11, 13)
# 30 weekdays of real-looking closes ending on LAST_CLOSE_DAY.
DAYS = []
_day = LAST_CLOSE_DAY
while len(DAYS) < 30:
    if _day.weekday() < 5:
        DAYS.insert(0, _day)
    _day -= timedelta(days=1)
CLOSES = [Decimal("300") + Decimal(index % 7) * Decimal("1.75") - Decimal(index % 3) for index in range(30)]
HISTORY = tuple(DailyClose(day, close) for day, close in zip(DAYS, CLOSES))

BIG_MOVE_QUOTE = {"symbol": "THYAO", "name": "THYAO", "price": 320.25, "change_pct": 6.0, "volume": 1e6,
                  "day_high": None, "day_low": None, "open": 315.0, "previous_close": 302.1}
NO_ESTIMATE = {"rsi": None, "ma_20": None, "volatility": None, "prediction": None, "reason": None,
               "is_favorable": None, "is_buyable": None}


@pytest.fixture
def factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all([
                Instrument(symbol="THYAO", exchange="BIST", provider_symbol="THYAO.IS", currency="TRY",
                           asset_class="equity", is_active=True),
                Instrument(symbol="AAPL", exchange="US", provider_symbol="AAPL", currency="USD",
                           asset_class="equity", is_active=True),
                Instrument(symbol="GC=F", exchange="CMDTY", provider_symbol="GC=F", currency="USD",
                           asset_class="commodity", is_active=True),
            ])
            await session.commit()

    asyncio.run(create())
    monkeypatch.setattr(workers, "AsyncSessionLocal", sessions)
    yield sessions
    asyncio.run(engine.dispose())


def _store_history(sessions, symbol):
    async def run():
        async with sessions() as session:
            instrument_id = (await session.execute(
                select(Instrument.id).where(Instrument.symbol == symbol))).scalar_one()
            session.add_all(PriceHistory(instrument_id=instrument_id, date=point.date, close=point.close,
                                         currency="TRY", source="test") for point in HISTORY)
            await session.commit()

    asyncio.run(run())


def _rows(sessions):
    async def run():
        async with sessions() as session:
            return {row.symbol: row for row in (await session.execute(select(StockData))).scalars()}

    return asyncio.run(run())


@pytest.fixture
def bist_quote(monkeypatch):
    quote = dict(BIG_MOVE_QUOTE)
    monkeypatch.setattr(analysis, "BIST_SYMBOLS", ["THYAO"])
    monkeypatch.setattr(turkish_market, "fetch_bist_stock", lambda symbol: dict(quote))
    return quote


def _fields(row):
    return {key: getattr(row, key) for key in NO_ESTIMATE}


def test_cards_get_the_indicators_of_the_stored_closes(factory, bist_quote):
    _store_history(factory, "THYAO")
    expected = enrich_quote(bist_quote, "BIST", "TRY", history=HISTORY)

    assert asyncio.run(workers.refresh_bist_stocks()) == 1

    card = _stock_to_dict(_rows(factory)["THYAO"])
    assert expected["rsi"] is not None and expected["ma_20"] is not None
    assert {key: card[key] for key in NO_ESTIMATE} == {key: expected[key] for key in NO_ESTIMATE}
    assert card["indicators_as_of"] == LAST_CLOSE_DAY.isoformat()
    assert card["indicator_method"] == expected["indicator_method"]
    assert card["volatility_pct"] == expected["volatility_pct"]
    assert "estimated_fields" not in card


def test_without_history_a_big_move_produces_no_estimate(factory, bist_quote):
    asyncio.run(workers.refresh_bist_stocks())

    card = _stock_to_dict(_rows(factory)["THYAO"])
    assert {key: card[key] for key in NO_ESTIMATE} == NO_ESTIMATE  # was rsi 68, HIGH, "PURCHASABLE ..."
    assert (card["indicators_as_of"], card["indicator_method"], card["volatility_pct"]) == (None, None, None)


def test_a_refresh_replaces_an_estimate_left_by_the_old_enrichment(factory, bist_quote):
    async def old_row():
        async with factory() as session:
            session.add(StockData(symbol="THYAO", price=300.0, market_type="BIST", currency="TRY", rsi=68.0,
                                  ma_20=291.0, volatility="HIGH", prediction="PURCHASABLE — strong momentum +6.0%",
                                  reason="PURCHASABLE — strong momentum +6.0%", is_favorable=True, is_buyable=True))
            await session.commit()

    asyncio.run(old_row())
    asyncio.run(workers.refresh_bist_stocks())

    assert _fields(_rows(factory)["THYAO"]) == NO_ESTIMATE


def test_a_failed_history_read_stores_the_quote_with_null_indicators(factory, bist_quote, monkeypatch, caplog):
    _store_history(factory, "THYAO")

    async def unreadable(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(card_history, "histories_for", unreadable)
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(workers.refresh_bist_stocks()) == 1

    row = _rows(factory)["THYAO"]
    assert _fields(row) == NO_ESTIMATE and row.price == 320.25
    assert any("indicators stay null" in record.getMessage() for record in caplog.records)


def test_global_and_commodity_quotes_find_their_own_history(factory, monkeypatch):
    _store_history(factory, "AAPL")
    _store_history(factory, "GC=F")
    monkeypatch.setattr(analysis, "GLOBAL_SYMBOLS", ["AAPL", "MSFT"])
    monkeypatch.setattr(analysis, "COMMODITIES_SYMBOLS", {"GC=F": "Gold"})
    monkeypatch.setattr(global_market, "fetch_global_stock",
                        lambda symbol: {**BIG_MOVE_QUOTE, "symbol": symbol, "currency": "USD"})
    monkeypatch.setattr(global_market, "fetch_commodity_data", lambda symbol: {**BIG_MOVE_QUOTE, "symbol": symbol})

    asyncio.run(workers.refresh_global_stocks())
    asyncio.run(workers.refresh_commodities())

    cards = {symbol: _stock_to_dict(row) for symbol, row in _rows(factory).items()}
    assert cards["AAPL"]["indicators_as_of"] == cards["GC=F"]["indicators_as_of"] == LAST_CLOSE_DAY.isoformat()
    assert cards["MSFT"]["rsi"] is None and cards["MSFT"]["indicators_as_of"] is None  # no stored history


def test_history_is_read_as_decimal_daily_closes(factory):
    _store_history(factory, "THYAO")

    async def run():
        async with factory() as session:
            return await card_history.histories_for(session, "BIST", ["THYAO", "THYAO.IS", "UNKNOWN", "bad sym"])

    histories = asyncio.run(run())

    assert histories["THYAO"] == HISTORY and histories["THYAO.IS"] == HISTORY
    assert all(isinstance(point.close, Decimal) for point in histories["THYAO"])
    assert histories["UNKNOWN"] is None and histories["bad sym"] is None


def test_the_old_enrichment_copy_is_gone():
    assert not hasattr(workers, "_enrich_stock_data")
