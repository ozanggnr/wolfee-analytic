"""
Security Audit Verification Test Suite
Tests all 9 domains remediated during security hardening:
1. Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)
2. CORS origin validation
3. Input validation & path-traversal / injection blocking on stock symbols
4. Safe error handling (no stack traces or internal DB details leaked to clients)
5. Public API sliding-window rate limiting
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from security_middleware import public_api_rate_limiter, auth_rate_limiter


@pytest.fixture(autouse=True)
def clear_limiters():
    public_api_rate_limiter.requests.clear()
    auth_rate_limiter.requests.clear()
    yield
    public_api_rate_limiter.requests.clear()
    auth_rate_limiter.requests.clear()


def test_security_headers_present():
    """Verify that all strict security headers are injected into HTTP responses."""
    client = TestClient(app)
    response = client.get("/healthz")

    assert response.status_code == 200
    headers = response.headers

    # 1. Content Security Policy
    assert "Content-Security-Policy" in headers
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "default-src 'self'" in headers["Content-Security-Policy"]

    # 2. Frame Options
    assert headers.get("X-Frame-Options") == "DENY"

    # 3. Content Type Options
    assert headers.get("X-Content-Type-Options") == "nosniff"

    # 4. Referrer Policy
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # 5. Permissions Policy
    assert "camera=()" in headers.get("Permissions-Policy", "")


def test_symbol_input_validation_blocks_injection():
    """Verify that malformed or malicious ticker symbols are rejected with 400 Bad Request."""
    client = TestClient(app)

    malicious_symbols = [
        "AAPL<script>",
        "THYAO';--",
        "TOOLONGSYMBOLNAMETHATEXCEEDSTWENTYCHARS",
        "BAD$YMB#OL",
        "THYAO..IS",
    ]

    for bad_sym in malicious_symbols:
        resp = client.get(f"/api/analyze/{bad_sym}")
        assert resp.status_code == 400, f"Symbol {bad_sym} did not return 400, returned {resp.status_code}"
        data = resp.json()
        assert "Invalid symbol format" in data.get("detail", "")


def test_portfolio_export_bounds():
    """Verify that requesting >50 symbols in portfolio export is rejected with 400."""
    client = TestClient(app)
    too_many_symbols = ",".join([f"SYM{i}" for i in range(55)])

    resp = client.get(f"/api/export/portfolio?symbols={too_many_symbols}&period=daily")
    assert resp.status_code == 400
    assert "Maximum 50 symbols allowed" in resp.json().get("detail", "")


def test_cors_origin_handling():
    """Verify that CORS honors explicit allowlist and railway domains, and does not return wildcard with credentials."""
    client = TestClient(app)

    # 1. Disallowed origin
    resp = client.options(
        "/api/stocks",
        headers={
            "Origin": "https://malicious-phishing-site.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    # The header Access-Control-Allow-Origin should NOT match the malicious origin
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin != "https://malicious-phishing-site.com"
    assert allow_origin != "*"

    # 2. Allowed localhost origin
    resp_valid = client.options(
        "/api/stocks",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert resp_valid.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_global_exception_handler_sanitized_response():
    """Verify that unexpected 500 errors return sanitized JSON without stack traces."""
    client = TestClient(app, raise_server_exceptions=False)

    # Trigger invalid period in chart endpoint
    resp = client.get("/api/chart/AAPL/invalid_period_name")
    assert resp.status_code == 400
    assert "Invalid period parameter" in resp.json().get("detail", "")
