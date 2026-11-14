"""Whether stock_data holds enough for a market insight (REQ-20).

The daily insight summarises BIST and global stocks. Built from an empty or
partial cache, it reported "0 stocks, +0.00%" as if that were the market. An
insight is built only when at least MIN_MARKET_COVERAGE of each stock universe
is cached; until then the "still loading" placeholder is shown and not stored.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Tuple

from quant.universe import BIST_SYMBOLS, GLOBAL_SYMBOLS

MIN_MARKET_COVERAGE = 0.5

# stock_data.market_type -> size of that universe
UNIVERSE_SIZES = {"BIST": len(set(BIST_SYMBOLS)), "GLOBAL": len(set(GLOBAL_SYMBOLS))}

INSIGHT_LOADING_TEXT = (
    "🐺 Wolfee AI: Market data is still loading. "
    "Today's market summary appears after the first data refresh."
)


def coverage(rows: Iterable[Tuple[str, str]]) -> dict[str, int]:
    """Distinct cached symbols per market from (market_type, symbol) rows."""
    seen: dict[str, set[str]] = {market: set() for market in UNIVERSE_SIZES}
    for market_type, symbol in rows:
        if market_type in seen and symbol:
            seen[market_type].add(symbol)
    return {market: len(symbols) for market, symbols in seen.items()}


def is_ready(counts: Mapping[str, int]) -> bool:
    return all(counts.get(market, 0) >= MIN_MARKET_COVERAGE * size for market, size in UNIVERSE_SIZES.items())


def describe(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{market} {counts.get(market, 0)}/{size}" for market, size in UNIVERSE_SIZES.items())
