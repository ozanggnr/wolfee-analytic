"""Holdings and performance endpoints, with hand-checked figures.

Scenario used by most tests (TRY portfolio, one TRY instrument, FIFO requested explicitly):

    DEPOSIT 10000
    BUY   10 @ 100, fee 5   -> lot 1 cost 1005
    BUY   10 @ 120, fee 5   -> lot 2 cost 1205
    SELL  15 @ 130, fee 10  -> net proceeds 1940
        lot 1: 10 units, cost 1005,  proceeds 1940*10/15 = 1293.3333333333, P/L 288.3333333333
        lot 2:  5 units, cost  602.5, proceeds 1940 - 1293.3333333333 = 646.6666666667, P/L 44.1666666667
        realised total 332.5
    DIVIDEND 5 units @ 2, fee 1 -> 9 net
    quote 140 -> 5 units worth 700; cost 602.5; unrealised 97.5
    cash: 10000 - 1005 - 1205 + 1940 + 9 = 9739; fees 5 + 5 + 10 = 20

Weighted average: pool 20 units for 2210 -> sell 15 costs 1657.5 -> realised 282.5;
remaining 5 units cost 552.5 -> unrealised 147.5.
"""
from datetime import timedelta

FIFO = {"cost_basis_method": "fifo"}

import pytest
from starlette.testclient import TestClient

from main import app


def url(portfolio: dict, view: str) -> str:
    return f"/api/v1/portfolios/{portfolio['id']}/{view}"


def record(user, portfolio: dict, body: dict) -> dict:
    response = user.post(url(portfolio, "transactions"), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def trade(kind: str, symbol: str, quantity: str, price: str, fee: str = "0", day: str = "2026-01-10") -> dict:
    return {"type": kind, "symbol": symbol, "quantity": quantity, "price": price, "fee": fee, "trade_date": day}


@pytest.fixture
def scenario(user, instrument, add_quote):
    portfolio = user.create_portfolio(base_currency="TRY")
    symbol = instrument["symbol"]
    record(user, portfolio, {"type": "DEPOSIT", "quantity": "10000", "currency": "TRY", "trade_date": "2026-01-02"})
    buy_1 = record(user, portfolio, trade("BUY", symbol, "10", "100", "5", "2026-01-05"))
    buy_2 = record(user, portfolio, trade("BUY", symbol, "10", "120", "5", "2026-01-06"))
    sell = record(user, portfolio, trade("SELL", symbol, "15", "130", "10", "2026-01-07"))
    record(user, portfolio, trade("DIVIDEND", symbol, "5", "2", "1", "2026-01-08"))
    add_quote(instrument["provider_symbol"], 140.0)
    return {"portfolio": portfolio, "instrument": instrument, "buy_1": buy_1, "buy_2": buy_2, "sell": sell}


# ------------------------------------------------------------------
# Holdings
# ------------------------------------------------------------------

def test_holdings_are_derived_from_the_ledger_and_valued_at_the_cached_quote(user, scenario):
    body = user.get(url(scenario["portfolio"], "holdings"), params=FIFO).json()

    assert body["portfolio_id"] == scenario["portfolio"]["id"]
    assert body["base_currency"] == "TRY"
    assert body["cost_basis_method"] == "fifo"
    assert body["computed_at"].endswith("+00:00")
    assert body["is_complete"] is True
    assert body["unvalued_symbols"] == []
    assert (body["total_market_value"], body["total_cost_basis"], body["total_unrealized_pnl"]) == (
        "700.000000", "602.500000", "97.500000")

    [position] = body["positions"]
    instrument = scenario["instrument"]
    assert (position["symbol"], position["exchange"], position["currency"]) == (
        instrument["symbol"], "BIST", "TRY")
    assert position["quantity"] == "5.00000000"
    assert position["average_cost"] == "120.500000"
    assert position["cost_basis"] == position["cost_basis_base"] == "602.500000"
    assert position["market_value"] == position["market_value_base"] == "700.000000"
    assert position["unrealized_pnl"] == position["unrealized_pnl_base"] == "97.500000"
    assert position["weight"] == "1.0000000000"
    assert position["unavailable_reason"] is None
    assert position["fx_rate"] is None
    quote = position["quote"]
    assert (quote["price"], quote["currency"], quote["freshness"], quote["source"]) == (
        "140.000000", "TRY", "delayed", "wolfee_quote_cache")
    assert quote["as_of"].endswith("+00:00")


def test_weighted_average_cost_basis_is_the_default(user, scenario):
    body = user.get(url(scenario["portfolio"], "holdings")).json()

    [position] = body["positions"]
    assert body["cost_basis_method"] == "weighted_average"
    assert (position["cost_basis"], position["average_cost"], position["unrealized_pnl"]) == (
        "552.500000", "110.500000", "147.500000")


def test_an_unknown_cost_basis_method_is_rejected(user, scenario):
    response = user.get(url(scenario["portfolio"], "holdings"), params={"cost_basis_method": "lifo"})

    assert response.status_code == 422


def test_a_position_without_a_quote_is_reported_and_totals_stay_null(user, instrument):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "3", "50"))

    body = user.get(url(portfolio, "holdings")).json()

    [position] = body["positions"]
    assert position["unavailable_reason"] == "missing_quote"
    assert position["quote"] is None
    assert position["market_value"] is None and position["weight"] is None
    assert position["cost_basis"] == "150.000000"
    assert body["is_complete"] is False
    assert body["unvalued_symbols"] == [instrument["symbol"]]
    assert body["total_market_value"] is None and body["total_unrealized_pnl"] is None


