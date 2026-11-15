"""REQ-31 (f): backend/api_router.py (a Finnhub / Alpha Vantage / Polygon router) was never
imported, so its failover never ran while the README described it as active. It is
deleted; the app must start without it."""
import importlib.util
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def test_the_unused_router_is_gone_and_the_app_imports_without_it():
    assert not os.path.exists(os.path.join(BACKEND_DIR, "api_router.py"))
    assert importlib.util.find_spec("api_router") is None

    import main  # noqa: F401  (raises if anything still imported it)
