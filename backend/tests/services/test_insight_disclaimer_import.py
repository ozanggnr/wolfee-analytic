"""REQ-35 note / REQ-38: ai_insight_service imports MARKET_DISCLAIMER directly (no fallback to
the DISCLAIMER alias), so the alias can be removed from ai.guardrails and a missing
MARKET_DISCLAIMER fails loudly instead of silently serving the old wording."""
import importlib
import os
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import ai.guardrails as guardrails  # noqa: E402
from services import ai_insight_service  # noqa: E402

ROW = SimpleNamespace(insight_text="x", generated_by="template", is_fallback=True,
                      generated_at=datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc), inputs_as_of=None)


def test_stored_insights_carry_the_market_disclaimer():
    assert ai_insight_service.stored_response(ROW)["disclaimer"] == guardrails.MARKET_DISCLAIMER


def test_the_service_works_once_the_disclaimer_alias_is_removed(monkeypatch):
    without_alias = types.ModuleType("ai.guardrails")
    without_alias.__dict__.update({k: v for k, v in vars(guardrails).items() if k != "DISCLAIMER"})
    without_alias.MARKET_DISCLAIMER = "market data only"
    monkeypatch.setitem(sys.modules, "ai.guardrails", without_alias)
    try:
        reloaded = importlib.reload(ai_insight_service)
        assert reloaded.stored_response(ROW)["disclaimer"] == "market data only"
    finally:
        monkeypatch.undo()
        importlib.reload(ai_insight_service)

    assert not hasattr(ai_insight_service, "DISCLAIMER")


def test_a_missing_market_disclaimer_is_an_import_error(monkeypatch):
    """The old fallback hid this behind the DISCLAIMER alias."""
    import pytest

    only_alias = types.ModuleType("ai.guardrails")
    only_alias.__dict__.update({k: v for k, v in vars(guardrails).items() if k != "MARKET_DISCLAIMER"})
    monkeypatch.setitem(sys.modules, "ai.guardrails", only_alias)
    try:
        with pytest.raises(ImportError):
            importlib.reload(ai_insight_service)
    finally:
        monkeypatch.undo()
        importlib.reload(ai_insight_service)
