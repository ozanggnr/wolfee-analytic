"""Transaction ledger endpoints: append, list, void, validation and user-level isolation."""
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from main import app

TRADE_DATE = "2026-03-10"


def ledger_url(portfolio: dict) -> str:
    return f"/api/v1/portfolios/{portfolio['id']}/transactions"


def buy(instrument: dict, **overrides) -> dict:
    body = {
        "type": "BUY",
        "symbol": instrument["symbol"],
        "quantity": "10",
        "price": "250.50",
        "fee": "1.25",
        "trade_date": TRADE_DATE,
    }
    return {**body, **overrides}


def record(user, portfolio: dict, body: dict) -> dict:
    response = user.post(ledger_url(portfolio), json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------
# Append
# ------------------------------------------------------------------

def test_the_ledger_requires_a_session():
    response = TestClient(app).get("/api/v1/portfolios/1/transactions")

    assert response.status_code == 401


def test_buy_is_stored_with_exact_decimal_strings_and_provenance(user, instrument):
    portfolio = user.create_portfolio(base_currency="TRY")

    response = user.post(ledger_url(portfolio), json=buy(instrument, note="  first lot  "))

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "BUY"
    assert body["symbol"] == instrument["symbol"]
    assert body["exchange"] == "BIST"
    assert body["quantity"] == "10.00000000"
    assert body["price"] == "250.500000"
    assert body["fee"] == "1.250000"
    assert body["currency"] == "TRY"
    assert body["fx_rate_to_base"] == "1.00000000"
    assert body["trade_date"] == TRADE_DATE
    assert body["note"] == "first lot"
    assert body["source"] == "manual"
    assert body["portfolio_id"] == portfolio["id"]
    assert body["voids_transaction_id"] is None
    assert body["voided_by_transaction_id"] is None
    assert body["created_at"].endswith("+00:00")
    assert "created_by_user_id" not in body


def test_the_provider_spelling_of_a_symbol_resolves_to_the_same_instrument(user, instrument):
    portfolio = user.create_portfolio()

    body = record(user, portfolio, buy(instrument, symbol=instrument["provider_symbol"].lower()))

    assert body["symbol"] == instrument["symbol"]


def test_small_quantities_keep_all_eight_decimal_places(user, instrument):
    portfolio = user.create_portfolio()

    body = record(user, portfolio, buy(instrument, quantity="0.00000001", price="0.000001", fee="0"))

    assert body["quantity"] == "0.00000001"
    assert body["price"] == "0.000001"
    assert body["fee"] == "0.000000"


@pytest.mark.parametrize(
    "overrides",
    [
        {"price": 250.5},
        {"quantity": 1.5},
        {"fee": 0.1},
        {"quantity": "0.000000001"},
        {"price": "1.0000001"},
        {"quantity": "-1"},
        {"price": "-0.01"},
        {"fee": "-1"},
        {"quantity": "NaN"},
        {"price": "Infinity"},
        {"quantity": "abc"},
        {"quantity": True},
    ],
)
def test_amounts_must_be_exact_non_negative_decimals(user, instrument, overrides):
    portfolio = user.create_portfolio()

    response = user.post(ledger_url(portfolio), json=buy(instrument, **overrides))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"type": "BUY", "quantity": "1", "price": "1", "trade_date": TRADE_DATE},
        {"type": "BUY", "symbol": "SYM", "quantity": "0", "price": "1", "trade_date": TRADE_DATE},
        {"type": "BUY", "symbol": "SYM", "quantity": "1", "trade_date": TRADE_DATE},
        {"type": "SELL", "symbol": "SYM", "quantity": "1", "trade_date": TRADE_DATE},
        {"type": "DIVIDEND", "symbol": "SYM", "quantity": "1", "trade_date": TRADE_DATE},
        {"type": "SPLIT", "symbol": "SYM", "quantity": "2", "price": "1", "trade_date": TRADE_DATE},
        {"type": "SPLIT", "symbol": "SYM", "quantity": "2", "fee": "1", "trade_date": TRADE_DATE},
        {"type": "SPLIT", "symbol": "SYM", "quantity": "0", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "100", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "100", "currency": "TRY", "symbol": "SYM", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "0", "currency": "TRY", "trade_date": TRADE_DATE},
        {"type": "WITHDRAWAL", "quantity": "5", "currency": "TRY", "fee": "1", "trade_date": TRADE_DATE},
        {"type": "WITHDRAWAL", "quantity": "5", "currency": "TRY", "price": "1", "trade_date": TRADE_DATE},
        {"type": "FEE", "currency": "TRY", "fee": "0", "trade_date": TRADE_DATE},
        {"type": "FEE", "currency": "TRY", "fee": "3", "quantity": "1", "trade_date": TRADE_DATE},
        {"type": "FEE", "fee": "3", "trade_date": TRADE_DATE},
        {"type": "TRANSFER", "quantity": "1", "currency": "TRY", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY"},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TL", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "1", "currency": "T1Y", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "trade_date": "10/03/2026"},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "trade_date": "1899-12-31"},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "exchange": "BIST", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "trade_date": TRADE_DATE, "source": "import"},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "trade_date": TRADE_DATE, "note": "n" * 501},
        {"type": "BUY", "symbol": "../etc", "quantity": "1", "price": "1", "trade_date": TRADE_DATE},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "trade_date": TRADE_DATE,
         "executed_at": "2026-03-10T10:00:00"},
        {"type": "DEPOSIT", "quantity": "1", "currency": "TRY", "trade_date": TRADE_DATE,
         "fx_rate_to_base": "0"},
    ],
)
def test_fields_must_fit_the_transaction_type(user, body):
    portfolio = user.create_portfolio()

    response = user.post(ledger_url(portfolio), json=body)

    assert response.status_code == 422


