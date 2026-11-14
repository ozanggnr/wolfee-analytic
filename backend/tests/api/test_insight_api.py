"""REQ-20: GET /api/insight never builds an insight from partial stock data, and never stores one."""
import asyncio

import pytest
from sqlalchemy import delete, func, select

import main
from database import AsyncSessionLocal
from models import AIInsight, StockData
from services import insight_readiness


async def _clear_insights():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AIInsight))
        await session.commit()


async def _counts():
    async with AsyncSessionLocal() as session:
        insights = await session.scalar(select(func.count(AIInsight.id)))
        stocks = await session.scalar(select(func.count(StockData.id)))
    return insights, stocks


@pytest.fixture
def no_stored_insight():
    asyncio.run(_clear_insights())  # the API test database is disposable
    yield
    asyncio.run(_clear_insights())


def test_without_enough_data_the_placeholder_is_returned_and_not_stored(user, no_stored_insight, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("an insight was generated from partial data")

    monkeypatch.setattr(main, "get_market_insight", must_not_run)
    monkeypatch.setattr(insight_readiness, "is_ready", lambda coverage: False)

    response = user.get("/api/insight")

    assert response.status_code == 200
    assert response.json() == {"insight": insight_readiness.INSIGHT_LOADING_TEXT}
    assert asyncio.run(_counts())[0] == 0


def test_with_enough_data_the_insight_uses_every_cached_row_and_is_not_stored(user, no_stored_insight, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "get_market_insight", lambda rows: seen.append(len(rows)) or "fresh")
    monkeypatch.setattr(insight_readiness, "is_ready", lambda coverage: True)

    response = user.get("/api/insight")

    insights, stocks = asyncio.run(_counts())
    assert response.json() == {"insight": "fresh"}
    assert seen == [stocks]  # not the first 50 rows
    assert insights == 0
