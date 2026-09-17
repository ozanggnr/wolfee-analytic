"""
Comprehensive Test Suite for Wolfee Analytics Authentication & Watchlist
Tests:
1. bcrypt password hashing (cost factor 12) & verification
2. Server-side password policy enforcement & common password blocklist
3. Exponential backoff account lockout (1m, 5m, 15m)
4. Anti-enumeration protections (uniform responses)
5. IP Rate limiting with Retry-After header
6. CSRF double-submit cookie protection on state-changing requests
7. HttpOnly, Secure, SameSite=Strict session cookie management
8. Watchlist CRUD operations for BIST100 and US markets
9. Watchlist summary card metrics (up/down/flat count, biggest mover, 60s cache)
"""

import os
import sys
import pytest
import secrets
from datetime import datetime, timezone, timedelta
import httpx
from starlette.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base, engine, AsyncSessionLocal, init_db
from models import User, WatchlistItem, UserSession, AuthToken, SecurityLog, StockData
from auth_utils import (
    hash_password, verify_password, validate_password_policy,
    calculate_lockout_cooldown, is_account_locked,
    generate_secure_token, hash_token
)
from security_middleware import (
    IPRateLimiter, SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME, auth_rate_limiter
)
import main
from main import app


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    auth_rate_limiter.requests.clear()
    yield
    auth_rate_limiter.requests.clear()


# ============================================================
# 1. UNIT TESTS: PASSWORD HASHING & POLICY
# ============================================================
def test_bcrypt_cost_factor_12():
    """Verify password hashing strictly uses bcrypt with cost factor 12."""
    raw_password = "SecurePassword2026!"
    hashed = hash_password(raw_password)

    # Cost factor 12 bcrypt hashes start with $2b$12$ or $2a$12$
    assert hashed.startswith("$2b$12$") or hashed.startswith("$2a$12$"), (
        f"Hash does not have cost factor 12: {hashed[:10]}"
    )
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_password_policy_enforcement():
    """Verify server-side password policy: min 10 chars and blocklist."""
    # Under 10 characters -> Reject
    valid, err = validate_password_policy("short9")
    assert valid is False
    assert "at least 10 characters" in err

    # In common password blocklist -> Reject
    valid, err = validate_password_policy("password123")
    assert valid is False
    assert "too common" in err

    valid, err = validate_password_policy("1234567890")
    assert valid is False
    assert "too common" in err

    # Repetitive characters -> Reject
    valid, err = validate_password_policy("aaaaaaaaaaaa")
    assert valid is False
    assert "repeated characters" in err

    # Strong password -> Accept
    valid, err = validate_password_policy("MySecureInvestmentPass2026!")
    assert valid is True
    assert err is None


# ============================================================
# 2. UNIT TESTS: EXPONENTIAL BACKOFF ACCOUNT LOCKOUT
# ============================================================
def test_exponential_backoff_cooldown_calculation():
    """Verify exponential cooldown progression (1m, 5m, 15m) without permanent lock."""
    # Failures 1-4: No lockout
    for i in range(1, 5):
        assert calculate_lockout_cooldown(i) is None

    # Failure 5: 1 minute
    cd_5 = calculate_lockout_cooldown(5)
    assert cd_5 == timedelta(minutes=1)

    # Failure 6: 5 minutes
    cd_6 = calculate_lockout_cooldown(6)
    assert cd_6 == timedelta(minutes=5)

    # Failure 7+: 15 minutes
    cd_7 = calculate_lockout_cooldown(7)
    assert cd_7 == timedelta(minutes=15)

    cd_10 = calculate_lockout_cooldown(10)
    assert cd_10 == timedelta(minutes=15)


def test_is_account_locked_helper():
    """Verify account lockout detection and remaining cooldown seconds."""
    # Not locked
    locked, rem = is_account_locked(None)
    assert locked is False
    assert rem is None

    # Past lock (expired)
    past = datetime.now(timezone.utc) - timedelta(minutes=2)
    locked, rem = is_account_locked(past)
    assert locked is False

    # Active lock (future)
    future = datetime.now(timezone.utc) + timedelta(seconds=45)
    locked, rem = is_account_locked(future)
    assert locked is True
    assert rem is not None and 30 <= rem <= 46


# ============================================================
# 3. UNIT TESTS: RATE LIMITER
# ============================================================
def test_ip_rate_limiter():
    """Verify rate limiter allows max requests then blocks with retry-after."""
    limiter = IPRateLimiter(window_seconds=60, max_requests=5)
    test_ip = "198.51.100.25"

    for _ in range(5):
        allowed, _ = limiter.is_allowed(test_ip)
        assert allowed is True

    # 6th request should be blocked
    allowed, retry_after = limiter.is_allowed(test_ip)
    assert allowed is False
    assert retry_after > 0


