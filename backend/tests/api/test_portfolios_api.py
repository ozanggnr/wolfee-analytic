"""Portfolio endpoints: CRUD, validation, soft delete and user-level isolation."""
import secrets

import pytest
from starlette.testclient import TestClient

from main import app

BASE = "/api/v1/portfolios"


def unique_name() -> str:
    return f"Long term {secrets.token_hex(4)}"


def test_listing_portfolios_requires_a_session():
    response = TestClient(app).get(BASE)

    assert response.status_code == 401


def test_creating_a_portfolio_without_csrf_header_is_rejected(user):
    body = {"name": unique_name(), "base_currency": "TRY"}

    response = user.client.post(BASE, json=body)

    assert response.status_code == 403


def test_create_returns_the_portfolio_without_exposing_the_owner(user):
    name = unique_name()

    response = user.post(BASE, json={"name": f"  {name}  ", "base_currency": "try"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == name
    assert body["base_currency"] == "TRY"
    assert body["kind"] == "real"
    assert body["archived_at"] is None
    assert body["created_at"].endswith("+00:00")
    assert isinstance(body["id"], int)
    assert "user_id" not in body


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "base_currency": "TRY"},
        {"name": "   ", "base_currency": "TRY"},
        {"name": "x" * 101, "base_currency": "TRY"},
        {"name": "Valid", "base_currency": "XXX"},
        {"name": "Valid", "base_currency": "TR"},
        {"name": "Valid", "base_currency": "TRY", "kind": "margin"},
        {"name": "Valid", "base_currency": "TRY", "user_id": 1},
        {"base_currency": "TRY"},
    ],
)
def test_create_rejects_invalid_input(user, body):
    response = user.post(BASE, json=body)

    assert response.status_code == 422


def test_an_active_portfolio_name_is_unique_per_user(user):
    name = unique_name()
    user.create_portfolio(name=name)

    response = user.post(BASE, json={"name": name, "base_currency": "USD"})

    assert response.status_code == 409


def test_two_users_may_use_the_same_portfolio_name(make_user):
    name = unique_name()
    make_user().create_portfolio(name=name)

    response = make_user().post(BASE, json={"name": name, "base_currency": "TRY"})

    assert response.status_code == 201


def test_list_returns_only_the_callers_portfolios_with_pagination(make_user):
    owner, stranger = make_user(), make_user()
    created = [owner.create_portfolio() for _ in range(3)]
    stranger.create_portfolio()

    page = owner.get(BASE, params={"limit": 2, "offset": 0}).json()
    rest = owner.get(BASE, params={"limit": 2, "offset": 2}).json()

    assert page["total"] == 3
    assert (page["limit"], page["offset"]) == (2, 0)
    assert len(page["items"]) == 2
    listed_ids = {item["id"] for item in page["items"] + rest["items"]}
    assert listed_ids == {portfolio["id"] for portfolio in created}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"limit": "abc"}])
def test_list_rejects_out_of_range_pagination(user, params):
    response = user.get(BASE, params=params)

    assert response.status_code == 422


def test_get_returns_one_portfolio(user):
    created = user.create_portfolio(kind="paper", base_currency="USD")

    response = user.get(f"{BASE}/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_responses_are_not_cacheable(user):
    response = user.get(BASE)

    assert response.headers["Cache-Control"] == "no-store, private"


def test_another_users_portfolio_is_reported_as_not_found(make_user):
    owner, stranger = make_user(), make_user()
    portfolio = owner.create_portfolio()
    url = f"{BASE}/{portfolio['id']}"

    assert stranger.get(url).status_code == 404
    assert stranger.patch(url, json={"name": "Taken over"}).status_code == 404
    assert stranger.delete(url).status_code == 404
    assert owner.get(url).json() == portfolio


def test_unknown_and_malformed_ids_do_not_reach_the_database(user):
    assert user.get(f"{BASE}/2147483647").status_code == 404
    assert user.get(f"{BASE}/0").status_code == 422
    assert user.get(f"{BASE}/99999999999999999999").status_code == 422


def test_rename_changes_only_the_name(user):
    created = user.create_portfolio()
    new_name = unique_name()

    response = user.patch(f"{BASE}/{created['id']}", json={"name": new_name})

    assert response.status_code == 200
    assert response.json() == {**created, "name": new_name}


def test_rename_cannot_change_other_fields(user):
    created = user.create_portfolio()

    response = user.patch(f"{BASE}/{created['id']}", json={"name": "Ok", "base_currency": "USD"})

    assert response.status_code == 422


def test_rename_to_an_existing_active_name_conflicts(user):
    first = user.create_portfolio()
    second = user.create_portfolio()

    response = user.patch(f"{BASE}/{second['id']}", json={"name": first["name"]})

    assert response.status_code == 409


def test_archive_is_a_soft_delete_that_keeps_the_row(user):
    created = user.create_portfolio()
    url = f"{BASE}/{created['id']}"

    response = user.delete(url)

    assert response.status_code == 200
    assert response.json()["archived_at"] is not None
    assert user.get(url).json()["archived_at"] is not None
    active_ids = {item["id"] for item in user.get(BASE).json()["items"]}
    all_ids = {item["id"] for item in user.get(BASE, params={"include_archived": True}).json()["items"]}
    assert created["id"] not in active_ids
    assert created["id"] in all_ids


def test_archiving_twice_keeps_the_first_archive_time(user):
    url = f"{BASE}/{user.create_portfolio()['id']}"
    first = user.delete(url).json()

    second = user.delete(url)

    assert second.status_code == 200
    assert second.json()["archived_at"] == first["archived_at"]


def test_an_archived_portfolio_cannot_be_renamed(user):
    url = f"{BASE}/{user.create_portfolio()['id']}"
    user.delete(url)

    response = user.patch(url, json={"name": unique_name()})

    assert response.status_code == 409


def test_a_name_is_reusable_after_its_portfolio_is_archived(user):
    created = user.create_portfolio()
    user.delete(f"{BASE}/{created['id']}")

    response = user.post(BASE, json={"name": created["name"], "base_currency": "TRY"})

    assert response.status_code == 201


@pytest.mark.parametrize("name", ["bad\u0000byte", "zero​width", "right‮left", "new\nline"])
def test_names_with_control_or_invisible_characters_are_rejected(user, name):
    created = user.create_portfolio()

    assert user.post(BASE, json={"name": name, "base_currency": "TRY"}).status_code == 422
    assert user.patch(f"{BASE}/{created['id']}", json={"name": name}).status_code == 422
