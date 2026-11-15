"""
Watchlist & Portfolio Routes for Wolfee Analytics
Endpoints:
- GET    /api/watchlist
- POST   /api/watchlist
- DELETE /api/watchlist/{ticker}
- GET    /api/watchlist/summary (with 60-second TTL cache)
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, WatchlistItem, StockData
from security_middleware import get_current_user
from analysis import analyze_stock
from services import watchlist_symbols
from services.market_display import price_level, rounded

logger = logging.getLogger("watchlist_routes")

router = APIRouter(prefix="/api/watchlist", tags=["Portfolio Watchlist"])


# ============================================================
# SUMMARY IN-MEMORY CACHE (60s TTL per user)
# ============================================================
SUMMARY_CACHE_TTL = 60  # seconds
_summary_cache: Dict[int, Dict[str, Any]] = {}
# Bumped on every watchlist change, so a summary computed across a change is not cached (REQ-21).
_summary_generation: Dict[int, int] = {}
# The server cache above is evicted on change; a browser's HTTP cache would not be (REQ-21).
SUMMARY_CACHE_CONTROL = "no-store, private"


def invalidate_user_cache(user_id: int):
    """Evict user's summary cache when watchlist changes."""
    _summary_generation[user_id] = _summary_generation.get(user_id, 0) + 1
    _summary_cache.pop(user_id, None)


import re
from pydantic import BaseModel, Field, field_validator

TICKER_REGEX = re.compile(r"^[A-Za-z0-9]+(?:[\.\-=][A-Za-z0-9]+)*$")

# ============================================================
# SCHEMAS
# ============================================================
class AddWatchlistRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    market: Optional[str] = Field(None, max_length=20)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        clean = v.strip().upper()
        if not TICKER_REGEX.match(clean):
            raise ValueError("Invalid ticker format. Must be 1-20 alphanumeric characters, dots, or dashes.")
        return clean

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().upper()
            if clean not in ("BIST100", "US", "GLOBAL", "COMMODITY"):
                raise ValueError("Market must be BIST100, US, GLOBAL, or COMMODITY.")
            return clean
        return v


class WatchlistItemResponse(BaseModel):
    id: int
    ticker: str
    market: str
    added_at: str
    name: Optional[str] = None
    price: float = 0.0
    change_pct: float = 0.0
    volume: float = 0.0
    day_high: Optional[float] = None  # null until computed from real history (D4)
    day_low: Optional[float] = None
    rsi: Optional[float] = None
    currency: str = "USD"
    prediction: Optional[str] = None