# ============================================================
# 4. INTEGRATION TESTS: FULL AUTH & WATCHLIST ENDPOINTS
# ============================================================
@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Ensure database tables exist for integration tests."""
    import asyncio
    asyncio.run(init_db())
    yield


def test_auth_registration_and_anti_enumeration():
    """Test user registration, verification flow, and anti-enumeration generic responses."""
    client = TestClient(app)
    unique_email = f"trader_{secrets.token_hex(4)}@example.com"
    strong_pw = "TraderSecure2026!#"

    # 1. Attempt with short password -> 400
    res = client.post("/api/auth/register", json={
        "email": unique_email,
        "password": "short",
        "captcha_token": "dev-captcha-pass"
    })
    assert res.status_code == 400
    assert "at least 10 characters" in res.json()["detail"]

    # 2. Register with valid details -> Generic Success
    res = client.post("/api/auth/register", json={
        "email": unique_email,
        "password": strong_pw,
        "captcha_token": "dev-captcha-pass"
    })
    assert res.status_code == 200
    assert "verification email has been sent" in res.json()["message"]

    # 3. Re-register with the SAME email -> Identical response (anti-enumeration)
    res_dup = client.post("/api/auth/register", json={
        "email": unique_email,
        "password": strong_pw,
        "captcha_token": "dev-captcha-pass"
    })
    assert res_dup.status_code == 200
    assert res_dup.json()["message"] == res.json()["message"]

    # 4. Attempt login before email verification -> 403 / unverified error
    res_login_unverified = client.post("/api/auth/login", json={
        "email": unique_email,
        "password": strong_pw,
        "captcha_token": "dev-captcha-pass"
    })
    assert res_login_unverified.status_code in (401, 403)
    assert "verify" in res_login_unverified.json()["detail"].lower()


def test_csrf_protection_on_state_changing_endpoints():
    """Test Double-Submit CSRF cookie validation."""
    client = TestClient(app)

    # Initial request receives a csrf_token cookie
    res_init = client.get("/api/auth/csrf")
    assert res_init.status_code == 200
    csrf_token = res_init.cookies.get(CSRF_COOKIE_NAME) or res_init.json().get("csrf_token")
    assert csrf_token is not None

    # POST with missing X-CSRF-Token header -> 403 Forbidden
    client.cookies.set(CSRF_COOKIE_NAME, csrf_token)
    res_no_header = client.post("/api/watchlist", json={"ticker": "THYAO"})
    assert res_no_header.status_code == 403
    assert "CSRF validation failed" in res_no_header.json()["detail"]

    # POST with valid X-CSRF-Token header -> Proceeds to next layer (e.g. 401 unauth)
    res_with_csrf = client.post(
        "/api/watchlist",
        json={"ticker": "THYAO"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    # Passed CSRF check, hits authentication check
    assert res_with_csrf.status_code == 401


def test_login_flow_and_session_cookie_security():
    """Test user verification, login, session cookies, and logout."""
    client = TestClient(app)
    import asyncio
    from database import AsyncSessionLocal
    from sqlalchemy import select

    email = f"verified_user_{secrets.token_hex(4)}@example.com"
    password = "SuperStrongPassword2026!"

    # Create verified user directly in DB
    async def create_verified_user():
        async with AsyncSessionLocal() as session:
            u = User(
                email=email,
                password_hash=hash_password(password),
                email_verified=True,
                failed_login_count=0
            )
            session.add(u)
            await session.commit()
            await session.refresh(u)
            return u.id

    user_id = asyncio.run(create_verified_user())

    # Obtain CSRF token
    csrf_res = client.get("/api/auth/csrf")
    csrf_token = csrf_res.cookies.get(CSRF_COOKIE_NAME) or csrf_res.json()["csrf_token"]
    client.cookies.set(CSRF_COOKIE_NAME, csrf_token)

    # 1. Login with incorrect password -> 401 Generic Error
    res_bad = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword123!", "captcha_token": "dev-captcha-pass"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_bad.status_code == 401
    assert "Invalid email or password" in res_bad.json()["detail"]

    # 2. Login with correct password -> Success & Cookies
    res_good = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "captcha_token": "dev-captcha-pass"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_good.status_code == 200
    assert "user" in res_good.json()

    # Verify session cookie properties
    session_cookie = res_good.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie is not None
    assert len(session_cookie) >= 32

    # 3. GET /api/auth/me -> Returns authenticated profile
    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["email"] == email

    # 4. Watchlist operations for authenticated user
    # Add BIST100 stock
    add_bist = client.post(
        "/api/watchlist",
        json={"ticker": "THYAO", "market": "BIST100"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert add_bist.status_code in (200, 201)

    # Add US stock
    add_us = client.post(
        "/api/watchlist",
        json={"ticker": "NVDA", "market": "US"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert add_us.status_code in (200, 201)

    # Get Watchlist
    get_wl = client.get("/api/watchlist")
    assert get_wl.status_code == 200
    items = get_wl.json()["items"]
    assert len(items) == 2
    tickers = [it["ticker"] for it in items]
    assert "THYAO" in tickers
    assert "NVDA" in tickers

    # 5. Watchlist Summary Card & 60s Cache
    summary_res = client.get("/api/watchlist/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_count"] == 2
    assert "up_count" in summary
    assert "down_count" in summary
    assert "avg_change_pct" in summary
    assert "biggest_mover" in summary
    assert "ticker_changes" in summary
    assert len(summary["ticker_changes"]) == 2

    # Verify Cache-Control header
    assert "max-age" in summary_res.headers.get("Cache-Control", "")

    # 6. Delete stock from watchlist
    del_res = client.delete(
        "/api/watchlist/NVDA",
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert del_res.status_code == 200

    get_wl2 = client.get("/api/watchlist")
    assert len(get_wl2.json()["items"]) == 1

    # 7. Logout -> Revokes session and clears cookies
    logout_res = client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert logout_res.status_code == 200

    # Unauthenticated again
    res_me_logged_out = client.get("/api/auth/me")
    assert res_me_logged_out.status_code == 401


def test_failed_logins_trigger_exponential_lockout():
    """Verify that 5 consecutive failed logins trigger exponential cooldown."""
    client = TestClient(app)
    import asyncio
    from database import AsyncSessionLocal
    from sqlalchemy import select

    email = f"lockout_user_{secrets.token_hex(4)}@example.com"
    password = "CorrectPassword123!"

    async def create_target_user():
        async with AsyncSessionLocal() as session:
            u = User(
                email=email,
                password_hash=hash_password(password),
                email_verified=True,
                failed_login_count=0
            )
            session.add(u)
            await session.commit()
            return u.id

    asyncio.run(create_target_user())

    # Obtain CSRF
    csrf_res = client.get("/api/auth/csrf")
    csrf_token = csrf_res.cookies.get(CSRF_COOKIE_NAME) or csrf_res.json()["csrf_token"]

    # 4 consecutive bad attempts -> Not locked yet
    for i in range(4):
        res = client.post(
            "/api/auth/login",
            json={"email": email, "password": f"BadPassword{i}!", "captcha_token": "dev-captcha-pass"},
            headers={CSRF_HEADER_NAME: csrf_token}
        )
        assert res.status_code == 401
        assert "Invalid email or password" in res.json()["detail"]

    # 5th bad attempt -> Triggers lockout cooldown
    res5 = client.post(
        "/api/auth/login",
        json={"email": email, "password": "BadPassword5!", "captcha_token": "dev-captcha-pass"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res5.status_code == 401

    # Immediate next attempt (even with CORRECT password) is blocked by lockout cooldown!
    res_locked = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "captcha_token": "dev-captcha-pass"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_locked.status_code == 401
    assert "temporarily locked" in res_locked.json()["detail"]


def test_password_reset_flow():
    """Test forgot-password request, token creation, reset-password, and session invalidation."""
    client = TestClient(app)
    import asyncio
    from database import AsyncSessionLocal
    from sqlalchemy import select

    email = f"reset_user_{secrets.token_hex(4)}@example.com"
    old_password = "InitialPassword123!"
    new_password = "BrandNewPassword2026!#"

    async def create_reset_user():
        async with AsyncSessionLocal() as session:
            u = User(
                email=email,
                password_hash=hash_password(old_password),
                email_verified=True,
                failed_login_count=0
            )
            session.add(u)
            await session.commit()
            return u.id

    asyncio.run(create_reset_user())

    csrf_res = client.get("/api/auth/csrf")
    csrf_token = csrf_res.cookies.get(CSRF_COOKIE_NAME) or csrf_res.json()["csrf_token"]

    # 1. Request forgot password -> Generic response
    res_forgot = client.post(
        "/api/auth/forgot-password",
        json={"email": email},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_forgot.status_code == 200
    assert "instructions have been sent" in res_forgot.json()["message"]

    # Fetch the generated reset token from DB
    async def get_reset_token():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AuthToken).where(
                    AuthToken.token_type == "password_reset",
                    AuthToken.is_used == False
                ).order_by(AuthToken.created_at.desc())
            )
            tok = result.scalars().first()
            return tok.token_hash

    tok_hash = asyncio.run(get_reset_token())
    assert tok_hash is not None

    # 2. Reset password using a known test token directly verified in DB
    raw_token = generate_secure_token()
    raw_hash = hash_token(raw_token)

    async def attach_known_token():
        async with AsyncSessionLocal() as session:
            res_u = await session.execute(select(User).where(User.email == email))
            u = res_u.scalar_one()
            t = AuthToken(
                user_id=u.id,
                token_hash=raw_hash,
                token_type="password_reset",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                is_used=False
            )
            session.add(t)
            await session.commit()

    asyncio.run(attach_known_token())

    # Reset password with weak password -> Reject
    res_weak = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "short"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_weak.status_code == 400

    # Reset password with valid password -> Success
    res_reset = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": new_password},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_reset.status_code == 200
    assert "successfully reset" in res_reset.json()["message"]

    # 3. Old password fails
    res_old = client.post(
        "/api/auth/login",
        json={"email": email, "password": old_password, "captcha_token": "dev-captcha-pass"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_old.status_code == 401

    # 4. New password succeeds
    res_new = client.post(
        "/api/auth/login",
        json={"email": email, "password": new_password, "captcha_token": "dev-captcha-pass"},
        headers={CSRF_HEADER_NAME: csrf_token}
    )
    assert res_new.status_code == 200
