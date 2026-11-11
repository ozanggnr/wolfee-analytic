"""Pins the output of ``analysis.analyze_stock`` so refactoring cannot change it.

Expected values were worked out from the logic at commit de0575a and the test
passed against that unmodified code before ``analysis.py`` was touched.
"""
from unittest.mock import patch

import pytest

pytest.importorskip("pandas")
pytest.importorskip("yfinance")

import analysis  # noqa: E402


def _raw(symbol, price, change_pct, **extra):
    return {"symbol": symbol, "name": symbol, "price": price, "change_pct": change_pct,
            "volume": 1000.0, "day_high": 0.0, "day_low": 0.0, "open": 0.0,
            "previous_close": 0.0, "bid": 0.0, "ask": 0.0, "market_cap": 5.0,
            "currency": "USD", **extra}


def test_global_stock_result_is_unchanged():
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
        "volatility": "LOW", "market_type": "GLOBAL",
    }


def test_bist_stock_keeps_suffix_and_try_currency():
    with patch("data_sources.turkish_market.fetch_bist_stock",
               return_value=_raw("THYAO", 300.0, -6.0, currency="TRY", previous_close=319.15,
                                 day_high=320.0, day_low=298.0, open=318.0)):
        result = analysis.analyze_stock("THYAO.IS")

    assert result["symbol"] == "THYAO.IS"
    assert result["currency"] == "TRY"
    assert result["market_type"] == "BIST"
    assert result["rsi"] == 32.0
    assert result["ma_20"] == 309.0
    assert result["volatility"] == "HIGH"
    assert result["prediction"] == "ACCUMULATE — oversold, potential bounce"
    assert (result["is_favorable"], result["is_buyable"]) == (False, False)


def test_commodity_uses_the_universe_display_name():
    with patch("data_sources.global_market.fetch_commodity_data",
               return_value=_raw("GC=F", 2000.0, 2.5, name="Gold (XAU/USD)")):
        result = analysis.analyze_stock("GC=F", is_commodity=True)

    assert result["name"] == "Gold (USD)"
    assert result["market_type"] == "COMMODITY"
    assert result["volatility"] == "MEDIUM"
    assert result["prediction"] == "PURCHASABLE — positive trend +2.5%"


def test_missing_data_returns_none():
    with patch("data_sources.global_market.fetch_global_stock", return_value=None):
        assert analysis.analyze_stock("AAPL") is None