def test_an_old_quote_is_labelled_stale(user, instrument, add_quote):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "1", "10"))
    add_quote(instrument["provider_symbol"], 11.0, age=timedelta(hours=3))

    [position] = user.get(url(portfolio, "holdings")).json()["positions"]

    assert position["quote"]["freshness"] == "stale"
    assert position["market_value"] == "11.000000"


def test_the_newest_cached_row_wins_whichever_spelling_it_uses(user, instrument, add_quote):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "1", "10"))
    add_quote(instrument["provider_symbol"], 11.0, age=timedelta(minutes=30))
    add_quote(instrument["symbol"], 12.5, age=timedelta(minutes=2))
    add_quote(instrument["symbol"], 0.0, age=timedelta(minutes=1))  # unusable rows are skipped

    [position] = user.get(url(portfolio, "holdings")).json()["positions"]

    assert position["quote"]["price"] == "12.500000"


def test_a_quote_in_another_currency_is_not_used(user, instrument, add_quote):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "1", "10"))
    add_quote(instrument["provider_symbol"], 11.0, currency="USD")

    [position] = user.get(url(portfolio, "holdings")).json()["positions"]

    assert position["unavailable_reason"] == "quote_currency_mismatch"
    assert position["market_value"] is None


def test_a_foreign_currency_position_without_a_cached_rate_is_not_converted(
        user, make_instrument, add_quote, fx_rate):
    fx_rate("USD/TRY", None)
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")
    record(user, portfolio, {**trade("BUY", us_stock["symbol"], "2", "150"), "fx_rate_to_base": "38.5"})
    add_quote(us_stock["provider_symbol"], 160.0, currency="USD")

    body = user.get(url(portfolio, "holdings")).json()

    [position] = body["positions"]
    assert position["market_value"] == "320.000000"
    assert position["unrealized_pnl"] == "20.000000"
    assert position["cost_basis_base"] == "11550.000000"
    assert position["market_value_base"] is None
    assert position["unavailable_reason"] == "missing_fx_rate"
    assert body["is_complete"] is False
    assert body["total_market_value"] is None


def test_an_empty_portfolio_has_no_positions_and_zero_totals(user):
    body = user.get(url(user.create_portfolio(), "holdings")).json()

    assert body["positions"] == []
    assert body["is_complete"] is True
    assert body["total_market_value"] == "0.000000"