def test_a_trade_dated_in_the_future_is_rejected(user, instrument):
    portfolio = user.create_portfolio()
    future = (date.today() + timedelta(days=3)).isoformat()

    response = user.post(ledger_url(portfolio), json=buy(instrument, trade_date=future))

    assert response.status_code == 422


def test_an_unknown_symbol_is_rejected_rather_than_guessed(user):
    portfolio = user.create_portfolio()

    response = user.post(ledger_url(portfolio), json=buy({"symbol": "NOSUCHSYM"}))

    assert response.status_code == 422
    assert "NOSUCHSYM" in response.json()["detail"]


def test_an_inactive_instrument_cannot_be_traded(user, make_instrument):
    portfolio = user.create_portfolio()
    delisted = make_instrument(is_active=False)

    response = user.post(ledger_url(portfolio), json=buy(delisted))

    assert response.status_code == 422


def test_a_trade_currency_must_match_the_instrument(user, instrument):
    portfolio = user.create_portfolio()

    response = user.post(ledger_url(portfolio), json=buy(instrument, currency="USD"))

    assert response.status_code == 422


def test_a_foreign_currency_trade_stores_the_rate_given_at_trade_time(user, make_instrument):
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")

    body = record(user, portfolio, buy(us_stock, fx_rate_to_base="38.4512"))

    assert body["currency"] == "USD"
    assert body["fx_rate_to_base"] == "38.45120000"


def test_a_missing_foreign_rate_stays_null_and_is_never_estimated(user, make_instrument):
    portfolio = user.create_portfolio(base_currency="TRY")
    us_stock = make_instrument(exchange="US", currency="USD")

    body = record(user, portfolio, buy(us_stock))

    assert body["fx_rate_to_base"] is None


def test_a_base_currency_trade_cannot_carry_a_rate_other_than_one(user, instrument):
    portfolio = user.create_portfolio(base_currency="TRY")

    response = user.post(ledger_url(portfolio), json=buy(instrument, fx_rate_to_base="1.05"))

    assert response.status_code == 422


