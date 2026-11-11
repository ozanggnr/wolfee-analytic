"""Read-only access to the exchange-rate cache (`exchange_rates`, written by workers.py)."""
from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ExchangeRate


async def rows_for_pairs(db: AsyncSession, pairs: Iterable[str]) -> Sequence[ExchangeRate]:
    wanted = sorted(set(pairs))
    if not wanted:
        return []
    return (await db.scalars(select(ExchangeRate).where(ExchangeRate.pair.in_(wanted)))).all()
