"""Transaction ledger endpoints (API_CONTRACT §5.1).

Append and void only: there is deliberately no route that edits or deletes a row.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from routers.deps import (
    DEFAULT_LIMIT, Limit, Offset, PortfolioId, TransactionId, http_errors, no_store,
)
from schemas.common import Page
from schemas.transaction import TransactionCreate, TransactionOut, TransactionVoid
from security_middleware import get_current_user
from services import transaction_service

router = APIRouter(
    prefix="/api/v1/portfolios/{portfolio_id}/transactions",
    tags=["Transactions"],
    dependencies=[Depends(no_store)],
)


@router.get("", response_model=Page[TransactionOut])
async def list_transactions(
    portfolio_id: PortfolioId,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await transaction_service.list_transactions(
            db, current_user.id, portfolio_id, limit=limit, offset=offset
        )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def record_transaction(
    portfolio_id: PortfolioId,
    payload: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    with http_errors():
        return await transaction_service.record_transaction(db, current_user.id, portfolio_id, payload)


@router.post(
    "/{transaction_id}/void", response_model=TransactionOut, status_code=status.HTTP_201_CREATED
)
async def void_transaction(
    portfolio_id: PortfolioId,
    transaction_id: TransactionId,
    payload: Optional[TransactionVoid] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reverse a transaction by appending a row that voids it."""
    note = payload.note if payload else None
    with http_errors():
        return await transaction_service.void_transaction(
            db, current_user.id, portfolio_id, transaction_id, note
        )
