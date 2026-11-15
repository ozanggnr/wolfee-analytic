"""REQ-10: /api/live-price writes its quote to the card cache through enrich_quote.

analyze_stock may still return its legacy single-day estimates (listed in
estimated_fields). Before this, the background update re-ran the old enrichment and
stored those estimates and an advice label in stock_data, where the cards read them.
"""
import asyncio
import secrets

import pytest
from sqlalchemy import select

import main
from database import AsyncSessionLocal
from models import StockData


def _legacy_result(symbol):
    return {"symbol": symbol, "name": symbol, "price": 101.5, "change_pct": 6.0, "volume": 1000.0,
            "currency": "TRY", "market_type": "BIST", "day_high": 0, "day_low": 0, "open": None,
            "previous_close": None, "rsi": 68.0, "ma_20": 99.4, "volatility": "HIGH",
            "prediction": "Up 6.0% today", "reason": "Up 6.0% today", "is_favorable": True, "is_buyable": True,
            "estimated_fields": ["rsi", "ma_20", "volatility", "is_favorable", "is_buyable"]}


async def _cached(symbol):
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(StockData).where(StockData.symbol == symbol))).scalar_one()


@pytest.fixture
def symbol(monkeypatch):
    ticker = f"ZL{secrets.token_hex(3).upper()}"
    monkeypatch.setattr(main, "analyze_stock", lambda symbol, *args, **kwargs: _legacy_result(symbol))
    return ticker


def test_legacy_estimates_from_analyze_stock_never_reach_the_card_cache(user, symbol):
    response = user.get(f"/api/live-price/{symbol}")
    assert response.status_code == 200, response.text

    row = asyncio.run(_cached(f"{symbol}.IS"))
    assert row.price == 101.5
    assert (row.rsi, row.ma_20, row.volatility, row.prediction, row.is_favorable, row.is_buyable,
            row.day_high, row.day_low) == (None,) * 8
    assert row.extra_data == {"indicators_as_of": None, "indicator_method": None, "volatility_pct": None}
