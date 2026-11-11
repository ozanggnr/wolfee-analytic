"""Portfolio analytics endpoints (API_CONTRACT §5.2). Read-only; a session is required."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from quant.types import CostBasisMethod
from routers.deps import PortfolioId, http_errors, no_store
from schemas.analytics import CostBasisMethodName, HoldingsOut, PerformanceOut
from security_middleware import get_current_user
from services import analytics_service

router = APIRouter(
    prefix="/api/v1/portfolios/{portfolio_id}",
    tags=["Portfolio analytics"],
    dependencies=[Depends(no_store)],
)

DEFAULT_METHOD: CostBasisMethodName = analytics_service.DEFAULT_COST_BASIS_METHOD.value


@router.get("/holdings", response_model=HoldingsOut)
async def get_holdings(
    portfolio_id: PortfolioId,
    cost_basis_method: CostBasisMethodName = Query(DEFAULT_METHOD),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await analytics_service.holdings(
            db, current_user.id, portfolio_id, CostBasisMethod(cost_basis_method)
        )


@router.get("/performance", response_model=PerformanceOut)
async def get_performance(
    portfolio_id: PortfolioId,
    cost_basis_method: CostBasisMethodName = Query(DEFAULT_METHOD),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await analytics_service.performance(
            db, current_user.id, portfolio_id, CostBasisMethod(cost_basis_method)
        )
