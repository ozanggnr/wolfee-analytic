"""REQ-28 (D5, DATABASE_CONTRACT §4.4) and REQ-20: AI routes on the guarded layer.

- /api/insight and /insight serve only a stored row with provenance; an old row
  without it (possibly pre-D5 adviser text) is ignored and a new insight is
  generated, stored with all four provenance values, and returned.
- No insight is generated or stored from partial data (REQ-20): the template is served.
- Errors are answered by the guarded layer's template, with provenance.
- /api/ai/analyze/{symbol} returns the guarded description with provenance.
- `violations` never appear in a response.
"""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from ai.guardrails import DISCLAIMER, Generation
from database import AsyncSessionLocal
from models import AIInsight, StockData
from services import ai_insight_service, insight_readiness

PROVENANCE = {"generated_by", "generated_at", "inputs_as_of", "is_fallback", "disclaimer"}
ADVISER_TEXT = "PURCHASABLE — strong buy signal, target +20%"


async def _clear_insights():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AIInsight))
        await session.commit()


def _stored():
    async def run():
        async with AsyncSessionLocal() as session:
            return (await session.execute(select(AIInsight).order_by(AIInsight.id))).scalars().all()

    return asyncio.run(run())


def _add(**fields):
    async def run():
        async with AsyncSessionLocal() as session:
            session.add(AIInsight(insight_type="daily", **fields))
            await session.commit()

    asyncio.run(run())


def _stock_rows():
    async def run():
        async with AsyncSessionLocal() as session:
            return len((await session.execute(select(StockData.id))).all())

    return asyncio.run(run())


@pytest.fixture(autouse=True)
def no_stored_insight():
    asyncio.run(_clear_insights())  # the API test database is disposable
    yield
    asyncio.run(_clear_insights())


@pytest.fixture
def model(monkeypatch):
    """A fake model: ``answer`` is the text it returns, ``calls`` counts the calls."""
    class Model:
        answer = "Markets are calm."
        calls = 0

        def __call__(self, prompt):
            self.calls += 1
            return Generation(text=self.answer, model="test-model")

    fake = Model()
    monkeypatch.setattr(ai_insight_service, "generate_text", fake)
    return fake


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(insight_readiness, "is_ready", lambda coverage: True)


@pytest.fixture
def cached_stock():
    symbol = f"ZA{secrets.token_hex(3).upper()}"
    updated_at = datetime(2026, 11, 14, 8, 30)

    async def run():
        async with AsyncSessionLocal() as session:
            session.add(StockData(symbol=symbol, name=symbol, price=101.5, change_pct=1.25, currency="TRY",
                                  market_type="BIST", updated_at=updated_at))
            await session.commit()

    asyncio.run(run())
    return symbol, updated_at


def _assert_provenance(body):
    assert PROVENANCE <= body.keys()
    assert "violations" not in body
    assert body["disclaimer"] == DISCLAIMER
    datetime.fromisoformat(body["generated_at"])


def test_without_enough_data_the_template_is_served_and_nothing_stored(user, model, monkeypatch):
    monkeypatch.setattr(insight_readiness, "is_ready", lambda coverage: False)

    body = user.get("/api/insight").json()

    _assert_provenance(body)
    assert (body["generated_by"], body["is_fallback"], body["inputs_as_of"]) == ("template", True, None)
    assert "still loading" in body["insight"] and "no instrument has a price" not in body["insight"]
    assert model.calls == 0 and _stored() == []


def test_a_new_insight_uses_every_cached_row_and_is_stored_with_provenance(user, model, ready, cached_stock,
                                                                            monkeypatch):
    seen = []
    real = ai_insight_service.market_insight_response
    monkeypatch.setattr(ai_insight_service, "market_insight_response",
                        lambda data, **kwargs: seen.append(len(data)) or real(data, **kwargs))

    body = user.get("/api/insight").json()

    _assert_provenance(body)
    assert (body["insight"], body["generated_by"], body["is_fallback"]) == ("Markets are calm.", "test-model", False)
    assert seen == [_stock_rows()]  # every row, not the first 50
    [row] = _stored()
    assert (row.insight_text, row.generated_by, row.is_fallback) == ("Markets are calm.", "test-model", False)
    assert row.generated_at is not None
    assert (row.inputs_as_of is None) == (body["inputs_as_of"] is None)


def test_an_old_row_without_provenance_is_never_served(user, model, ready, cached_stock):
    _add(insight_text=ADVISER_TEXT)

    body = user.get("/api/insight").json()

    assert body["insight"] == "Markets are calm."
    assert model.calls == 1
    assert [row.generated_by for row in _stored()] == [None, "test-model"]  # old row kept, not served


def test_a_stored_row_with_provenance_is_served_without_a_model_call(user, model):
    generated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    _add(insight_text="Stored description.", generated_by="gemini-x", generated_at=generated_at,
         inputs_as_of=generated_at - timedelta(minutes=10), is_fallback=False)

    for path in ("/api/insight", "/insight"):
        body = user.get(path).json()
        _assert_provenance(body)
        assert (body["insight"], body["generated_by"], body["is_fallback"]) == ("Stored description.", "gemini-x", False)
        assert datetime.fromisoformat(body["inputs_as_of"]) == generated_at - timedelta(minutes=10)
    assert model.calls == 0


def test_model_text_that_breaks_the_guardrails_is_replaced_by_the_template(user, model, ready, cached_stock):
    model.answer = "Buy THYAO now: target price 400, guaranteed gains."

    body = user.get("/api/insight").json()

    _assert_provenance(body)
    assert (body["generated_by"], body["is_fallback"]) == ("template", True)
    assert "guaranteed" not in body["insight"]
    assert [row.is_fallback for row in _stored()] == [True]


def test_an_error_is_answered_by_the_template(user, model, monkeypatch):
    async def broken(db):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(ai_insight_service, "latest_with_provenance", broken)

    response = user.get("/api/insight")

    assert response.status_code == 200
    body = response.json()
    _assert_provenance(body)
    assert (body["generated_by"], body["is_fallback"]) == ("template", True)
    assert model.calls == 0


def test_the_stock_analysis_carries_provenance(user, model, cached_stock):
    symbol, updated_at = cached_stock

    body = user.get(f"/api/ai/analyze/{symbol}").json()

    _assert_provenance(body)
    assert (body["symbol"], body["analysis"], body["generated_by"]) == (symbol, "Markets are calm.", "test-model")
    assert datetime.fromisoformat(body["inputs_as_of"]) == updated_at.replace(tzinfo=timezone.utc)


def test_a_stock_analysis_that_breaks_the_guardrails_is_the_template(user, model, cached_stock):
    model.answer = "Strong buy: enter at 100, target 150."

    body = user.get(f"/api/ai/analyze/{cached_stock[0]}").json()

    _assert_provenance(body)
    assert (body["generated_by"], body["is_fallback"]) == ("template", True)
    assert "target" not in body["analysis"].lower()


def test_a_stock_analysis_error_is_the_template(user, model, cached_stock, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(ai_insight_service, "stock_response", broken)

    response = user.get(f"/api/ai/analyze/{cached_stock[0]}")

    assert response.status_code == 200
    body = response.json()
    _assert_provenance(body)
    assert (body["symbol"], body["generated_by"], body["is_fallback"]) == (cached_stock[0], "template", True)
