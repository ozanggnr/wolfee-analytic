"""REQ-31 (c): the /api/chart last-resort fallback keeps a missing open/high/low null.

main.py had a third copy of the Yahoo chart parser that filled a missing open, high
or low with the close. The fallback now goes through Agent 3's helper (chart_row).
"""
import pytest

import data_sources.global_market as global_market
import data_sources.turkish_market as turkish_market

CHART_BODY = {"chart": {"result": [{
    "timestamp": [1794555000, 1794641400],
    "indicators": {"quote": [{"open": [None, 315.75], "high": [None, 323.5], "low": [None, 315.0],
                              "close": [319.25, 320.25], "volume": [None, 29607838]}]},
}]}}


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return CHART_BODY


class Client:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None):
        return Response()


@pytest.mark.parametrize("module, history, symbol", [
    (turkish_market, "fetch_bist_history", "THYAO"),
    (global_market, "fetch_global_history", "AAPL"),
])
def test_the_last_resort_chart_keeps_missing_values_null(user, monkeypatch, module, history, symbol):
    monkeypatch.setattr(module, history, lambda *args, **kwargs: None)  # first attempt failed
    monkeypatch.setattr(module.httpx, "Client", Client)

    response = user.get(f"/api/chart/{symbol}/1mo")

    assert response.status_code == 200, response.text
    first, second = response.json()["history"]
    assert (first["open"], first["high"], first["low"], first["close"]) == (None, None, None, 319.25)
    assert (second["open"], second["high"], second["low"], second["close"]) == (315.75, 323.5, 315.0, 320.25)
