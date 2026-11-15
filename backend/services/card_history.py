"""Real daily closes for the market-card quotes (REQ-10, REQ-24, REQ-26; decision D4).

The workers enrich every refreshed quote with ``quant.signals.enrich_quote``. This
module supplies its ``history`` argument: the instrument's stored ``price_history``
closes as ``quant.types.DailyClose`` values with Decimal closes. A quote whose
instrument is unknown, or that has no stored close, gets ``None``, so its
indicators are null; nothing is estimated in its place.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Instrument, PriceHistory
from quant.symbols import normalize_symbol
from quant.types import DailyClose

# stock_data.market_type -> the market hint normalize_symbol understands.
_MARKET_HINTS = {"BIST": "BIST", "GLOBAL": "US", "COMMODITY": "COMMODITY"}

History = Optional[tuple[DailyClose, ...]]


def _identity(symbol: str, market_type: str) -> Optional[tuple[str, str]]:
    try:
        canonical = normalize_symbol(symbol, _MARKET_HINTS.get(market_type))
    except ValueError:
        return None
    return canonical.symbol, canonical.exchange


async def histories_for(db: AsyncSession, market_type: str, symbols: Iterable[str]) -> dict[str, History]:
    """``{quote symbol: closes oldest first, or None}`` for one market's quotes, in two queries."""
    identities = {symbol: _identity(symbol, market_type) for symbol in symbols}
    wanted = {identity for identity in identities.values() if identity is not None}
    if not wanted:
        return {symbol: None for symbol in identities}

    instruments = (await db.execute(
        select(Instrument.id, Instrument.symbol, Instrument.exchange).where(
            Instrument.exchange.in_({exchange for _, exchange in wanted}),
            Instrument.symbol.in_({symbol for symbol, _ in wanted}),
        ))).all()
    id_by_identity = {(row.symbol, row.exchange): row.id for row in instruments
                      if (row.symbol, row.exchange) in wanted}

    closes = await _closes_by_instrument(db, list(id_by_identity.values()))
    return {symbol: (closes.get(id_by_identity.get(identity)) if identity else None) or None
            for symbol, identity in identities.items()}


async def _closes_by_instrument(db: AsyncSession, instrument_ids: Sequence[int]) -> dict[int, tuple[DailyClose, ...]]:
    if not instrument_ids:
        return {}
    rows = (await db.execute(
        select(PriceHistory.instrument_id, PriceHistory.date, PriceHistory.close)
        .where(PriceHistory.instrument_id.in_(instrument_ids))
        .order_by(PriceHistory.instrument_id, PriceHistory.date))).all()
    grouped: dict[int, list[DailyClose]] = defaultdict(list)
    for instrument_id, day, close in rows:
        grouped[instrument_id].append(DailyClose(date=day, close=Decimal(str(close))))
    return {instrument_id: tuple(points) for instrument_id, points in grouped.items()}