def test_voided_trades_do_not_count(user, instrument, add_quote):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "2", "10"))
    voided = record(user, portfolio, trade("BUY", instrument["symbol"], "7", "10"))
    user.post(f"{url(portfolio, 'transactions')}/{voided['id']}/void")
    add_quote(instrument["provider_symbol"], 10.0)

    [position] = user.get(url(portfolio, "holdings")).json()["positions"]

    assert position["quantity"] == "2.00000000"


# ------------------------------------------------------------------
# Performance
# ------------------------------------------------------------------

def test_performance_reports_realised_unrealised_dividends_fees_and_cash(user, scenario):
    body = user.get(url(scenario["portfolio"], "performance"), params=FIFO).json()

    assert body["realized_pnl"] == [{"currency": "TRY", "amount": "332.500000"}]
    assert body["realized_pnl_base"] == "332.500000"
    assert body["unrealized_pnl_base"] == "97.500000"
    assert body["dividends"] == [{"currency": "TRY", "amount": "9.000000"}]
    assert body["fees"] == [{"currency": "TRY", "amount": "20.000000"}]
    assert body["net_deposits"] == [{"currency": "TRY", "amount": "10000.000000"}]
    assert body["cash_balances"] == [{"currency": "TRY", "amount": "9739.000000"}]
    assert body["is_complete"] is True

    first, second = body["realized_lots"]
    assert (first["quantity"], first["cost"], first["proceeds"], first["pnl"]) == (
        "10.00000000", "1005.000000", "1293.333333", "288.333333")
    assert (second["quantity"], second["cost"], second["proceeds"], second["pnl"]) == (
        "5.00000000", "602.500000", "646.666667", "44.166667")
    assert first["buy_transaction_id"] == scenario["buy_1"]["id"]
    assert second["buy_transaction_id"] == scenario["buy_2"]["id"]
    assert first["sell_transaction_id"] == second["sell_transaction_id"] == scenario["sell"]["id"]
    assert (first["acquired"], first["disposed"]) == ("2026-01-05", "2026-01-07")
    assert first["symbol"] == scenario["instrument"]["symbol"]


def test_weighted_average_is_the_default_for_realised_profit(user, scenario):
    body = user.get(url(scenario["portfolio"], "performance")).json()

    assert body["cost_basis_method"] == "weighted_average"

    assert body["realized_pnl"] == [{"currency": "TRY", "amount": "282.500000"}]
    assert body["unrealized_pnl_base"] == "147.500000"


def test_realised_profit_in_base_is_null_when_a_foreign_trade_has_no_stored_rate(user, make_instrument):
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")
    record(user, portfolio, trade("BUY", us_stock["symbol"], "2", "100"))
    record(user, portfolio, trade("SELL", us_stock["symbol"], "2", "110", day="2026-01-11"))

    body = user.get(url(portfolio, "performance")).json()

    assert body["realized_pnl"] == [{"currency": "USD", "amount": "20.000000"}]
    assert body["realized_pnl_base"] is None


# ------------------------------------------------------------------
# Ledger consistency on write
# ------------------------------------------------------------------

def test_selling_more_than_is_held_is_rejected_and_nothing_is_stored(user, instrument):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "10", "5"))

    response = user.post(url(portfolio, "transactions"), json=trade("SELL", instrument["symbol"], "11", "6"))

    assert response.status_code == 409
    assert "exceeds" in response.json()["detail"]
    assert user.get(url(portfolio, "transactions")).json()["total"] == 1


def test_a_backdated_sell_before_the_purchase_is_rejected(user, instrument):
    portfolio = user.create_portfolio()
    record(user, portfolio, trade("BUY", instrument["symbol"], "10", "5", day="2026-01-10"))

    response = user.post(url(portfolio, "transactions"),
                         json=trade("SELL", instrument["symbol"], "1", "6", day="2026-01-09"))

    assert response.status_code == 409


def test_voiding_a_purchase_that_a_later_sale_depends_on_is_rejected(user, instrument):
    portfolio = user.create_portfolio()
    purchase = record(user, portfolio, trade("BUY", instrument["symbol"], "10", "5"))
    record(user, portfolio, trade("SELL", instrument["symbol"], "10", "6", day="2026-01-11"))

    response = user.post(f"{url(portfolio, 'transactions')}/{purchase['id']}/void")

    assert response.status_code == 409
    assert user.get(url(portfolio, "transactions")).json()["total"] == 2


