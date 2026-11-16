"""REQ-33 (a): the naive timestamp columns hold UTC whatever the database server's time zone.

stock_data / turkish_gold / exchange_rates `updated_at` and ai_insights `created_at` are
`timestamp without time zone` with server_default now(): on a non-UTC Postgres they stored
local time, which the code reads as UTC. On Postgres each test runs its session at +09:00
(Asia/Tokyo), so a server-local value would be 9 hours off. On SQLite now() is UTC already.
"""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text, update

from database import AsyncSessionLocal, is_sqlite
from models import AIInsight, ExchangeRate, StockData, TurkishGold

TOLERANCE = timedelta(minutes=2)


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _session_far_from_utc(session):
    if not is_sqlite:
        await session.execute(text("SET TIME ZONE 'Asia/Tokyo'"))


async def _reset(session):
    if not is_sqlite:
        await session.execute(text("RESET TIME ZONE"))


def _assert_utc_now(value):
    assert value is not None
    naive = value if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
    assert abs(naive - _utc_now()) < TOLERANCE, f"{value} is not the current UTC time ({_utc_now()})"


def test_inserted_rows_get_utc_timestamps():
    symbol, gold_type, pair = f"T{secrets.token_hex(4)}", f"g_{secrets.token_hex(4)}", secrets.token_hex(3)

    async def run():
        async with AsyncSessionLocal() as session:
            await _session_far_from_utc(session)
            stock = StockData(symbol=symbol, price=1.0, market_type="BIST", currency="TRY")
            gold = TurkishGold(gold_type=gold_type, display_name="g", buying_price=1.0, selling_price=1.0)
            rate = ExchangeRate(pair=pair, display_name="r", buying=1.0, selling=1.0)
            insight = AIInsight(insight_type="test_utc", insight_text="x")
            session.add_all([stock, gold, rate, insight])
            await session.commit()
            values = [stock.updated_at, gold.updated_at, rate.updated_at, insight.created_at]
            await session.execute(delete(StockData).where(StockData.symbol == symbol))
            await session.execute(delete(TurkishGold).where(TurkishGold.gold_type == gold_type))
            await session.execute(delete(ExchangeRate).where(ExchangeRate.pair == pair))
            await session.execute(delete(AIInsight).where(AIInsight.id == insight.id))
            await _reset(session)
            await session.commit()
            return values

    for value in asyncio.run(run()):
        _assert_utc_now(value)


def test_updates_refresh_updated_at_in_utc():
    symbol = f"T{secrets.token_hex(4)}"
    stale = _utc_now() - timedelta(days=3)

    async def run():
        async with AsyncSessionLocal() as session:
            await _session_far_from_utc(session)
            session.add(StockData(symbol=symbol, price=1.0, market_type="BIST", currency="TRY", updated_at=stale))
            await session.commit()

            row = (await session.execute(select(StockData).where(StockData.symbol == symbol))).scalar_one()
            row.price = 2.0  # ORM update
            await session.commit()
            after_orm = row.updated_at

            await session.execute(update(StockData).where(StockData.symbol == symbol).values(updated_at=stale))
            await session.execute(update(StockData).where(StockData.symbol == symbol).values(price=3.0))  # Core
            await session.commit()
            after_core = (await session.execute(
                select(StockData.updated_at).where(StockData.symbol == symbol))).scalar_one()

            await session.execute(delete(StockData).where(StockData.symbol == symbol))
            await _reset(session)
            await session.commit()
            return after_orm, after_core

    for value in asyncio.run(run()):
        _assert_utc_now(value)


def test_the_api_marks_these_timestamps_as_utc(user):
    gold_type = f"g_{secrets.token_hex(4)}"

    async def add(remove=False):
        async with AsyncSessionLocal() as session:
            if remove:
                await session.execute(delete(TurkishGold).where(TurkishGold.gold_type == gold_type))
            else:
                session.add(TurkishGold(gold_type=gold_type, display_name="g", buying_price=1.0, selling_price=1.0))
            await session.commit()

    asyncio.run(add())
    try:
        gold = next(g for g in user.get("/api/turkish-gold").json()["gold"] if g["gold_type"] == gold_type)
    finally:
        asyncio.run(add(remove=True))

    stamp = datetime.fromisoformat(gold["updated_at"])
    assert stamp.utcoffset() == timedelta(0)  # was naive: a browser read it as local time
    _assert_utc_now(stamp)
