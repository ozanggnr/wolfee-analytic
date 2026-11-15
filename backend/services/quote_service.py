"""Builds quant PriceQuotes from the latest-quote cache, with honest provenance.

The cache (`stock_data`) is filled by the refresh worker from yfinance and HTML
scrapes. None of them is an exchange real-time feed, so a quote is labelled
`delayed` at best and `stale` once it is older than QUOTE_DELAYED_MAX_AGE.
The cache records no provider per row, so `source` names the cache itself.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models import Instrument, StockData
from quant.types import Freshness, PriceQuote
from repositories import quote_repository

QUOTE_SOURCE = "wolfee_quote_cache"
QUOTE_DELAYED_MAX_AGE = timedelta(hours=1)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def freshness_for(as_of: datetime, now: datetime) -> Freshness:
    return Freshness.DELAYED if now - as_of <= QUOTE_DELAYED_MAX_AGE else Freshness.STALE


def _price(row: StockData) -> Optional[Decimal]:
    """The cached float as the Decimal it prints as; None if unusable. Never a placeholder."""
    if row.price is None or row.price <= 0:
        return None
    try:
        price = Decimal(repr(float(row.price)))
    except (InvalidOperation, ValueError):
        return None
    return price if price.is_finite() else None


def _to_quote(key: str, row: StockData, now: datetime) -> Optional[PriceQuote]:
    price = _price(row)
    if price is None or row.updated_at is None or not row.currency:
        return None
    as_of = _as_utc(row.updated_at)
    return PriceQuote(
        symbol=key,
        price=price,
        currency=row.currency.strip(),
        as_of=as_of,
        freshness=freshness_for(as_of, now),
        source=QUOTE_SOURCE,
    )


async def latest_quotes(
    db: AsyncSession, instruments: Mapping[str, Instrument], now: datetime
) -> dict[str, PriceQuote]:
    """The newest usable cached quote per position key. Keys without one are absent.

    The cache is keyed by bare symbol only. A spelling shared by two held instruments
    cannot be attributed to either, so it is not used for them (no guessing).
    """
    owners: dict[str, set[str]] = {}
    for key, instrument in instruments.items():
        for spelling in (instrument.symbol, instrument.provider_symbol):
            owners.setdefault(spelling.upper(), set()).add(key)
    spellings = {spelling: next(iter(keys)) for spelling, keys in owners.items() if len(keys) == 1}

    quotes: dict[str, PriceQuote] = {}
    for row in await quote_repository.rows_for_symbols(db, spellings):
        key = spellings.get((row.symbol or "").upper())
        if key is None or key in quotes:
            continue  # rows arrive newest first; keep the first usable one
        quote = _to_quote(key, row, now)
        if quote is not None:
            quotes[key] = quote
    return quotes