def test_voiding_the_sale_first_then_the_purchase_is_allowed(user, instrument):
    portfolio = user.create_portfolio()
    purchase = record(user, portfolio, trade("BUY", instrument["symbol"], "10", "5"))
    sale = record(user, portfolio, trade("SELL", instrument["symbol"], "10", "6", day="2026-01-11"))
    void_url = f"{url(portfolio, 'transactions')}/{{}}/void"

    assert user.post(void_url.format(sale["id"])).status_code == 201
    assert user.post(void_url.format(purchase["id"])).status_code == 201
    assert user.get(url(portfolio, "holdings")).json()["positions"] == []


# ------------------------------------------------------------------
# Access
# ------------------------------------------------------------------

def test_analytics_require_a_session():
    client = TestClient(app)

    assert client.get("/api/v1/portfolios/1/holdings").status_code == 401
    assert client.get("/api/v1/portfolios/1/performance").status_code == 401


def test_another_users_analytics_are_not_found(make_user, scenario):
    stranger = make_user()

    for view in ("holdings", "performance"):
        response = stranger.get(url(scenario["portfolio"], view))
        assert response.status_code == 404
        assert response.headers["Cache-Control"] == "no-store, private"


def test_an_archived_portfolio_still_reports_its_history(user, scenario):
    user.delete(f"/api/v1/portfolios/{scenario['portfolio']['id']}")

    response = user.get(url(scenario["portfolio"], "performance"), params=FIFO)

    assert response.status_code == 200
    assert response.json()["realized_pnl"] == [{"currency": "TRY", "amount": "332.500000"}]


def test_analytics_responses_are_not_cacheable(user, scenario):
    response = user.get(url(scenario["portfolio"], "holdings"))

    assert response.headers["Cache-Control"] == "no-store, private"


def test_a_full_ledger_can_still_be_corrected_by_voids(user, instrument, monkeypatch):
    from services import ledger_adapter

    portfolio = user.create_portfolio()
    first = record(user, portfolio, trade("BUY", instrument["symbol"], "1", "10"))
    record(user, portfolio, trade("BUY", instrument["symbol"], "1", "10"))
    monkeypatch.setattr(ledger_adapter, "MAX_TRANSACTIONS_PER_PORTFOLIO", 2)

    assert user.post(url(portfolio, "transactions"), json=trade("BUY", instrument["symbol"], "1", "10")).status_code == 409
    assert user.post(f"{url(portfolio, 'transactions')}/{first['id']}/void").status_code == 201


def test_instruments_sharing_a_symbol_on_two_exchanges_stay_separate_and_unpriced(
        user, make_instrument, add_quote):
    import asyncio

    from sqlalchemy import update

    from database import AsyncSessionLocal
    from models import Instrument

    portfolio = user.create_portfolio(base_currency="TRY")
    a = make_instrument(exchange="US", currency="USD")
    b = make_instrument(exchange="CMDTY", currency="USD")

    async def share_symbol():
        async with AsyncSessionLocal() as session:
            await session.execute(update(Instrument).where(Instrument.symbol == b["symbol"], Instrument.exchange == "CMDTY").values(symbol=a["symbol"]))
            await session.commit()

    asyncio.run(share_symbol())
    record(user, portfolio, {**trade("BUY", a["symbol"], "1", "10"), "exchange": "US"})
    record(user, portfolio, {**trade("BUY", a["symbol"], "2", "20"), "exchange": "CMDTY"})
    add_quote(a["symbol"], 99.0, currency="USD")  # bare symbol: cannot tell which instrument it is

    positions = user.get(url(portfolio, "holdings")).json()["positions"]

    assert sorted((p["exchange"], p["quantity"]) for p in positions) == [("CMDTY", "2.00000000"), ("US", "1.00000000")]
    assert all(p["unavailable_reason"] == "missing_quote" for p in positions)


