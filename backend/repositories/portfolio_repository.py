"""Queries on `portfolios`. Every function takes the owning user's id."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Portfolio


def _owned_by(user_id: int, include_archived: bool):
    conditions = [Portfolio.user_id == user_id]
    if not include_archived:
        conditions.append(Portfolio.archived_at.is_(None))
    return conditions


async def list_for_user(
    db: AsyncSession, user_id: int, *, include_archived: bool, limit: int, offset: int
) -> tuple[Sequence[Portfolio], int]:
    conditions = _owned_by(user_id, include_archived)
    total = await db.scalar(select(func.count()).select_from(Portfolio).where(*conditions))
    rows = await db.scalars(
        select(Portfolio)
        .where(*conditions)
        .order_by(Portfolio.created_at.desc(), Portfolio.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return rows.all(), total or 0


async def get_for_user(
    db: AsyncSession, user_id: int, portfolio_id: int, *, for_update: bool = False
) -> Optional[Portfolio]:
    query = select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
    if for_update:  # row lock on Postgres; SQLite ignores it
        query = query.with_for_update()
    return await db.scalar(query)


async def active_name_taken(
    db: AsyncSession, user_id: int, name: str, *, excluding_id: Optional[int] = None
) -> bool:
    query = select(Portfolio.id).where(
        Portfolio.user_id == user_id, Portfolio.name == name, Portfolio.archived_at.is_(None)
    )
    if excluding_id is not None:
        query = query.where(Portfolio.id != excluding_id)
    return await db.scalar(query.limit(1)) is not None
