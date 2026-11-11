"""Portfolio rules: ownership, unique active names and soft delete."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import Portfolio
from repositories import portfolio_repository
from schemas.common import Page
from schemas.portfolio import PortfolioCreate, PortfolioOut, PortfolioUpdate
from services.errors import ConflictError, NotFoundError, is_unique_violation

NOT_FOUND = "Portfolio not found."
NAME_TAKEN = "You already have an active portfolio with this name."
ARCHIVED = "This portfolio is archived and can no longer be changed."


async def load_owned(db: AsyncSession, user_id: int, portfolio_id: int) -> Portfolio:
    """The caller's portfolio row, or NotFoundError if it is missing or someone else's."""
    portfolio = await portfolio_repository.get_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise NotFoundError(NOT_FOUND)
    return portfolio


async def load_writable(db: AsyncSession, user_id: int, portfolio_id: int) -> Portfolio:
    """The caller's active portfolio, row-locked until commit so a concurrent
    archive cannot slip in between this check and the write."""
    portfolio = await portfolio_repository.get_for_user(db, user_id, portfolio_id, for_update=True)
    if portfolio is None:
        raise NotFoundError(NOT_FOUND)
    if portfolio.archived_at is not None:
        raise ConflictError(ARCHIVED)
    return portfolio


async def _commit_unique_name(db: AsyncSession) -> None:
    """Commit; a concurrent request that took the name first surfaces as a conflict."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if not is_unique_violation(exc, "uq_portfolios_user_name_active", "portfolios.user_id, portfolios.name"):
            raise
        raise ConflictError(NAME_TAKEN) from exc


async def list_portfolios(
    db: AsyncSession, user_id: int, *, include_archived: bool, limit: int, offset: int
) -> Page[PortfolioOut]:
    rows, total = await portfolio_repository.list_for_user(
        db, user_id, include_archived=include_archived, limit=limit, offset=offset
    )
    items = [PortfolioOut.model_validate(row) for row in rows]
    return Page[PortfolioOut](items=items, total=total, limit=limit, offset=offset)


async def get_portfolio(db: AsyncSession, user_id: int, portfolio_id: int) -> PortfolioOut:
    return PortfolioOut.model_validate(await load_owned(db, user_id, portfolio_id))


async def create_portfolio(db: AsyncSession, user_id: int, payload: PortfolioCreate) -> PortfolioOut:
    if await portfolio_repository.active_name_taken(db, user_id, payload.name):
        raise ConflictError(NAME_TAKEN)
    portfolio = Portfolio(
        user_id=user_id,
        name=payload.name,
        base_currency=payload.base_currency,
        kind=payload.kind,
        created_at=datetime.now(timezone.utc),
    )
    db.add(portfolio)
    await _commit_unique_name(db)
    return PortfolioOut.model_validate(portfolio)


async def rename_portfolio(
    db: AsyncSession, user_id: int, portfolio_id: int, payload: PortfolioUpdate
) -> PortfolioOut:
    portfolio = await load_writable(db, user_id, portfolio_id)
    if await portfolio_repository.active_name_taken(db, user_id, payload.name, excluding_id=portfolio.id):
        raise ConflictError(NAME_TAKEN)
    portfolio.name = payload.name
    await _commit_unique_name(db)
    return PortfolioOut.model_validate(portfolio)


async def archive_portfolio(db: AsyncSession, user_id: int, portfolio_id: int) -> PortfolioOut:
    """Soft delete. The ledger is kept; archiving again is a no-op."""
    portfolio = await load_owned(db, user_id, portfolio_id)
    if portfolio.archived_at is None:
        portfolio.archived_at = datetime.now(timezone.utc)
        await db.commit()
    return PortfolioOut.model_validate(portfolio)
