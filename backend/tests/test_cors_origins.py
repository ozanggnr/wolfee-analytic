"""REQ-33 (b): no leftover hosting origins in CORS (credentialed requests).

Before: a regex allowing any https://*.up.railway.app, RAILWAY_PUBLIC_DOMAIN,
wolfee-backend.onrender.com and a workers.dev origin. Now: localhost plus CORS_ORIGINS.
"""
import os
import sys

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from main import LOCAL_ORIGINS, app, cors_origins  # noqa: E402

STALE = [
    "https://anything.up.railway.app",
    "https://wolfee-backend-production.up.railway.app",
    "https://wolfee-backend.onrender.com",
    "https://solitary-scene-04bc.ozanggnr.workers.dev",
]


def _preflight(origin):
    return TestClient(app).options("/api/stocks", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})


@pytest.mark.parametrize("origin", STALE)
def test_old_hosting_origins_are_refused(origin):
    assert _preflight(origin).headers.get("access-control-allow-origin") is None


def test_localhost_is_still_allowed():
    response = _preflight("http://localhost:8000")
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_the_allowlist_is_localhost_plus_cors_origins_only(monkeypatch):
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "wolfee.up.railway.app")  # no longer read

    origins = cors_origins(" https://wolfee-analytics.fly.dev , ,https://wolfee-analytics.fly.dev")

    assert origins == [*LOCAL_ORIGINS, "https://wolfee-analytics.fly.dev"]
    assert cors_origins(None) == list(LOCAL_ORIGINS)


def test_the_running_app_has_no_stale_origin_or_regex():
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs.get("allow_origin_regex") is None
    assert not any(stale in main.origins for stale in STALE)
