"""Which market a watchlist ticker belongs to (REQ-19).

The server decides; the client's market is only a hint. Resolution order:

1. an explicit suffix (``.IS``, ``=F``, ``=X``) is definitive;
2. the instruments table (the hint picks between listings on two exchanges);
3. the known symbol universe (BIST and global lists in ``quant.universe``);
4. only for a symbol known nowhere, the hint, else ``quant.symbols`` defaults (BIST).

A hint that is impossible for the symbol's form (COMMODITY for AAPL) is refused; a
plausible but wrong one (US for THYAO) is corrected.

The smoke test stored THYAO as "US" because the frontend sent ``market: "US"`` and
the backend trusted it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from quant.symbols import (
    EXCHANGE_BIST, EXCHANGE_COMMODITY, EXCHANGE_FX, EXCHANGE_US, normalize_symbol,
)
from quant.types import CanonicalSymbol
from quant.universe import BIST_SYMBOLS, GLOBAL_SYMBOLS
from repositories import instrument_repository

# watchlist_items.market vocabulary (API_CONTRACT §2.8). FX has no value of its own;
# GLOBAL makes the enrichment look it up by its provider symbol.
WATCHLIST_MARKET = {
    EXCHANGE_BIST: "BIST100",
    EXCHANGE_US: "US",
    EXCHANGE_COMMODITY: "COMMODITY",
    EXCHANGE_FX: "GLOBAL",
}

_KNOWN_SYMBOLS = frozenset(normalize_symbol(s).symbol for s in (*BIST_SYMBOLS, *GLOBAL_SYMBOLS))


@dataclass(frozen=True)
class WatchlistSymbol:
    ticker: str
    market: str


def _has_explicit_market(raw: str) -> bool:
    cleaned = raw.strip().upper()
    return cleaned.endswith(".IS") or "=" in cleaned


def _out(canonical: CanonicalSymbol) -> WatchlistSymbol:
    return WatchlistSymbol(ticker=canonical.symbol, market=WATCHLIST_MARKET[canonical.exchange])


async def resolve(db: AsyncSession, raw: str, market_hint: Optional[str] = None) -> WatchlistSymbol:
    """Raise ValueError when ``raw`` is not a symbol, or the hint contradicts its form."""
    plain = normalize_symbol(raw)
    hinted = normalize_symbol(raw, market_hint) if market_hint else None
    if _has_explicit_market(raw):
        return _out(plain)

    listed = {row.exchange for row in await instrument_repository.find_active(db, plain.symbol)}
    listed &= WATCHLIST_MARKET.keys()
    if listed:
        preferred = (hinted.exchange if hinted else None, plain.exchange)
        exchange = next((e for e in preferred if e in listed), min(listed))
        return WatchlistSymbol(ticker=plain.symbol, market=WATCHLIST_MARKET[exchange])

    if plain.symbol in _KNOWN_SYMBOLS:
        return _out(plain)
    return _out(hinted or plain)
