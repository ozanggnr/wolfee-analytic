"""Queries on `instruments`, the shared registry of tradable things (not user-owned)."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Instrument


async def find_active(
    db: AsyncSession, symbol: str, exchange: Optional[str] = None
) -> Sequence[Instrument]:
    """Active instruments whose canonical or provider symbol equals `symbol`."""
    query = select(Instrument).where(
        or_(Instrument.symbol == symbol, Instrument.provider_symbol == symbol),
        Instrument.is_active.is_(True),
    )
    if exchange is not None:
        query = query.where(Instrument.exchange == exchange)
    return (await db.scalars(query.order_by(Instrument.exchange))).all()


async def get_by_identity(db: AsyncSession, symbol: str, exchange: str) -> Optional[Instrument]:
    return await db.scalar(
        select(Instrument).where(Instrument.symbol == symbol, Instrument.exchange == exchange)
    )
