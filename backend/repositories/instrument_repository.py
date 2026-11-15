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


async def all_instruments(db: AsyncSession) -> Sequence[Instrument]:
    return (await db.scalars(select(Instrument))).all()


async def active_on_exchanges(db: AsyncSession, exchanges: Sequence[str]) -> Sequence[Instrument]:
    """Active instruments listed on any of `exchanges`, in a stable order."""
    if not exchanges:
        return ()
    query = select(Instrument).where(Instrument.exchange.in_(list(exchanges)), Instrument.is_active.is_(True))
    return (await db.scalars(query.order_by(Instrument.exchange, Instrument.symbol))).all()