# ============================================================
# HELPER: ENRICH TICKERS WITH MARKET DATA
# ============================================================
async def _enrich_watchlist_tickers(
    db: AsyncSession,
    items: List[WatchlistItem]
) -> List[Dict[str, Any]]:
    """
    Enrich watchlist tickers using Wolfee's multi-tier data pipeline:
    1. Primary: Query StockData database table (regularly updated by background workers)
    2. Fallback: On-demand live fetch via analyze_stock if not in DB
    """
    if not items:
        return []

    # Prepare lookup symbols (both raw ticker and ticker.IS)
    symbols_to_query = set()
    for item in items:
        sym = item.ticker.upper()
        symbols_to_query.add(sym)
        if item.market == "BIST100" and not sym.endswith(".IS"):
            symbols_to_query.add(f"{sym}.IS")

    # Fetch from DB StockData table
    result = await db.execute(
        select(StockData).where(StockData.symbol.in_(list(symbols_to_query)))
    )
    db_stocks = {s.symbol.upper(): s for s in result.scalars().all()}

    enriched_list = []
    for item in items:
        sym = item.ticker.upper()
        is_bist = item.market == "BIST100"
        lookup_key = f"{sym}.IS" if is_bist and not sym.endswith(".IS") else sym

        stock_record = db_stocks.get(lookup_key) or db_stocks.get(sym)

        if stock_record:
            enriched_list.append({
                "id": item.id,
                "ticker": sym,
                "market": item.market,
                "added_at": item.added_at.isoformat() if item.added_at else "",
                "name": stock_record.name or sym,
                "price": round(stock_record.price or 0.0, 2),
                "change_pct": round(stock_record.change_pct or 0.0, 2),
                "volume": stock_record.volume or 0.0,
                "day_high": price_level(stock_record.day_high),
                "day_low": price_level(stock_record.day_low),
                "rsi": rounded(stock_record.rsi, 1),
                "currency": stock_record.currency or ("TRY" if is_bist else "USD"),
                # A null label stays null (D4): no "Bullish" / "Bearish" from one day's move.
                "prediction": stock_record.prediction,
                "market_type": stock_record.market_type or item.market
            })
        else:
            # Fallback on-demand analysis
            try:
                live_data = analyze_stock(lookup_key, is_commodity=False, detailed=False)
            except Exception as e:
                logger.warning(f"Failed fallback fetch for {lookup_key}: {e}")
                live_data = None

            if live_data:
                enriched_list.append({
                    "id": item.id,
                    "ticker": sym,
                    "market": item.market,
                    "added_at": item.added_at.isoformat() if item.added_at else "",
                    "name": live_data.get("name", sym),
                    "price": round(live_data.get("price", 0.0), 2),
                    "change_pct": round(live_data.get("change_pct", 0.0), 2),
                    "volume": live_data.get("volume", 0.0),
                    "day_high": price_level(live_data.get("day_high")),
                    "day_low": price_level(live_data.get("day_low")),
                    "rsi": rounded(live_data.get("rsi"), 1),
                    "currency": live_data.get("currency", "TRY" if is_bist else "USD"),
                    "prediction": live_data.get("prediction", ""),
                    "market_type": item.market
                })
            else:
                # Default placeholder if both DB and live fetch are unavailable
                enriched_list.append({
                    "id": item.id,
                    "ticker": sym,
                    "market": item.market,
                    "added_at": item.added_at.isoformat() if item.added_at else "",
                    "name": sym,
                    "price": 0.0,
                    "change_pct": 0.0,
                    "volume": 0.0,
                    "day_high": None,
                    "day_low": None,
                    "rsi": None,
                    "currency": "TRY" if is_bist else "USD",
                    "prediction": "Data updating",
                    "market_type": item.market
                })

    return enriched_list


# ============================================================
# 1. GET USER WATCHLIST
# ============================================================
@router.get("")
async def get_user_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve watched tickers for the authenticated user,
    enriched with live/cached market data from Wolfee's database & provider pipeline.
    """
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.added_at.desc())
    )
    items = result.scalars().all()
    enriched = await _enrich_watchlist_tickers(db, items)

    return {
        "items": enriched,
        "count": len(enriched)
    }


# ============================================================
# 2. ADD TICKER TO WATCHLIST
# ============================================================
@router.post("", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    req: AddWatchlistRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a stock ticker to user's portfolio watchlist.
    The market is resolved on the server; a client-supplied market is only a hint.
    """
    raw_ticker = req.ticker.strip().upper()
    if not raw_ticker:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticker symbol required.")

    # The server decides the market; req.market is only a hint (REQ-19).
    try:
        resolved = await watchlist_symbols.resolve(db, raw_ticker, req.market)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    canonical_ticker, market = resolved.ticker, resolved.market

    # Check if already in watchlist
    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.ticker == canonical_ticker
        )
    )
    if existing.scalar_one_or_none():
        return {"message": f"{canonical_ticker} is already in your watchlist.", "ticker": canonical_ticker}

    item = WatchlistItem(
        user_id=current_user.id,
        ticker=canonical_ticker,
        market=market,
        added_at=datetime.now(timezone.utc)
    )
    db.add(item)
    await db.commit()

    # Invalidate cached summary
    invalidate_user_cache(current_user.id)

    return {
        "message": f"Added {canonical_ticker} to your watchlist.",
        "ticker": canonical_ticker,
        "market": market
    }


