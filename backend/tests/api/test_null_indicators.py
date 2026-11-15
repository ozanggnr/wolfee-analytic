"""REQ-24 support (decision D4): rsi, ma_20, day range and volatility are null until
they are computed from real price history. Every consumer of these values in the
watchlist and export routes must accept null: JSON keeps null, the Excel export
shows "Not available", nothing is estimated and nothing answers 500.
"""
import asyncio
import io
import secrets
from datetime import datetime, timezone

import pytest
from openpyxl import load_workbook

import main
import watchlist_routes
from database import AsyncSessionLocal
from models import StockData, WatchlistItem
from services.market_display import NOT_AVAILABLE

NULL_INDICATORS = {"rsi": None, "ma_20": None, "day_high": None, "day_low": None, "volatility": None,
                   "is_buyable": None, "is_favorable": None}


def _ticker() -> str:
    return f"ZN{secrets.token_hex(3).upper()}"


async def _watch(user_id: int, ticker: str, cached: bool):
    async with AsyncSessionLocal() as session:
        session.add(WatchlistItem(user_id=user_id, ticker=ticker, market="BIST100",
                                  added_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        if cached:
            session.add(StockData(symbol=f"{ticker}.IS", name=ticker, price=101.5, change_pct=1.25,
                                  currency="TRY", market_type="BIST100", **NULL_INDICATORS))
        await session.commit()


def _sheet_rows(response):
    sheet = load_workbook(io.BytesIO(response.content)).active
    header = [cell.value for cell in sheet[1]]
    return [dict(zip(header, (cell.value for cell in row))) for row in sheet.iter_rows(min_row=2)]


def _assert_indicators_not_available(row):
    for column in ("Period High", "Period Low", "RSI (14)", "RSI Status", "Volatility %", "MA(20)"):
        assert row[column] == NOT_AVAILABLE, (column, row[column])


def test_the_watchlist_keeps_null_indicators_from_the_cache(user):
    ticker = _ticker()
    asyncio.run(_watch(user.user_id, ticker, cached=True))

    response = user.get("/api/watchlist")

    assert response.status_code == 200, response.text
    item = next(i for i in response.json()["items"] if i["ticker"] == ticker)
    assert (item["price"], item["rsi"], item["day_high"], item["day_low"]) == (101.5, None, None, None)
    assert item["prediction"] is None  # was "Bullish" from the day's change


def test_the_watchlist_keeps_null_indicators_from_the_live_fallback(user, monkeypatch):
    ticker = _ticker()
    asyncio.run(_watch(user.user_id, ticker, cached=False))
    live = {"symbol": f"{ticker}.IS", "name": ticker, "price": 55.0, "change_pct": -0.5, "currency": "TRY",
            **NULL_INDICATORS}
    monkeypatch.setattr(watchlist_routes, "analyze_stock", lambda *args, **kwargs: dict(live))

    response = user.get("/api/watchlist")

    assert response.status_code == 200, response.text
    item = next(i for i in response.json()["items"] if i["ticker"] == ticker)
    assert (item["price"], item["rsi"], item["day_high"], item["day_low"]) == (55.0, None, None, None)


def test_the_watchlist_placeholder_does_not_invent_indicators(user, monkeypatch):
    ticker = _ticker()
    asyncio.run(_watch(user.user_id, ticker, cached=False))
    monkeypatch.setattr(watchlist_routes, "analyze_stock", lambda *args, **kwargs: None)

    response = user.get("/api/watchlist")

    item = next(i for i in response.json()["items"] if i["ticker"] == ticker)
    assert (item["rsi"], item["day_high"], item["day_low"]) == (None, None, None)


def test_the_posted_export_shows_not_available_for_null_indicators(user):
    stock = {"symbol": "THYAO.IS", "name": "THY", "price": 300.0, "change_pct": 2.0, "currency": "TRY",
             "previous_close": 294.12, "volume": 1000, **NULL_INDICATORS}

    response = user.post("/api/export/portfolio", json={"period": "daily", "stocks": [stock]})

    assert response.status_code == 200, response.text
    [row] = _sheet_rows(response)
    _assert_indicators_not_available(row)
    assert (row["Current Price"], row["Start Price"]) == (300.0, 294.12)


def test_the_posted_export_survives_indicator_values_that_are_not_numbers(user):
    stock = {"symbol": "AAPL", "price": 190.0, "rsi": "abc", "day_high": "n/a", "ma_20": [1]}

    response = user.post("/api/export/portfolio", json={"period": "weekly", "stocks": [stock]})

    assert response.status_code == 200, response.text
    [row] = _sheet_rows(response)
    assert (row["RSI (14)"], row["Period High"], row["MA(20)"]) == (NOT_AVAILABLE,) * 3


def test_the_watchlist_export_shows_not_available_for_null_indicators(user):
    ticker = _ticker()
    asyncio.run(_watch(user.user_id, ticker, cached=True))

    response = user.post("/api/export/portfolio", json={"period": "monthly", "stocks": []})

    assert response.status_code == 200, response.text
    row = next(r for r in _sheet_rows(response) if r["Symbol"] == ticker)
    _assert_indicators_not_available(row)


def test_the_symbol_export_shows_not_available_for_null_indicators(user, monkeypatch):
    live = {"symbol": "AAPL", "name": "Apple", "price": 190.0, "change_pct": 0.0, "currency": "USD",
            **NULL_INDICATORS}
    monkeypatch.setattr(main, "analyze_stock", lambda *args, **kwargs: dict(live))

    response = user.get("/api/export/portfolio?symbols=AAPL&period=daily")

    assert response.status_code == 200, response.text
    [row] = _sheet_rows(response)
    _assert_indicators_not_available(row)


def test_a_failed_symbol_in_the_export_is_not_available_rather_than_zero(user, monkeypatch):
    monkeypatch.setattr(main, "analyze_stock", lambda *args, **kwargs: None)

    response = user.get("/api/export/portfolio?symbols=AAPL&period=daily")

    assert response.status_code == 200, response.text
    [row] = _sheet_rows(response)
    _assert_indicators_not_available(row)
    assert row["Current Price"] == NOT_AVAILABLE


def test_cached_stock_rows_keep_null_indicators_in_api_responses():
    row = StockData(symbol="X.IS", name="X", price=10.0, change_pct=0.0, **NULL_INDICATORS)

    shown = main._stock_to_dict(row)

    assert {key: shown[key] for key in NULL_INDICATORS} == NULL_INDICATORS
    assert shown["price"] == 10.0


@pytest.mark.parametrize("value, expected", [(None, None), (0, None), (-1.0, None), ("12", None),
                                             (float("nan"), None), (float("inf"), None), (True, None),
                                             (12.345, 12.35)])
def test_price_levels_are_positive_finite_numbers_or_none(value, expected):
    from services.market_display import price_level

    assert price_level(value) == expected


@pytest.mark.parametrize("rsi, status", [(None, NOT_AVAILABLE), (29.9, "Oversold"), (30, "Neutral"),
                                         (70.1, "Overbought"), (0, "Oversold")])
def test_rsi_status_needs_a_real_rsi(rsi, status):
    from services.market_display import rsi_status

    assert rsi_status(rsi) == status
