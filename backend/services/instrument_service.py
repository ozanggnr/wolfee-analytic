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


def _normalized(seed: InstrumentSeedLike) -> InstrumentSeedLike:
    """Upper-case identity fields so lookups (which match upper case) always find the row."""
    return _Seed(
        symbol=seed.symbol.strip().upper(),
        exchange=seed.exchange.strip().upper(),
        provider_symbol=seed.provider_symbol.strip().upper(),
        currency=seed.currency.strip().upper(),
        asset_class=seed.asset_class.strip(),
        name=seed.name,
    )


@dataclass(frozen=True)
class _Seed:
    symbol: str
    exchange: str
    provider_symbol: str
    currency: str
    asset_class: str
    name: Optional[str]


async def sync_instruments(db: AsyncSession, seeds: Iterable[InstrumentSeedLike]) -> SyncResult:
    """Insert missing instruments and refresh descriptive fields, in one transaction.

    Idempotent: a second run with the same seed changes nothing. Never deletes,
    deactivates or reactivates a row. Raises ValueError, before writing anything,
    if the seed lists one (symbol, exchange) twice.
    """
    normalized = [_normalized(seed) for seed in seeds]
    identities = [(seed.symbol, seed.exchange) for seed in normalized]
    if len(set(identities)) != len(identities):
        raise ValueError("instrument seed lists the same (symbol, exchange) more than once")

    existing = {(row.symbol, row.exchange): row for row in await instrument_repository.all_instruments(db)}
    inserted = 0
    updated = 0
    for seed in normalized:
        row = existing.get((seed.symbol, seed.exchange))
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


async def sync_from_quant_seed() -> SyncResult:
    """Load quant.symbols.instrument_seed() into the configured database (DATABASE_URL)."""
    from database import AsyncSessionLocal
    from quant.symbols import instrument_seed

    async with AsyncSessionLocal() as db:
        return await sync_instruments(db, instrument_seed())


def main() -> None:
    """Command line: `python -m services.instrument_service`, run from backend/ after
    `alembic upgrade head`. Safe to run on every deploy."""
    import asyncio

    result = asyncio.run(sync_from_quant_seed())
    print(f"instruments synced: {result.inserted} inserted, {result.updated} updated")


if __name__ == "__main__":
    main()