# ============================================================
# 3. REMOVE TICKER FROM WATCHLIST
# ============================================================
@router.delete("/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a ticker from the user's watchlist."""
    clean_ticker = ticker.strip().upper().replace(".IS", "")

    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.ticker.in_([clean_ticker, f"{clean_ticker}.IS"])
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{clean_ticker} not found in your watchlist."
        )

    await db.delete(item)
    await db.commit()

    invalidate_user_cache(current_user.id)

    return {"message": f"Removed {clean_ticker} from your watchlist.", "ticker": clean_ticker}


# ============================================================
# 4. WATCHLIST SUMMARY CARD (60-second TTL Cache)
# ============================================================
@router.get("/summary")
async def get_watchlist_summary(
    response: Response,
    force_refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Computes real-time portfolio performance metrics for the summary card:
    1. Count of tickers Up today vs Down today vs Unchanged
    2. The single biggest mover (highest absolute daily % move) highlighted
    3. Today's % change for each watched ticker
    4. Average portfolio percentage change
    Cached for 60 seconds to avoid hammering the data source.
    """
    now_ts = time.time()
    user_id = current_user.id
    generation = _summary_generation.get(user_id, 0)
    response.headers["Cache-Control"] = SUMMARY_CACHE_CONTROL

    # Check 60-second cache
    cached_entry = _summary_cache.get(user_id)
    if not force_refresh and cached_entry:
        age = now_ts - cached_entry["cached_at"]
        if age < SUMMARY_CACHE_TTL:
            remaining = int(SUMMARY_CACHE_TTL - age)
            data = cached_entry["data"].copy()
            data["from_cache"] = True
            data["cache_expires_in"] = remaining
            return data

    # Fetch user watchlist items
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.added_at.desc())
    )
    items = result.scalars().all()

    if not items:
        empty_summary = {
            "total_count": 0,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "avg_change_pct": 0.0,
            "biggest_mover": None,
            "ticker_changes": [],
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "from_cache": False,
            "cache_expires_in": SUMMARY_CACHE_TTL
        }
        return empty_summary

    # Enrich tickers with price data
    enriched_stocks = await _enrich_watchlist_tickers(db, items)

    up_count = 0
    down_count = 0
    flat_count = 0
    total_change = 0.0
    valid_stocks_count = 0

    ticker_changes = []
    biggest_mover = None
    max_abs_move = -1.0

    for s in enriched_stocks:
        change_pct = s.get("change_pct", 0.0) or 0.0
        price = s.get("price", 0.0) or 0.0
        sym = s.get("ticker", "")
        currency = s.get("currency", "TRY" if s.get("market") == "BIST100" else "USD")

        if change_pct > 0.0:
            up_count += 1
        elif change_pct < 0.0:
            down_count += 1
        else:
            flat_count += 1

        total_change += change_pct
        valid_stocks_count += 1

        ticker_changes.append({
            "symbol": sym,
            "name": s.get("name", sym),
            "price": price,
            "change_pct": change_pct,
            "currency": currency,
            "market": s.get("market", "BIST100")
        })

        # Track single biggest mover (positive or negative)
        abs_move = abs(change_pct)
        if abs_move > max_abs_move:
            max_abs_move = abs_move
            biggest_mover = {
                "symbol": sym,
                "name": s.get("name", sym),
                "price": price,
                "change_pct": change_pct,
                "currency": currency,
                "direction": "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat"),
                "market": s.get("market", "BIST100")
            }

    avg_change = round(total_change / valid_stocks_count, 2) if valid_stocks_count > 0 else 0.0

    summary_data = {
        "total_count": len(enriched_stocks),
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "avg_change_pct": avg_change,
        "biggest_mover": biggest_mover,
        "ticker_changes": ticker_changes,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "cache_expires_in": SUMMARY_CACHE_TTL
    }

    # Store in cache, unless the watchlist changed while this summary was computed
    if _summary_generation.get(user_id, 0) == generation:
        _summary_cache[user_id] = {
            "data": summary_data,
            "cached_at": now_ts
        }

    return summary_data