# ------------------------------------------------------------------
# FX (decision D3, REQ-15): foreign positions convert into TRY at the exchange_rates selling rate
# ------------------------------------------------------------------

def test_a_foreign_position_is_converted_into_try_at_the_cached_rate(user, make_instrument, add_quote, fx_rate):
    # 2 @ 150 USD bought at 38.5 -> cost 11550 TRY; quote 160 USD at 40 -> 12800 TRY; P/L 1250 TRY
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")
    record(user, portfolio, {**trade("BUY", us_stock["symbol"], "2", "150"), "fx_rate_to_base": "38.5"})
    add_quote(us_stock["provider_symbol"], 160.0, currency="USD")
    fx_rate("USD/TRY", 40.0)

    body = user.get(url(portfolio, "holdings")).json()

    [position] = body["positions"]
    assert position["unavailable_reason"] is None
    assert (position["market_value_base"], position["cost_basis_base"], position["unrealized_pnl_base"]) == (
        "12800.000000", "11550.000000", "1250.000000")
    fx = position["fx_rate"]
    assert (fx["base"], fx["quote"], fx["rate"], fx["source"]) == ("USD", "TRY", "40.00000000", "exchange_rates")
    assert body["is_complete"] is True
    assert (body["total_market_value"], body["total_unrealized_pnl"]) == ("12800.000000", "1250.000000")


def test_a_missing_rate_leaves_only_that_position_out_of_the_totals(
        user, instrument, make_instrument, add_quote, fx_rate):
    fx_rate("USD/TRY", None)
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")
    record(user, portfolio, trade("BUY", instrument["symbol"], "5", "120"))
    record(user, portfolio, {**trade("BUY", us_stock["symbol"], "1", "100"), "fx_rate_to_base": "38"})
    add_quote(instrument["provider_symbol"], 140.0)
    add_quote(us_stock["provider_symbol"], 110.0, currency="USD")

    body = user.get(url(portfolio, "holdings")).json()

    reasons = {p["symbol"]: p["unavailable_reason"] for p in body["positions"]}
    assert reasons == {instrument["symbol"]: None, us_stock["symbol"]: "missing_fx_rate"}
    weights = {p["symbol"]: p["weight"] for p in body["positions"]}
    assert weights == {instrument["symbol"]: "1.0000000000", us_stock["symbol"]: None}  # share of the partial total
    assert body["is_complete"] is False
    assert body["unvalued_symbols"] == [us_stock["symbol"]]
    assert (body["total_market_value"], body["total_cost_basis"], body["total_unrealized_pnl"]) == (
        "700.000000", "600.000000", "100.000000")
    performance = user.get(url(portfolio, "performance")).json()
    assert performance["unrealized_pnl_base"] == "100.000000"


def test_a_failed_rate_fetch_stored_as_zero_is_never_used(user, make_instrument, add_quote, fx_rate):
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")
    record(user, portfolio, {**trade("BUY", us_stock["symbol"], "1", "100"), "fx_rate_to_base": "38"})
    add_quote(us_stock["provider_symbol"], 110.0, currency="USD")
    fx_rate("USD/TRY", 0.0)

    body = user.get(url(portfolio, "holdings")).json()

    assert body["positions"][0]["unavailable_reason"] == "missing_fx_rate"
    assert body["total_market_value"] is None


def test_the_selling_rate_is_used_and_labelled_with_its_source(user, make_instrument, add_quote, fx_rate):
    # The fixture stores buying=0, so a valued position proves the selling rate was used.
    portfolio = user.create_portfolio()
    us_stock = make_instrument(exchange="US", currency="USD")
    record(user, portfolio, {**trade("BUY", us_stock["symbol"], "1", "100"), "fx_rate_to_base": "38"})
    add_quote(us_stock["provider_symbol"], 110.0, currency="USD")
    fx_rate("USD/TRY", 41.25)

    [position] = user.get(url(portfolio, "holdings")).json()["positions"]

    assert position["market_value_base"] == "4537.500000"
    assert (position["fx_rate"]["rate"], position["fx_rate"]["source"]) == ("41.25000000", "exchange_rates")
