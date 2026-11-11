"""FX rates into the portfolio base currency, from the exchange-rate cache (decision D3).

The cache holds TCMB `today.xml` rates quoted against TRY (`USD/TRY`, `EUR/TRY`),
refreshed by the worker. Positions are valued at the ForexBuying rate. Only
conversions into TRY exist in the source; for any other base currency no rate is
supplied, so foreign positions report `missing_fx_rate` rather than an inverted or
cross rate computed here.
"""
from __future__ import annotations

from datetime import timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models import ExchangeRate
from quant.types import FxRate
from repositories import fx_repository

FX_SOURCE = "tcmb_forex_buying"
FX_QUOTE_CURRENCY = "TRY"


def _pair(currency: str) -> str:
    return f"{currency}/{FX_QUOTE_CURRENCY}"


def _to_rate(currency: str, row: ExchangeRate) -> Optional[FxRate]:
    """The cached rate as an FxRate; None if unusable. A failed fetch stores 0, never used."""
    if row.buying is None or row.updated_at is None:
        return None
    try:
        rate = Decimal(repr(float(row.buying)))
    except (InvalidOperation, ValueError):
        return None
    if not rate.is_finite() or rate <= 0:
        return None
    updated = row.updated_at if row.updated_at.tzinfo is None else row.updated_at.astimezone(timezone.utc)
    return FxRate(base=currency, quote=FX_QUOTE_CURRENCY, rate=rate, as_of=updated.date(), source=FX_SOURCE)


async def rates_to_base(db: AsyncSession, currencies: Iterable[str], base_currency: str) -> dict[str, FxRate]:
    """Usable rates converting each foreign currency into `base_currency`, keyed by currency."""
    if base_currency != FX_QUOTE_CURRENCY:
        return {}
    foreign = {c for c in currencies if c != base_currency}
    by_pair = {row.pair: row for row in await fx_repository.rows_for_pairs(db, (_pair(c) for c in foreign))}
    rates: dict[str, FxRate] = {}
    for currency in foreign:
        row = by_pair.get(_pair(currency))
        rate = _to_rate(currency, row) if row is not None else None
        if rate is not None:
            rates[currency] = rate
    return rates
