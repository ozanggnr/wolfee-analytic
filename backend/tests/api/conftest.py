"""Fixtures for the /api/v1 tests: signed-in clients and instruments, without the login flow."""
import asyncio
import os
import secrets
import sys

import pytest
from starlette.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import AsyncSessionLocal, init_db  # noqa: E402
from main import app  # noqa: E402
from models import Instrument, User  # noqa: E402
from security_middleware import (  # noqa: E402
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    auth_rate_limiter,
    create_user_session,
    public_api_rate_limiter,
)


@pytest.fixture(scope="session", autouse=True)
def database_tables():
    asyncio.run(init_db())


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    auth_rate_limiter.requests.clear()
    public_api_rate_limiter.requests.clear()
    yield


class ApiUser:
    """A TestClient holding one user's session and CSRF cookies."""

    def __init__(self, client: TestClient, user_id: int, csrf_token: str):
        self.client = client
        self.user_id = user_id
        self._headers = {CSRF_HEADER_NAME: csrf_token}

    def get(self, url, **kwargs):
        return self.client.get(url, **kwargs)

    def post(self, url, json=None):
        return self.client.post(url, json=json, headers=self._headers)

    def patch(self, url, json=None):
        return self.client.patch(url, json=json, headers=self._headers)

    def delete(self, url):
        return self.client.delete(url, headers=self._headers)

    def create_portfolio(self, name=None, base_currency="TRY", kind="real") -> dict:
        body = {
            "name": name or f"Portfolio {secrets.token_hex(4)}",
            "base_currency": base_currency,
            "kind": kind,
        }
        response = self.post("/api/v1/portfolios", json=body)
        assert response.status_code == 201, response.text
        return response.json()


async def _create_user_with_session() -> tuple[int, str]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"ledger_{secrets.token_hex(6)}@example.com",
            password_hash="unusable-test-hash",
            email_verified=True,
            failed_login_count=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        _, session_id = await create_user_session(session, user.id)
        return user.id, session_id


@pytest.fixture
def make_user():
    def _make() -> ApiUser:
        user_id, session_id = asyncio.run(_create_user_with_session())
        client = TestClient(app)
        csrf_token = secrets.token_hex(16)
        client.cookies.set(SESSION_COOKIE_NAME, session_id)
        client.cookies.set(CSRF_COOKIE_NAME, csrf_token)
        return ApiUser(client, user_id, csrf_token)

    return _make


@pytest.fixture
def user(make_user) -> ApiUser:
    return make_user()


async def _insert_instrument(exchange: str, currency: str, is_active: bool) -> dict:
    symbol = f"ZZ{secrets.token_hex(4).upper()}"
    provider_symbol = f"{symbol}.IS" if exchange == "BIST" else symbol
    async with AsyncSessionLocal() as session:
        instrument = Instrument(
            symbol=symbol,
            exchange=exchange,
            provider_symbol=provider_symbol,
            name=f"Test {symbol}",
            currency=currency,
            asset_class="equity",
            is_active=is_active,
        )
        session.add(instrument)
        await session.commit()
    return {"symbol": symbol, "exchange": exchange, "provider_symbol": provider_symbol, "currency": currency}


@pytest.fixture
def make_instrument():
    def _make(exchange="BIST", currency="TRY", is_active=True) -> dict:
        return asyncio.run(_insert_instrument(exchange, currency, is_active))

    return _make


@pytest.fixture
def instrument(make_instrument) -> dict:
    return make_instrument()


async def _insert_quote(symbol: str, price: float, currency: str, age):
    from datetime import datetime, timezone

    from models import StockData

    updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - age  # the cache stores naive UTC
    async with AsyncSessionLocal() as session:
        session.add(StockData(symbol=symbol, name=symbol, price=price, currency=currency, updated_at=updated_at))
        await session.commit()


@pytest.fixture
def add_quote():
    """Write a row into the latest-quote cache, `age` old (a timedelta)."""
    from datetime import timedelta

    def _add(symbol: str, price: float, currency: str = "TRY", age=timedelta(minutes=5)) -> None:
        asyncio.run(_insert_quote(symbol, price, currency, age))

    return _add


async def _replace_fx_rate(pair: str, buying):
    from datetime import datetime, timezone

    from sqlalchemy import delete

    from models import ExchangeRate

    async with AsyncSessionLocal() as session:
        await session.execute(delete(ExchangeRate).where(ExchangeRate.pair == pair))
        if buying is not None:
            session.add(ExchangeRate(pair=pair, display_name=pair, buying=buying, selling=buying,
                                     updated_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        await session.commit()


@pytest.fixture
def fx_rate():
    """Set (or with None, remove) a cached `XXX/TRY` rate; every pair touched is removed afterwards."""
    touched = set()

    def _set(pair: str, buying) -> None:
        touched.add(pair)
        asyncio.run(_replace_fx_rate(pair, buying))

    yield _set
    for pair in touched:
        asyncio.run(_replace_fx_rate(pair, None))
