"""Read-only access to the latest-quote cache (`stock_data`, written by workers.py)."""
from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import StockData


async def rows_for_symbols(db: AsyncSession, symbols: Iterable[str]) -> Sequence[StockData]:
    """Cached rows whose symbol is any of `symbols`, newest first.

    BIST rows may be stored as `THYAO` or `THYAO.IS` (DATABASE_CONTRACT §2.6), so
    callers pass both spellings and pick the newest row per instrument.
    """
    wanted = sorted(set(symbols))
    if not wanted:
        return []
    rows = await db.scalars(
        select(StockData)
        .where(StockData.symbol.in_(wanted))
        .order_by(StockData.updated_at.desc(), StockData.id.desc())
    )
    return rows.all()
