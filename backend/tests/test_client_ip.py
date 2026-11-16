"""REQ-39: per-IP limits key on an address the client cannot choose.

On Fly (FLY_APP_NAME set) only Fly-Client-IP (set by the Fly proxy) is used; locally and in
tests the socket peer. CF-Connecting-IP and X-Forwarded-For are ignored everywhere, so a
fresh fake value per request no longer bypasses the auth rate limit, the invite-code limit,
the login lockout or the security log.
"""
import asyncio
import os
import secrets
import sys

import pytest
from sqlalchemy import select
from starlette.requests import Request
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_utils import hash_password  # noqa: E402
from database import AsyncSessionLocal, init_db  # noqa: E402
from main import app  # noqa: E402
from models import SecurityLog, User  # noqa: E402
from security_middleware import (  # noqa: E402
    RATE_LIMIT_MAX_REQUESTS, UNKNOWN_FLY_CLIENT, auth_rate_limiter, get_client_ip, invite_failure_limiter,
    public_api_rate_limiter,
)

INVITE = "invite-" + secrets.token_hex(6)
FLY_IP = "203.0.113.7"


@pytest.fixture(scope="module", autouse=True)
def tables():
    asyncio.run(init_db())


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    limiters = (auth_rate_limiter, invite_failure_limiter, public_api_rate_limiter)
    for limiter in limiters:
        limiter.requests.clear()
    yield
    for limiter in limiters:
        limiter.requests.clear()


@pytest.fixture
def on_fly(monkeypatch):
    monkeypatch.setenv("FLY_APP_NAME", "wolfee-analytics")


def _spoofed(n):
    """Fresh client-chosen addresses, as an attacker would send on every request."""
    return {"X-Forwarded-For": f"198.51.100.{n % 250}, 10.0.0.1", "CF-Connecting-IP": f"192.0.2.{n % 250}"}


def _request(headers, peer=("10.1.2.3", 5555)):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw, "client": peer})


# --- the key itself ---------------------------------------------------------------

def test_locally_the_socket_peer_is_used_and_every_header_ignored():
    headers = {**_spoofed(1), "Fly-Client-IP": FLY_IP}

    assert get_client_ip(_request(headers)) == "10.1.2.3"


def test_on_fly_only_fly_client_ip_is_used(on_fly):
    assert get_client_ip(_request({**_spoofed(1), "Fly-Client-IP": FLY_IP})) == FLY_IP
    assert get_client_ip(_request({**_spoofed(2), "Fly-Client-IP": FLY_IP})) == FLY_IP


@pytest.mark.parametrize("value", [None, "", "not-an-ip", "1.2.3.4, 5.6.7.8"])
def test_on_fly_a_missing_or_bad_header_falls_back_to_one_shared_key(on_fly, value):
    headers = _spoofed(3) if value is None else {**_spoofed(3), "Fly-Client-IP": value}

    assert get_client_ip(_request(headers)) == UNKNOWN_FLY_CLIENT  # never the peer or a spoofed header


def test_on_fly_ipv6_is_normalised(on_fly):
    assert get_client_ip(_request({"Fly-Client-IP": "2001:DB8::0001"})) == "2001:db8::1"


# --- the limits cannot be bypassed --------------------------------------------------

def _login(client, n, email="nobody@example.com", password="Wrong-password-1!", **headers):
    return client.post("/api/auth/login", json={"email": email, "password": password},
                       headers={**_spoofed(n), **headers})


def test_the_auth_rate_limit_holds_against_rotating_spoofed_headers():
    client = TestClient(app)

    codes = [_login(client, n).status_code for n in range(RATE_LIMIT_MAX_REQUESTS + 1)]

    assert codes[-1] == 429 and 429 not in codes[:-1]


def test_on_fly_the_auth_rate_limit_follows_fly_client_ip_only(on_fly):
    client = TestClient(app)

    codes = [_login(client, n, **{"Fly-Client-IP": FLY_IP}).status_code for n in range(RATE_LIMIT_MAX_REQUESTS + 1)]
    other = _login(client, 99, **{"Fly-Client-IP": "203.0.113.8"})

    assert codes[-1] == 429
    assert other.status_code != 429  # a different real client is not affected


def _register(client, n, code, **headers):
    return client.post("/api/auth/register",
                       json={"email": f"ip_{secrets.token_hex(5)}@example.com", "password": "TraderSecure2026!#",
                             "invite_code": code}, headers={**_spoofed(n), **headers})


@pytest.mark.parametrize("fly", [False, True])
def test_the_invite_limit_holds_against_rotating_spoofed_headers(monkeypatch, fly):
    if fly:
        monkeypatch.setenv("FLY_APP_NAME", "wolfee-analytics")
    extra = {"Fly-Client-IP": FLY_IP} if fly else {}
    client = TestClient(app)

    for n in range(5):
        assert _register(client, n, f"guess-{n}", **extra).status_code == 403
    blocked = _register(client, 50, INVITE, **extra)

    assert blocked.status_code == 429


def _logged_ips(email, event):
    async def run():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(SecurityLog.ip_address).where(
                SecurityLog.email == email, SecurityLog.event_type == event))).scalars().all()
    return asyncio.run(run())


def test_on_fly_the_security_log_records_fly_client_ip(on_fly):
    email = f"log_{secrets.token_hex(5)}@example.com"

    TestClient(app).post("/api/auth/register", json={"email": email, "password": "TraderSecure2026!#",
                                                     "invite_code": "wrong"},
                         headers={**_spoofed(7), "Fly-Client-IP": FLY_IP})

    assert _logged_ips(email, "REGISTER_INVITE_REJECTED") == [FLY_IP]


def test_the_login_lockout_holds_and_logs_the_real_address(on_fly):
    email, password = f"lock_{secrets.token_hex(5)}@example.com", "CorrectPassword123!"

    async def create():
        async with AsyncSessionLocal() as session:
            session.add(User(email=email, password_hash=hash_password(password), email_verified=True,
                             failed_login_count=0))
            await session.commit()

    asyncio.run(create())
    client = TestClient(app)
    for n in range(5):
        assert _login(client, n, email=email, **{"Fly-Client-IP": FLY_IP}).status_code == 401
    auth_rate_limiter.requests.clear()

    locked = _login(client, 40, email=email, password=password, **{"Fly-Client-IP": "203.0.113.9"})

    assert locked.status_code == 401 and "temporarily locked" in locked.json()["detail"]
    assert set(_logged_ips(email, "LOGIN_FAILED")) == {FLY_IP}
