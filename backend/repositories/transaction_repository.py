"""Queries on `transactions`. Read and insert only: the ledger is append-only.

Every query joins `portfolios` and filters on the owning user, so a transaction id
alone is never enough to reach a row.
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Portfolio, Transaction


def _in_owned_portfolio(user_id: int, portfolio_id: int):
    return (
        Transaction.portfolio_id == portfolio_id,
        Portfolio.id == Transaction.portfolio_id,
        Portfolio.user_id == user_id,
    )


async def list_for_portfolio(
    db: AsyncSession, user_id: int, portfolio_id: int, *, limit: int, offset: int
) -> tuple[Sequence[Transaction], int]:
    conditions = _in_owned_portfolio(user_id, portfolio_id)
    total = await db.scalar(select(func.count(Transaction.id)).where(*conditions))
    rows = await db.scalars(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return rows.all(), total or 0


async def get_in_portfolio(
    db: AsyncSession, user_id: int, portfolio_id: int, transaction_id: int
) -> Optional[Transaction]:
    return await db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, *_in_owned_portfolio(user_id, portfolio_id)
        )
    )


async def reversals_of(db: AsyncSession, transaction_ids: Sequence[int]) -> dict[int, int]:
    """Map each voided transaction id to the id of the row that voids it."""
    if not transaction_ids:
        return {}
    rows = await db.execute(
        select(Transaction.voids_transaction_id, Transaction.id).where(
            Transaction.voids_transaction_id.in_(transaction_ids)
        )
    )
    return {voided_id: reversal_id for voided_id, reversal_id in rows.all()}
