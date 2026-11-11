"""Portfolio endpoints (API_CONTRACT §5.1). A session is required on every route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from routers.deps import DEFAULT_LIMIT, Limit, Offset, PortfolioId, http_errors, no_store
from schemas.common import Page
from schemas.portfolio import PortfolioCreate, PortfolioOut, PortfolioUpdate
from security_middleware import get_current_user
from services import portfolio_service

router = APIRouter(prefix="/api/v1/portfolios", tags=["Portfolios"], dependencies=[Depends(no_store)])


@router.get("", response_model=Page[PortfolioOut])
async def list_portfolios(
    include_archived: bool = Query(False),
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await portfolio_service.list_portfolios(
        db, current_user.id, include_archived=include_archived, limit=limit, offset=offset
    )


@router.post("", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await portfolio_service.create_portfolio(db, current_user.id, payload)


@router.get("/{portfolio_id}", response_model=PortfolioOut)
async def get_portfolio(
    portfolio_id: PortfolioId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await portfolio_service.get_portfolio(db, current_user.id, portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioOut)
async def rename_portfolio(
    portfolio_id: PortfolioId,
    payload: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await portfolio_service.rename_portfolio(db, current_user.id, portfolio_id, payload)


@router.delete("/{portfolio_id}", response_model=PortfolioOut)
async def archive_portfolio(
    portfolio_id: PortfolioId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archive (soft delete). The transaction history is kept."""
    with http_errors():
        return await portfolio_service.archive_portfolio(db, current_user.id, portfolio_id)
