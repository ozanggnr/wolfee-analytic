"""The one symbol normaliser (TEAM_STRUCTURE H6, DATABASE_CONTRACT §3.1).

Every layer should turn user or provider input into a :class:`CanonicalSymbol`
here instead of appending or stripping ``.IS`` itself. The canonical ``symbol``
has no provider suffix (``THYAO``); ``provider_symbol`` is what the data source
needs (``THYAO.IS``).

Resolution order, matching the existing behaviour in API_CONTRACT §1.5:

1. a symbol containing ``=`` is FX (``…=X``) or a commodity future (``…=F``);
2. an explicit ``.IS`` suffix means BIST, whatever the hint says;
3. otherwise the market hint decides;
4. with no hint, a symbol in the global universe is a US listing and anything
   else is treated as BIST.
"""
from __future__ import annotations

import re

from quant.types import CanonicalSymbol, InstrumentSeed
from quant.universe import BIST_SYMBOLS, COMMODITIES_SYMBOLS, GLOBAL_SYMBOLS

EXCHANGE_BIST = "BIST"
EXCHANGE_US = "US"
EXCHANGE_COMMODITY = "CMDTY"
EXCHANGE_FX = "FX"

MAX_SYMBOL_LENGTH = 20
_SYMBOL_PATTERN = re.compile(r"[A-Z0-9]+(?:[.\-=][A-Z0-9]+)*")
_COMMODITY_PATTERN = re.compile(r"[A-Z0-9]{1,6}=F")
_BIST_SUFFIX = ".IS"
_FX_SUFFIX = "=X"
_CURRENCY_CODE_LENGTH = 3

# Both vocabularies in use today: stock_data.market_type and watchlist_items.market.
_HINT_TO_EXCHANGE = {
    "BIST": EXCHANGE_BIST,
    "BIST100": EXCHANGE_BIST,
    "US": EXCHANGE_US,
    "GLOBAL": EXCHANGE_US,
    "COMMODITY": EXCHANGE_COMMODITY,
    "CMDTY": EXCHANGE_COMMODITY,
    "FX": EXCHANGE_FX,
}
_GLOBAL_SYMBOL_SET = frozenset(GLOBAL_SYMBOLS)


def normalize_symbol(raw: str, market_hint: str | None = None) -> CanonicalSymbol:
    """Resolve ``raw`` to its canonical identity; raise ValueError if it is not a valid symbol."""
    symbol = _clean(raw)
    hinted_exchange = _exchange_for_hint(market_hint)

    if "=" in symbol:
        return _fx(symbol) if symbol.endswith(_FX_SUFFIX) else _commodity(symbol)
    if symbol.endswith(_BIST_SUFFIX):
        return _bist(symbol[: -len(_BIST_SUFFIX)])
    if "." in symbol:
        raise ValueError(f"unsupported exchange suffix in symbol {symbol!r}")
    if hinted_exchange in (EXCHANGE_COMMODITY, EXCHANGE_FX):
        raise ValueError(f"{symbol!r} is not a {market_hint} symbol")
    if hinted_exchange == EXCHANGE_BIST:
        return _bist(symbol)
    if hinted_exchange == EXCHANGE_US or symbol in _GLOBAL_SYMBOL_SET:
        return _us(symbol)
    return _bist(symbol)


def instrument_seed() -> tuple[InstrumentSeed, ...]:
    """One row per tracked instrument, for seeding the ``instruments`` table (migration M1).

    ``name`` is filled only where the code base holds a real display name;
    it is never invented from the ticker.
    """
    equities = [(provider_symbol, None) for provider_symbol in (*BIST_SYMBOLS, *GLOBAL_SYMBOLS)]
    commodities = list(COMMODITIES_SYMBOLS.items())
    return tuple(_seed(normalize_symbol(symbol), name) for symbol, name in (*equities, *commodities))


def _seed(canonical: CanonicalSymbol, name: str | None) -> InstrumentSeed:
    return InstrumentSeed(
        symbol=canonical.symbol,
        exchange=canonical.exchange,
        provider_symbol=canonical.provider_symbol,
        currency=canonical.currency,
        asset_class=canonical.asset_class,
        name=name,
    )


def _clean(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("symbol must be a string")
    # ASCII only: str.upper() would otherwise turn letters such as "ſ" or "ß" into valid tickers.
    symbol = raw.strip().upper() if raw.isascii() else ""
    if not symbol or len(symbol) > MAX_SYMBOL_LENGTH or not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError(f"invalid symbol: {raw!r}")
    return symbol


def _exchange_for_hint(market_hint: str | None) -> str | None:
    if market_hint is None:
        return None
    exchange = _HINT_TO_EXCHANGE.get(str(market_hint).strip().upper())
    if exchange is None:
        raise ValueError(f"unknown market_hint: {market_hint!r}")
    return exchange


def _bist(stem: str) -> CanonicalSymbol:
    return CanonicalSymbol(stem, EXCHANGE_BIST, f"{stem}{_BIST_SUFFIX}", "TRY", "equity")


def _us(symbol: str) -> CanonicalSymbol:
    return CanonicalSymbol(symbol, EXCHANGE_US, symbol, "USD", "equity")


def _commodity(symbol: str) -> CanonicalSymbol:
    if not _COMMODITY_PATTERN.fullmatch(symbol):
        raise ValueError(f"unsupported symbol: {symbol!r}")
    return CanonicalSymbol(symbol, EXCHANGE_COMMODITY, symbol, "USD", "commodity")


def _fx(symbol: str) -> CanonicalSymbol:
    """Yahoo FX pairs: ``USDTRY=X`` is priced in TRY, ``EUR=X`` is USD priced in EUR."""
    pair = symbol[: -len(_FX_SUFFIX)]
    if len(pair) not in (_CURRENCY_CODE_LENGTH, 2 * _CURRENCY_CODE_LENGTH) or not pair.isalpha():
        raise ValueError(f"unsupported FX symbol: {symbol!r}")
    return CanonicalSymbol(symbol, EXCHANGE_FX, symbol, pair[-_CURRENCY_CODE_LENGTH:], "fx")
