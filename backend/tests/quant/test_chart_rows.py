"""Chart bars from the data sources: a missing open, high or low stays None.

Before this the helpers wrote the bar's close into a missing open / high / low,
which drew a flat bar that was never observed (user decision 2026-11-15).
"""
import math

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("yfinance")

from data_sources import global_market, turkish_market  # noqa: E402
from data_sources.provided import chart_level, chart_row  # noqa: E402

# 1767225600 = 2026-01-01 00:00 UTC; the bars are one day apart.
# Bar 1 is complete, bar 2 has no open / high / low, bar 3 has no close, bar 4 has a zero low.
CHART_BODY = {"chart": {"result": [{
    "timestamp": [1767225600, 1767312000, 1767398400, 1767484800],
    "indicators": {"quote": [{
        "open": [10.0, None, 12.0, 13.0],
        "high": [10.55555, None, 12.5, 13.5],
        "low": [9.5, None, 11.5, 0],
        "close": [10.25, 11.0, None, 13.25],
        "volume": [1000, None, 500, 700],
    }]},
}]}}

EXPECTED_ROWS = [
    {"time": "2026-01-01 00:00", "open": 10.0, "high": 10.5556, "low": 9.5, "close": 10.25, "volume": 1000},
    {"time": "2026-01-02 00:00", "open": None, "high": None, "low": None, "close": 11.0, "volume": 0},
    {"time": "2026-01-04 00:00", "open": 13.0, "high": 13.5, "low": None, "close": 13.25, "volume": 700},
]


class _Response:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _client(body):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, params=None):
            return _Response(body)

    return Client


HELPERS = [
    (turkish_market, "_fetch_yahoo_chart", "THYAO.IS"),
    (global_market, "_fetch_yahoo_chart_global", "AAPL"),
]


@pytest.mark.parametrize("module, helper, symbol", HELPERS)
def test_missing_open_high_low_are_none_not_the_close(monkeypatch, module, helper, symbol):
    monkeypatch.setattr(module.httpx, "Client", _client(CHART_BODY))

    rows = getattr(module, helper)(symbol, "1mo", "1d")

    assert rows == EXPECTED_ROWS


@pytest.mark.parametrize("module, helper, symbol", HELPERS)
def test_shorter_open_high_low_lists_give_none(monkeypatch, module, helper, symbol):
    body = {"chart": {"result": [{
        "timestamp": [1767225600],
        "indicators": {"quote": [{"close": [10.25]}]},
    }]}}
    monkeypatch.setattr(module.httpx, "Client", _client(body))

    rows = getattr(module, helper)(symbol, "1mo", "1d")

    assert rows == [{"time": "2026-01-01 00:00", "open": None, "high": None, "low": None,
                     "close": 10.25, "volume": 0}]


class _Ticker:
    def __init__(self, symbol):
        pass

    def history(self, period=None, interval=None):
        index = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
        return pd.DataFrame({
            "Open": [10.0, math.nan, 12.0],
            "High": [10.5, math.nan, 12.5],
            "Low": [9.5, math.nan, 11.5],
            "Close": [10.25, 11.0, math.nan],
            "Volume": [1000, math.nan, 500],
        }, index=index)


@pytest.mark.parametrize("module, fetch, helper, symbol", [
    (turkish_market, "fetch_bist_history", "_fetch_yahoo_chart", "THYAO"),
    (global_market, "fetch_global_history", "_fetch_yahoo_chart_global", "AAPL"),
])
def test_the_yfinance_fallback_leaves_nan_as_none(monkeypatch, module, fetch, helper, symbol):
    monkeypatch.setattr(module, helper, lambda *args: None)        # the direct API gave nothing
    monkeypatch.setattr(module.yf, "Ticker", _Ticker)

    rows = getattr(module, fetch)(symbol, "1mo")

    assert rows == [
        {"time": "2026-01-01 00:00", "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.25, "volume": 1000},
        {"time": "2026-01-02 00:00", "open": None, "high": None, "low": None, "close": 11.0, "volume": 0},
    ]                                                              # the bar without a close is dropped


@pytest.mark.parametrize("value", [None, 0, -1.0, math.nan, math.inf, "n/a", True])
def test_a_level_the_provider_did_not_give_is_none(value):
    assert chart_level(value) is None


def test_levels_are_rounded_to_four_decimals():
    assert chart_level(10.123456) == 10.1235
    assert chart_row("t", None, None, None, None, 5) is None
