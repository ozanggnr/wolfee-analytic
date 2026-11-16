"""REQ-36 (c), decision D2: without an email provider, reset and resend-verification refuse.

- 503 with one fixed message for every address (no enumeration), before any lookup.
- No AuthToken is created (also not on registration).
- No verification / reset link or token is ever written to the log, also when a provider
  is configured but fails (the old fallback logged the full link: a live token).
"""
import asyncio
import logging
import os
import secrets
import sys

import pytest
from sqlalchemy import func, select
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth_utils  # noqa: E402
from auth_utils import hash_password, send_password_reset_email, send_verification_email  # noqa: E402
from database import AsyncSessionLocal, init_db  # noqa: E402
from main import app  # noqa: E402
from models import AuthToken, SecurityLog, User  # noqa: E402
from security_middleware import auth_rate_limiter, invite_failure_limiter  # noqa: E402

PROVIDER_ENV = ("RESEND_API_KEY", "SENDGRID_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
INVITE = "invite-" + secrets.token_hex(6)


@pytest.fixture(scope="module", autouse=True)
def tables():
    asyncio.run(init_db())


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    monkeypatch.setenv("AUTO_VERIFY_DEV", "false")
    for limiter in (auth_rate_limiter, invite_failure_limiter):
        limiter.requests.clear()
    yield
    for limiter in (auth_rate_limiter, invite_failure_limiter):
        limiter.requests.clear()


def _user(verified):
    email = f"mail_{secrets.token_hex(5)}@example.com"

    async def run():
        async with AsyncSessionLocal() as session:
            user = User(email=email, password_hash=hash_password("CorrectPassword123!"), email_verified=verified,
                        failed_login_count=0)
            session.add(user)
            await session.commit()
            return user.id

    return email, asyncio.run(run())


def _count(model, *where):
    async def run():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()
    return asyncio.run(run())


@pytest.mark.parametrize("path, verified, message", [
    ("/api/auth/forgot-password", True, "Password reset is not available yet."),
    ("/api/auth/resend-verification", False, "Email verification is not available yet."),
])
def test_without_a_provider_the_action_is_refused_alike_for_every_address(path, verified, message):
    email, user_id = _user(verified)
    client = TestClient(app)

    known = client.post(path, json={"email": email})
    unknown = client.post(path, json={"email": f"nobody_{secrets.token_hex(5)}@example.com"})

    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json()) == (503, {"detail": message})
    assert _count(AuthToken, AuthToken.user_id == user_id) == 0
    assert _count(SecurityLog, SecurityLog.email == email, SecurityLog.event_type == "PASSWORD_RESET_REQUEST") == 0


def test_registration_without_a_provider_creates_no_verification_token():
    email = f"reg_{secrets.token_hex(5)}@example.com"

    response = TestClient(app).post("/api/auth/register",
                                    json={"email": email, "password": "TraderSecure2026!#", "invite_code": INVITE})

    async def user_id():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(User.id).where(User.email == email))).scalar_one()

    assert response.status_code == 200
    assert _count(AuthToken, AuthToken.user_id == asyncio.run(user_id())) == 0


def _logged_text(caplog, capfd):
    records = "\n".join(f"{r.getMessage()} {r.args!r}" for r in caplog.records)
    out, err = capfd.readouterr()
    return records + out + err


@pytest.mark.parametrize("send", [send_password_reset_email, send_verification_email])
def test_no_token_or_link_is_logged_without_a_provider(caplog, capfd, send):
    token = "tok_" + secrets.token_urlsafe(24)

    with caplog.at_level(logging.DEBUG):
        sent = asyncio.run(send("someone@example.com", token, base_url="https://wolfee.example"))

    logged = _logged_text(caplog, capfd)
    assert sent is False
    assert caplog.records, "the unsent email should still be reported"
    assert token not in logged and "reset_token=" not in logged and "verify-email?token" not in logged


class _FailingProvider:
    """Resend answers 422 and echoes the request body, as some providers do."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        class Response:
            status_code = 422
            text = f"invalid request: {json}"
        return Response()


def test_no_token_is_logged_when_the_provider_fails(caplog, capfd, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_not_a_real_key")
    monkeypatch.setattr(auth_utils.httpx, "AsyncClient", _FailingProvider)
    token = "tok_" + secrets.token_urlsafe(24)

    with caplog.at_level(logging.DEBUG):
        sent = asyncio.run(send_password_reset_email("someone@example.com", token, base_url="https://wolfee.example"))

    assert sent is False
    assert token not in _logged_text(caplog, capfd)
