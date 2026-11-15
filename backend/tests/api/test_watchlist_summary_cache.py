"""REQ-21: the watchlist summary reflects an add or remove immediately.

The server cache was already evicted on POST/DELETE, but the summary was sent with
`Cache-Control: private, max-age=60`, so after a change the browser kept showing
its HTTP-cached copy (the frontend refetches without force_refresh). A request that
was computing while the watchlist changed could also put the old summary back.
"""
import pytest

import watchlist_routes


@pytest.fixture(autouse=True)
def no_live_quotes(monkeypatch):
    monkeypatch.setattr(watchlist_routes, "analyze_stock", lambda *args, **kwargs: None)


def _summary(user):
    response = user.get("/api/watchlist/summary")
    assert response.status_code == 200, response.text
    return response


def _symbols(response):
    return sorted(change["symbol"] for change in response.json()["ticker_changes"])


def test_the_summary_changes_immediately_after_add_and_remove(user):
    assert user.post("/api/watchlist", json={"ticker": "AAPL"}).status_code == 201
    assert _symbols(_summary(user)) == ["AAPL"]
    assert _summary(user).json()["from_cache"] is True  # the server cache is in use

    user.post("/api/watchlist", json={"ticker": "THYAO"})
    after_add = _summary(user)
    user.delete("/api/watchlist/AAPL")
    after_remove = _summary(user)

    assert (after_add.json()["total_count"], _symbols(after_add)) == (2, ["AAPL", "THYAO"])
    assert (after_remove.json()["total_count"], _symbols(after_remove)) == (1, ["THYAO"])
    assert after_add.json()["from_cache"] is False and after_remove.json()["from_cache"] is False


@pytest.mark.parametrize("watching", [False, True])
def test_browsers_may_not_reuse_a_summary(user, watching):
    if watching:
        user.post("/api/watchlist", json={"ticker": "AAPL"})
        _summary(user)  # fill the server cache, so the cached branch is checked too

    response = _summary(user)

    assert response.headers["Cache-Control"] == "no-store, private"


def test_a_summary_computed_across_a_change_is_not_cached(user, monkeypatch):
    user.post("/api/watchlist", json={"ticker": "AAPL"})
    real_enrich = watchlist_routes._enrich_watchlist_tickers

    async def enrich_while_the_watchlist_changes(db, items):
        enriched = await real_enrich(db, items)
        watchlist_routes.invalidate_user_cache(user.user_id)  # an add commits meanwhile
        return enriched

    monkeypatch.setattr(watchlist_routes, "_enrich_watchlist_tickers", enrich_while_the_watchlist_changes)
    _summary(user)
    monkeypatch.setattr(watchlist_routes, "_enrich_watchlist_tickers", real_enrich)

    assert _summary(user).json()["from_cache"] is False
