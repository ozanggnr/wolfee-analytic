"""REQ-19: the server decides a watchlist ticker's market.

Smoke test: adding THYAO stored market "US". The frontend sends an explicit
market hint ("US" whenever its own BIST list lookup misses) and the backend
trusted it. A known symbol is now resolved with quant.symbols.normalize_symbol and
the instruments table; the client's hint only decides for unknown symbols.
"""
import secrets

import pytest

import watchlist_routes


@pytest.fixture(autouse=True)
def no_live_quotes(monkeypatch):
    """Reading the watchlist back would otherwise fetch uncached tickers from Yahoo."""
    monkeypatch.setattr(watchlist_routes, "analyze_stock", lambda *args, **kwargs: None)


def _add(user, ticker, market=None):
    body = {"ticker": ticker} if market is None else {"ticker": ticker, "market": market}
    return user.post("/api/watchlist", json=body)


def _stored(user):
    return {item["ticker"]: item["market"] for item in user.get("/api/watchlist").json()["items"]}


@pytest.mark.parametrize("ticker, hint, stored_ticker, market", [
    ("THYAO", None, "THYAO", "BIST100"),
    ("THYAO", "US", "THYAO", "BIST100"),        # the smoke-test case: the frontend's hint was wrong
    ("thyao.is", None, "THYAO", "BIST100"),
    ("THYAO.IS", "US", "THYAO", "BIST100"),     # an explicit suffix beats the hint
    ("AAPL", None, "AAPL", "US"),
    ("AAPL", "BIST100", "AAPL", "US"),
    ("GC=F", None, "GC=F", "COMMODITY"),
    ("GC=F", "US", "GC=F", "COMMODITY"),
])
def test_known_symbols_get_their_real_market(user, ticker, hint, stored_ticker, market):
    response = _add(user, ticker, hint)

    assert response.status_code == 201, response.text
    assert (response.json()["ticker"], response.json()["market"]) == (stored_ticker, market)
    assert _stored(user) == {stored_ticker: market}


def test_the_instruments_table_beats_the_hint(user, make_instrument):
    listed = make_instrument(exchange="US", currency="USD")

    response = _add(user, listed["symbol"], "BIST100")

    assert response.json()["market"] == "US"


def test_an_unknown_symbol_follows_the_hint(user):
    unknown = f"ZQ{secrets.token_hex(3).upper()}"

    assert _add(user, unknown, "US").json()["market"] == "US"


def test_an_unknown_symbol_without_a_hint_is_treated_as_bist(user):
    unknown = f"ZQ{secrets.token_hex(3).upper()}"

    response = _add(user, unknown)

    assert (response.json()["ticker"], response.json()["market"]) == (unknown, "BIST100")


@pytest.mark.parametrize("ticker, hint", [("THYAO.XX", None), ("AAPL", "COMMODITY")])
def test_symbols_that_cannot_be_resolved_are_refused(user, ticker, hint):
    response = _add(user, ticker, hint)

    assert response.status_code == 422, response.text
    assert _stored(user) == {}


def test_the_same_symbol_with_and_without_suffix_is_one_entry(user):
    _add(user, "THYAO")

    again = _add(user, "THYAO.IS")

    assert "already" in again.json()["message"]
    assert _stored(user) == {"THYAO": "BIST100"}