def test_cash_and_corporate_action_rows_are_accepted(user, instrument):
    portfolio = user.create_portfolio(base_currency="TRY")

    deposit = record(user, portfolio, {"type": "DEPOSIT", "quantity": "5000", "currency": "try",
                                       "trade_date": TRADE_DATE})
    fee = record(user, portfolio, {"type": "FEE", "fee": "12.5", "currency": "TRY", "trade_date": TRADE_DATE})
    split = record(user, portfolio, {"type": "SPLIT", "symbol": instrument["symbol"], "quantity": "2",
                                     "trade_date": TRADE_DATE})
    dividend = record(user, portfolio, {"type": "DIVIDEND", "symbol": instrument["symbol"], "quantity": "10",
                                        "price": "1.5", "fee": "0.15", "trade_date": TRADE_DATE})

    assert (deposit["symbol"], deposit["quantity"], deposit["price"]) == (None, "5000.00000000", None)
    assert (fee["quantity"], fee["fee"]) == ("0.00000000", "12.500000")
    assert (split["quantity"], split["price"]) == ("2.00000000", None)
    assert (dividend["price"], dividend["fee"]) == ("1.500000", "0.150000")


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------

def test_the_ledger_lists_newest_trades_first_with_pagination(user, instrument):
    portfolio = user.create_portfolio()
    oldest = record(user, portfolio, buy(instrument, trade_date="2026-01-05"))
    newest = record(user, portfolio, buy(instrument, trade_date="2026-03-01"))
    middle = record(user, portfolio, buy(instrument, trade_date="2026-02-01"))
    same_day_later = record(user, portfolio, buy(instrument, trade_date="2026-02-01"))

    first_page = user.get(ledger_url(portfolio), params={"limit": 3}).json()
    second_page = user.get(ledger_url(portfolio), params={"limit": 3, "offset": 3}).json()

    assert first_page["total"] == 4
    assert [row["id"] for row in first_page["items"]] == [newest["id"], same_day_later["id"], middle["id"]]
    assert [row["id"] for row in second_page["items"]] == [oldest["id"]]


def test_each_portfolio_has_its_own_ledger(user, instrument):
    first, second = user.create_portfolio(), user.create_portfolio()
    record(user, first, buy(instrument))

    page = user.get(ledger_url(second)).json()

    assert page == {"items": [], "total": 0, "limit": 50, "offset": 0}


# ------------------------------------------------------------------
# Isolation
# ------------------------------------------------------------------

def test_another_users_ledger_cannot_be_read_written_or_voided(make_user, instrument):
    owner, stranger = make_user(), make_user()
    portfolio = owner.create_portfolio()
    transaction = record(owner, portfolio, buy(instrument))
    url = ledger_url(portfolio)

    assert stranger.get(url).status_code == 404
    assert stranger.post(url, json=buy(instrument)).status_code == 404
    assert stranger.post(f"{url}/{transaction['id']}/void").status_code == 404

    page = owner.get(url).json()
    assert page["total"] == 1
    assert page["items"][0]["voided_by_transaction_id"] is None


def test_a_transaction_cannot_be_voided_through_a_different_portfolio(make_user, instrument):
    owner, stranger = make_user(), make_user()
    transaction = record(owner, owner.create_portfolio(), buy(instrument))
    other_portfolio = owner.create_portfolio()
    strangers_portfolio = stranger.create_portfolio()

    own_other = owner.post(f"{ledger_url(other_portfolio)}/{transaction['id']}/void")
    through_stranger = stranger.post(f"{ledger_url(strangers_portfolio)}/{transaction['id']}/void")

    assert own_other.status_code == 404
    assert through_stranger.status_code == 404


# ------------------------------------------------------------------
# Void and immutability
# ------------------------------------------------------------------

def test_void_appends_a_reversal_and_leaves_the_original_row_intact(user, instrument):
    portfolio = user.create_portfolio()
    original = record(user, portfolio, buy(instrument))

    response = user.post(f"{ledger_url(portfolio)}/{original['id']}/void", json={"note": "wrong price"})

    assert response.status_code == 201
    reversal = response.json()
    assert reversal["voids_transaction_id"] == original["id"]
    assert reversal["note"] == "wrong price"
    for field in ("type", "symbol", "quantity", "price", "fee", "currency", "fx_rate_to_base", "trade_date"):
        assert reversal[field] == original[field]

    rows = {row["id"]: row for row in user.get(ledger_url(portfolio)).json()["items"]}
    assert len(rows) == 2
    assert rows[original["id"]] == {**original, "voided_by_transaction_id": reversal["id"]}


