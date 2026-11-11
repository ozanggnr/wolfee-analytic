"""Loads the instrument registry from a seed list supplied by the quant layer.

The seed objects only need the attributes of `InstrumentSeed`
(symbol, exchange, provider_symbol, currency, asset_class, name).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from models import Instrument
from repositories import instrument_repository


class InstrumentSeedLike(Protocol):
    symbol: str
    exchange: str
    provider_symbol: str
    currency: str
    asset_class: str
    name: Optional[str]


@dataclass(frozen=True)
class SyncResult:
    inserted: int
    updated: int


def _refresh_descriptive_fields(row: Instrument, seed: InstrumentSeedLike) -> bool:
    """Update name and provider symbol only. Identity and currency are fixed once
    transactions may reference the row."""
    changed = False
    if seed.name and row.name != seed.name:
        row.name = seed.name
        changed = True
    if row.provider_symbol != seed.provider_symbol:
        row.provider_symbol = seed.provider_symbol
        changed = True
    return changed


async def sync_instruments(db: AsyncSession, seeds: Iterable[InstrumentSeedLike]) -> SyncResult:
    """Insert missing instruments and refresh descriptive fields. Never deletes,
    deactivates or reactivates a row."""
    inserted = 0
    updated = 0
    for seed in seeds:
        row = await instrument_repository.get_by_identity(db, seed.symbol, seed.exchange)
        if row is None:
            db.add(Instrument(
                symbol=seed.symbol,
                exchange=seed.exchange,
                provider_symbol=seed.provider_symbol,
                name=seed.name,
                currency=seed.currency,
                asset_class=seed.asset_class,
                is_active=True,
            ))
            inserted += 1
        elif _refresh_descriptive_fields(row, seed):
            updated += 1
    await db.commit()
    return SyncResult(inserted=inserted, updated=updated)
