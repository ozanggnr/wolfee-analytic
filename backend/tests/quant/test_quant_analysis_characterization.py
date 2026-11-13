"""Pins the output of ``analysis.analyze_stock``.

Decision D4 (REQ-24): without real daily closes the indicators and the labels
built on them are None, and a day high or low the provider did not supply is
None. The other fields are unchanged from commit de0575a.
"""
import math
import statistics
from datetime import date, timedelta
from decimal import Decimal as D
from unittest.mock import patch

import pytest

pytest.importorskip("pandas")
pytest.importorskip("yfinance")

import analysis  # noqa: E402
from quant.indicators import INDICATOR_METHOD  # noqa: E402
from quant.types import DailyClose  # noqa: E402


def _raw(symbol, price, change_pct, **extra):
    return {"symbol": symbol, "name": symbol, "price": price, "change_pct": change_pct,
            "volume": 1000.0, "day_high": 0.0, "day_low": 0.0, "open": 0.0,
            "previous_close": 0.0, "bid": 0.0, "ask": 0.0, "market_cap": 5.0,
            "currency": "USD", **extra}


def test_default_call_still_returns_the_legacy_estimates_until_callers_accept_none():
    # TEMPORARY (REQ-26): watchlist_routes and the exports still round these fields.
    with patch("data_sources.global_market.fetch_global_stock",
               return_value=_raw("AAPL", 200.0, 1.0, currency="EUR")):
        result = analysis.analyze_stock("AAPL")

    assert result == {
        "symbol": "AAPL", "name": "AAPL", "price": 200.0, "change_pct": 1.0,
        "currency": "EUR", "market_cap": 5.0, "volume": 1000,
        "day_high": 202.0, "day_low": 198.0, "open": 198.0, "previous_close": 198.02,
        "bid": 0.0, "ask": 0.0, "rsi": 53.0, "ma_20": 199.0,
        "prediction": "PURCHASABLE — rising +1.0%", "reason": "PURCHASABLE — rising +1.0%",
        "buy_signals": [], "is_favorable": True, "is_buyable": True,
        "volatility": "LOW", "volatility_pct": None,
        "indicators_as_of": None, "indicator_method": None,      # None marks the figures as estimates
        "market_type": "GLOBAL",
    }


def test_legacy_estimates_for_a_falling_bist_stock_are_unchanged():
    with patch("data_sources.turkish_market.fetch_bist_stock",
               return_value=_raw("THYAO", 300.0, -6.0, currency="TRY", previous_close=319.15,
                                 day_high=320.0, day_low=298.0, open=318.0)):
        result = analysis.analyze_stock("THYAO.IS")

    assert (result["rsi"], result["ma_20"], result["volatility"]) == (32.0, 309.0, "HIGH")
    assert result["prediction"] == "ACCUMULATE — oversold, potential bounce"
    assert (result["is_favorable"], result["is_buyable"]) == (False, False)
    assert result["indicators_as_of"] is None


def test_global_stock_without_history_has_no_indicators_or_labels():
    with patch("data_sources.global_market.fetch_global_stock",
               return_value=_raw("AAPL", 200.0, 1.0, currency="EUR")):
        result = analysis.analyze_stock("AAPL", legacy_estimates=False)

    assert result == {
        "symbol": "AAPL", "name": "AAPL", "price": 200.0, "change_pct": 1.0,
        "currency": "EUR", "market_cap": 5.0, "volume": 1000,
        "day_high": None, "day_low": None, "open": 198.0, "previous_close": 198.02,
        "bid": 0.0, "ask": 0.0, "rsi": None, "ma_20": None,
        "prediction": None, "reason": None,
        "buy_signals": [], "is_favorable": None, "is_buyable": None,
        "volatility": None, "volatility_pct": None,
        "indicators_as_of": None, "indicator_method": None,
        "market_type": "GLOBAL",
    }


def test_bist_stock_keeps_suffix_currency_and_the_providers_day_range():
    with patch("data_sources.turkish_market.fetch_bist_stock",
               return_value=_raw("THYAO", 300.0, -6.0, currency="TRY", previous_close=319.15,
                                 day_high=320.0, day_low=298.0, open=318.0)):
        result = analysis.analyze_stock("THYAO.IS", history=[])

    assert result["symbol"] == "THYAO.IS"
    assert result["currency"] == "TRY"
    assert result["market_type"] == "BIST"
    assert (result["day_high"], result["day_low"]) == (320.0, 298.0)
    assert (result["rsi"], result["ma_20"], result["volatility"]) == (None, None, None)
    assert (result["prediction"], result["is_favorable"], result["is_buyable"]) == (None, None, None)


def test_real_history_gives_real_indicators_and_labels():
    # 21 daily closes rising 100, 101, ... 120: every move is a gain, so RSI is 100,
    # and the last 20 closes (101..120) average 110.5.
    start = date(2026, 1, 1)
    history = [DailyClose(start + timedelta(days=i), D(100 + i)) for i in range(21)]
    returns = [(101 + i) / (100 + i) - 1 for i in range(20)]
    expected_volatility = statistics.stdev(returns) * math.sqrt(252) * 100     # 0.788 %

    with patch("data_sources.global_market.fetch_global_stock",
               return_value=_raw("AAPL", 120.0, 4.0)):
        result = analysis.analyze_stock("AAPL", history=history)

    assert result["rsi"] == 100.0
    assert result["ma_20"] == 110.5
    assert result["volatility_pct"] == round(expected_volatility, 2) == 0.79
    assert result["volatility"] == "LOW"
    assert result["prediction"] == "TAKE PROFITS — up 4.0%, overbought"
    assert (result["is_favorable"], result["is_buyable"]) == (True, False)
    assert result["indicators_as_of"] == "2026-01-21"
    assert result["indicator_method"] == INDICATOR_METHOD


def test_commodity_uses_the_universe_display_name():
    with patch("data_sources.global_market.fetch_commodity_data",
               return_value=_raw("GC=F", 2000.0, 2.5, name="Gold (XAU/USD)")):
        result = analysis.analyze_stock("GC=F", is_commodity=True, legacy_estimates=False)

    assert result["name"] == "Gold (USD)"
    assert result["market_type"] == "COMMODITY"
    assert result["volatility"] is None
    assert result["prediction"] is None


def test_missing_data_returns_none():
    with patch("data_sources.global_market.fetch_global_stock", return_value=None):
        assert analysis.analyze_stock("AAPL") is None


def test_opportunities_need_a_label_that_could_be_computed():
    cached = [
        {"symbol": "A", "change_pct": 3.0, "is_favorable": None},     # no history: no label
        {"symbol": "B", "change_pct": 3.0, "is_favorable": True},
        {"symbol": "C", "change_pct": 0.2, "is_favorable": True},     # move too small
    ]

    assert [o["symbol"] for o in analysis.get_market_opportunities(cached)] == ["B"]