def test_void_works_without_a_request_body(user, instrument):
    portfolio = user.create_portfolio()
    original = record(user, portfolio, buy(instrument))

    response = user.post(f"{ledger_url(portfolio)}/{original['id']}/void")

    assert response.status_code == 201
    assert response.json()["note"] is None


def test_a_transaction_can_be_voided_only_once(user, instrument):
    portfolio = user.create_portfolio()
    original = record(user, portfolio, buy(instrument))
    void_url = f"{ledger_url(portfolio)}/{original['id']}/void"
    user.post(void_url)

    response = user.post(void_url)

    assert response.status_code == 409
    assert user.get(ledger_url(portfolio)).json()["total"] == 2


def test_a_reversal_cannot_itself_be_voided(user, instrument):
    portfolio = user.create_portfolio()
    original = record(user, portfolio, buy(instrument))
    reversal = user.post(f"{ledger_url(portfolio)}/{original['id']}/void").json()

    response = user.post(f"{ledger_url(portfolio)}/{reversal['id']}/void")

    assert response.status_code == 409


def test_voiding_an_unknown_transaction_is_not_found(user):
    portfolio = user.create_portfolio()

    response = user.post(f"{ledger_url(portfolio)}/987654321/void")

    assert response.status_code == 404


def test_there_is_no_endpoint_to_edit_or_delete_a_transaction(user, instrument):
    portfolio = user.create_portfolio()
    transaction = record(user, portfolio, buy(instrument))
    url = f"{ledger_url(portfolio)}/{transaction['id']}"

    assert user.patch(url, json={"quantity": "99"}).status_code in (404, 405)
    assert user.delete(url).status_code in (404, 405)
    assert user.client.put(url, json=buy(instrument), headers=user._headers).status_code in (404, 405)
    assert user.get(ledger_url(portfolio)).json()["items"] == [transaction]


def test_an_archived_portfolio_keeps_its_history_but_accepts_no_new_rows(user, instrument):
    portfolio = user.create_portfolio()
    transaction = record(user, portfolio, buy(instrument))
    user.delete(f"/api/v1/portfolios/{portfolio['id']}")

    append = user.post(ledger_url(portfolio), json=buy(instrument))
    void = user.post(f"{ledger_url(portfolio)}/{transaction['id']}/void")
    history = user.get(ledger_url(portfolio))

    assert append.status_code == 409
    assert void.status_code == 409
    assert history.status_code == 200
    assert history.json()["total"] == 1


# ------------------------------------------------------------------
# Timestamps, notes and caching
# ------------------------------------------------------------------

def test_executed_at_is_normalised_to_utc(user):
    portfolio = user.create_portfolio()

    body = record(user, portfolio, {"type": "DEPOSIT", "quantity": "1", "currency": "TRY",
                                    "trade_date": TRADE_DATE, "executed_at": "2026-03-10T10:00:00+03:00"})

    assert body["executed_at"] == "2026-03-10T07:00:00+00:00"
    assert user.get(ledger_url(portfolio)).json()["items"][0]["executed_at"] == "2026-03-10T07:00:00+00:00"


def test_an_empty_void_note_is_stored_as_null(user, instrument):
    portfolio = user.create_portfolio()
    original = record(user, portfolio, buy(instrument))

    response = user.post(f"{ledger_url(portfolio)}/{original['id']}/void", json={"note": "   "})

    assert response.json()["note"] is None


def test_error_responses_are_not_cacheable_either(user):
    response = user.get("/api/v1/portfolios/2147483647/transactions")

    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize(
    "overrides",
    [
        {"note": "bad\u0000byte"},
        {"note": "hidden​space"},
        {"quantity": "٣"},
        {"currency": "uſd"},
        {"exchange": "ＢIST"},
    ],
)
def test_invisible_and_lookalike_characters_are_rejected(user, instrument, overrides):
    portfolio = user.create_portfolio()

    response = user.post(ledger_url(portfolio), json=buy(instrument, **overrides))

    assert response.status_code == 422


def test_a_note_may_span_lines(user, instrument):
    portfolio = user.create_portfolio()

    body = record(user, portfolio, buy(instrument, note="line one\nline two"))

    assert body["note"] == "line one\nline two"
