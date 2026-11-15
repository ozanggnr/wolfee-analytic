"""Queries on `price_history`, the shared end-of-day price cache (DATABASE_CONTRACT §4.3).

Not user-owned: the rows describe instruments, so there is no user filter here.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Mapping, NamedTuple, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from models import PriceHistory


class DailyCloseRow(NamedTuple):
    """One real close. Same fields as Agent 3's quant.types.DailyClose (REQ-24 input shape)."""

    date: date
    close: Decimal


class LatestBar(NamedTuple):
    date: date
    fetched_at: datetime


async def latest_by_instrument(db: AsyncSession, instrument_ids: Sequence[int]) -> dict[int, LatestBar]:
    """Per instrument: its latest stored trading day and when that row was last written."""
    if not instrument_ids:
        return {}
    query = (
        select(PriceHistory.instrument_id, func.max(PriceHistory.date), func.max(PriceHistory.fetched_at))
        .where(PriceHistory.instrument_id.in_(list(instrument_ids)))
        .group_by(PriceHistory.instrument_id)
    )
    return {row[0]: LatestBar(row[1], row[2]) for row in (await db.execute(query)).all()}


def _insert_for(db: AsyncSession):
    return postgresql.insert if db.bind.dialect.name == "postgresql" else sqlite.insert


async def upsert_bars(
    db: AsyncSession, instrument_id: int, currency: str, source: str, bars: Iterable[Mapping], fetched_at: datetime
) -> int:
    """Insert or replace bars on (instrument_id, date): a re-fetched day overwrites its row."""
    rows = [{**bar, "instrument_id": instrument_id, "currency": currency, "source": source, "fetched_at": fetched_at}
            for bar in bars]
    if not rows:
        return 0
    insert = _insert_for(db)(PriceHistory).values(rows)
    replaced = {column: insert.excluded[column]
                for column in ("open", "high", "low", "close", "volume", "currency", "source", "fetched_at")}
    await db.execute(insert.on_conflict_do_update(index_elements=["instrument_id", "date"], set_=replaced))
    return len(rows)


async def daily_closes(
    db: AsyncSession, instrument_id: int, since: Optional[date] = None
) -> list[DailyCloseRow]:
    """Stored closes for one instrument, oldest first, one per trading day."""
    query = select(PriceHistory.date, PriceHistory.close).where(PriceHistory.instrument_id == instrument_id)
    if since is not None:
        query = query.where(PriceHistory.date >= since)
    rows = (await db.execute(query.order_by(PriceHistory.date))).all()
    return [DailyCloseRow(row[0], Decimal(row[1])) for row in rows]
