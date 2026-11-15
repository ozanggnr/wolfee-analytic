"""Guarded AI text for the market summary and the single-instrument view (decision D5).

Deterministic code turns cached quotes into facts; the model may only describe
them; its text is checked and replaced by a template when it fails. There is no
recommendation, entry point, target or prediction, and no model call at all
when there is no market data.

The model call is synchronous network I/O: from async code use
``await asyncio.to_thread(market_insight_response, ...)``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

from ai.explain import Generator, explain_market, explain_stock, response_fields
from ai.facts import MARKET_DATA_LOADING, NO_MARKET_DATA, market_facts, stock_facts
from ai.guardrails import AIResult
from ai.provider import gemini_generate


def market_insight(
    market_data: Iterable[Mapping[str, object]] | None,
    *,
    now: datetime,
    inputs_as_of: datetime | None = None,
    generate: Generator | None = gemini_generate,
    loading: bool = False,
) -> AIResult:
    """Description of today's market from cached quotes.

    ``inputs_as_of`` is the age of the oldest quote used, supplied by the
    caller. With no usable quote the result is the template saying so, and the
    model is not called.

    ``loading=True`` is for a cache that is still filling: whatever
    ``market_data`` holds is partial, so none of it is described. The result is
    the template saying the data is still loading, and the model is not called.
    """
    facts = (MARKET_DATA_LOADING,) if loading else market_facts(market_data)
    if facts in ((NO_MARKET_DATA,), (MARKET_DATA_LOADING,)):
        generate = None
        inputs_as_of = None
    return explain_market(facts, now=now, inputs_as_of=inputs_as_of, generate=generate)


def stock_analysis(
    stock_data: Mapping[str, object] | None,
    *,
    now: datetime,
    inputs_as_of: datetime | None = None,
    generate: Generator | None = gemini_generate,
) -> AIResult:
    """Description of one instrument from its cached quote; template only when it has no price."""
    facts = stock_facts(stock_data)
    if len(facts) == 1:
        generate = None
        inputs_as_of = None
    return explain_stock(facts, now=now, inputs_as_of=inputs_as_of, generate=generate)


def market_insight_response(
    market_data: Iterable[Mapping[str, object]] | None,
    *,
    now: datetime,
    inputs_as_of: datetime | None = None,
    generate: Generator | None = gemini_generate,
    loading: bool = False,
) -> dict:
    """Body of ``GET /api/insight``: ``insight`` plus the provenance fields.

    Pass ``loading=True`` while the cache is still filling (see ``market_insight``).
    """
    result = market_insight(market_data, now=now, inputs_as_of=inputs_as_of, generate=generate,
                            loading=loading)
    return {"insight": result.text, **response_fields(result)}


def stock_analysis_response(
    symbol: str,
    stock_data: Mapping[str, object] | None,
    *,
    now: datetime,
    inputs_as_of: datetime | None = None,
    generate: Generator | None = gemini_generate,
) -> dict:
    """Body of ``GET /api/ai/analyze/{symbol}``: ``symbol``, ``analysis`` and the provenance fields."""
    result = stock_analysis(stock_data, now=now, inputs_as_of=inputs_as_of, generate=generate)
    return {"symbol": symbol, "analysis": result.text, **response_fields(result)}
