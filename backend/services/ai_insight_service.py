"""Stored and generated AI text with provenance (REQ-28, decision D5, DATABASE_CONTRACT §4.4).

All AI text comes from the guarded layer (``ai.insights``): facts computed by
deterministic code, model text checked by the guardrails, the template on any
violation or provider error. Every response carries ``generated_by``,
``generated_at``, ``inputs_as_of``, ``is_fallback`` and the disclaimer;
``violations`` never leave the server (the guarded layer logs them).

A stored ``ai_insights`` row without ``generated_by`` / ``generated_at`` was written
before provenance existed and may hold pre-D5 adviser wording: it is never served.

The model call is blocking network I/O, so it runs through ``asyncio.to_thread``,
and no database session is held open across it.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.guardrails import MARKET_DISCLAIMER
from ai.insights import market_insight_response, stock_analysis_response
from ai.provider import gemini_generate
from models import AIInsight

DAILY = "daily"
KEEP_LATEST = 10

# The model generator; tests replace it. None would mean "template only".
generate_text = gemini_generate


def utc(value: Optional[datetime]) -> Optional[datetime]:
    """An aware UTC datetime; naive values (SQLite, ``stock_data.updated_at``) are UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def oldest_quote_time(stocks: Iterable[Any]) -> Optional[datetime]:
    """``inputs_as_of`` for a set of cached quotes: the time of the oldest one, if known."""
    times = [utc(stock.updated_at) for stock in stocks if getattr(stock, "updated_at", None)]
    return min(times) if times else None


async def latest_with_provenance(db: AsyncSession) -> Optional[AIInsight]:
    """The newest daily insight that may be served; rows without provenance are skipped."""
    return (await db.execute(
        select(AIInsight)
        .where(AIInsight.insight_type == DAILY, AIInsight.generated_by.is_not(None),
               AIInsight.generated_at.is_not(None), AIInsight.insight_text.is_not(None))
        .order_by(desc(AIInsight.generated_at))
        .limit(1))).scalar_one_or_none()


def stored_response(row: AIInsight) -> dict:
    """Body of ``GET /api/insight`` for a stored row, in the shape of ``market_insight_response``."""
    inputs_as_of = utc(row.inputs_as_of)
    return {
        "insight": row.insight_text,
        "generated_by": row.generated_by,
        "generated_at": utc(row.generated_at).isoformat(),
        "inputs_as_of": None if inputs_as_of is None else inputs_as_of.isoformat(),
        "is_fallback": bool(row.is_fallback),
        "disclaimer": MARKET_DISCLAIMER,
    }


async def market_response(market_data: Sequence[Mapping[str, Any]], inputs_as_of: Optional[datetime],
                          now: Optional[datetime] = None) -> dict:
    """A new market insight from cached quotes, generated off the event loop."""
    return await asyncio.to_thread(market_insight_response, market_data, now=now or _now(),
                                   inputs_as_of=inputs_as_of, generate=generate_text)


def market_placeholder(now: Optional[datetime] = None, loading: bool = False) -> dict:
    """The template insight, without a model call: ``loading=True`` while the cache is still
    filling ("still loading"), otherwise "no market data" (used on any error)."""
    return market_insight_response(None, now=now or _now(), generate=None, loading=loading)


async def stock_response(symbol: str, stock_data: Mapping[str, Any], inputs_as_of: Optional[datetime],
                         now: Optional[datetime] = None) -> dict:
    return await asyncio.to_thread(stock_analysis_response, symbol, stock_data, now=now or _now(),
                                   inputs_as_of=inputs_as_of, generate=generate_text)


def stock_placeholder(symbol: str, now: Optional[datetime] = None) -> dict:
    """The template for an instrument without data: used on any error."""
    return stock_analysis_response(symbol, None, now=now or _now(), generate=None)


async def store(db: AsyncSession, response: Mapping[str, Any]) -> AIInsight:
    """Save a generated market insight with all four provenance values; keep the newest ten."""
    row = AIInsight(
        insight_type=DAILY,
        insight_text=response["insight"],
        generated_by=response["generated_by"],
        generated_at=datetime.fromisoformat(response["generated_at"]),
        inputs_as_of=None if response["inputs_as_of"] is None else datetime.fromisoformat(response["inputs_as_of"]),
        is_fallback=bool(response["is_fallback"]),
    )
    db.add(row)
    await db.flush()
    old_ids = (await db.execute(
        select(AIInsight.id).where(AIInsight.insight_type == DAILY)
        .order_by(desc(AIInsight.created_at), desc(AIInsight.id)).offset(KEEP_LATEST))).scalars().all()
    if old_ids:
        await db.execute(delete(AIInsight).where(AIInsight.id.in_(old_ids)))
    return row


def _now() -> datetime:
    return datetime.now(timezone.utc)
