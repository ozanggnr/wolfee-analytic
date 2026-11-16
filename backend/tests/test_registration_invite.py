"""Decision D1: no CAPTCHA; registration requires the REGISTRATION_INVITE_CODE secret.

- Missing code, wrong code and closed registration (secret unset) give the same 403.
- No account is created and the e-mail is never looked up without a valid code.
- The comparison is constant-time (hmac.compare_digest).
- 5 wrong codes per hour from one IP block registration from it (429), even with the right code.
- Login no longer asks for a CAPTCHA after failed attempts (the lockout stays).
"""
import asyncio
import hmac
import os
import secrets
import sys

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth_utils  # noqa: E402
from auth_utils import hash_password, invite_code_matches  # noqa: E402
from database import AsyncSessionLocal, init_db  # noqa: E402
from main import app  # noqa: E402
from models import SecurityLog, User  # noqa: E402
from security_middleware import auth_rate_limiter, invite_failure_limiter  # noqa: E402

INVITE = "launch-" + secrets.token_hex(8)
PASSWORD = "TraderSecure2026!#"
GENERIC = "Registration requires a valid invite code."


@pytest.fixture(scope="module", autouse=True)
def tables():
    asyncio.run(init_db())


@pytest.fixture(autouse=True)
def clean_limits(monkeypatch):
    monkeypatch.setenv("AUTO_VERIFY_DEV", "false")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    for limiter in (auth_rate_limiter, invite_failure_limiter):
        limiter.requests.clear()
    yield
    for limiter in (auth_rate_limiter, invite_failure_limiter):
        limiter.requests.clear()


def _email():
    return f"invite_{secrets.token_hex(5)}@example.com"


def _register(client, email, **extra):
    return client.post("/api/auth/register", json={"email": email, "password": PASSWORD, **extra})


def _user(email):
    async def run():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    return asyncio.run(run())


@pytest.mark.parametrize("secret", [None, "", "   "])
def test_registration_is_closed_without_the_secret(monkeypatch, secret):
    if secret is None:
        monkeypatch.delenv("REGISTRATION_INVITE_CODE", raising=False)
    else:
        monkeypatch.setenv("REGISTRATION_INVITE_CODE", secret)
    email = _email()

    for code in (None, "", "anything", "   "):
        response = _register(TestClient(app), email, **({} if code is None else {"invite_code": code}))
        assert (response.status_code, response.json()["detail"]) == (403, GENERIC)
    assert _user(email) is None


@pytest.mark.parametrize("payload", [{}, {"invite_code": ""}, {"invite_code": "wrong-code"},
                                     {"invite_code": INVITE + "x"}, {"invite_code": INVITE.upper()},
                                     {"captcha_token": "dev-captcha-pass"}])
def test_a_missing_or_wrong_code_gets_the_generic_error_and_no_account(monkeypatch, payload):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    email = _email()

    response = _register(TestClient(app), email, **payload)

    assert (response.status_code, response.json()) == (403, {"detail": GENERIC})
    assert _user(email) is None


def test_the_right_code_registers(monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    email = _email()

    response = _register(TestClient(app), email, invite_code=INVITE)

    assert response.status_code == 200, response.text
    assert _user(email) is not None


def test_an_existing_email_with_a_wrong_code_reveals_nothing(monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    email = _email()
    assert _register(TestClient(app), email, invite_code=INVITE).status_code == 200

    response = _register(TestClient(app), email, invite_code="wrong")

    assert (response.status_code, response.json()["detail"]) == (403, GENERIC)


def test_a_wrong_code_is_checked_before_the_password_policy(monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)

    response = TestClient(app).post("/api/auth/register",
                                    json={"email": _email(), "password": "short", "invite_code": "wrong"})

    assert response.json()["detail"] == GENERIC


def test_the_comparison_is_constant_time(monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    calls, original = [], hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(auth_utils.hmac, "compare_digest", spy)

    assert invite_code_matches(INVITE) and not invite_code_matches("wrong")
    assert len(calls) == 2


def test_five_wrong_codes_block_the_ip_even_for_the_right_code(monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    client = TestClient(app)

    for attempt in range(5):
        assert _register(client, _email(), invite_code=f"guess-{attempt}").status_code == 403
    blocked = _register(client, _email(), invite_code=INVITE)

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_rejected_attempts_are_audited(monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", INVITE)
    email = _email()
    _register(TestClient(app), email, invite_code="wrong")

    async def events():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(SecurityLog.event_type).where(SecurityLog.email == email))).scalars().all()

    assert asyncio.run(events()) == ["REGISTER_INVITE_REJECTED"]


def test_the_captcha_path_is_gone():
    assert not hasattr(auth_utils, "verify_captcha")
    assert not hasattr(auth_utils, "CAPTCHA_SECRET_KEY")


def test_login_after_failed_attempts_asks_for_no_captcha():
    email, password = _email(), "CorrectPassword123!"

    async def create():
        async with AsyncSessionLocal() as session:
            session.add(User(email=email, password_hash=hash_password(password), email_verified=True,
                             failed_login_count=3))
            await session.commit()

    asyncio.run(create())
    client = TestClient(app)

    response = client.post("/api/auth/login", json={"email": email, "password": password})

    assert response.status_code == 200, response.text
    assert "X-Captcha-Required" not in response.headers
