import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Body, Request
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, FileResponse
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import init_db, AsyncSessionLocal, engine, get_db
from models import StockData, TurkishGold, ExchangeRate, AIInsight, WatchlistItem
from analysis import (
    analyze_stock, get_market_opportunities, get_bulk_analysis,
    BIST_SYMBOLS, GLOBAL_SYMBOLS, COMMODITIES_SYMBOLS
)
from workers import _DB_WRITE_LOCK, refresh_all_data, start_periodic_refresh

from security_middleware import SecurityMiddleware, get_optional_user
import auth_routes
import watchlist_routes
from watchlist_routes import _enrich_watchlist_tickers
from services import ai_insight_service, insight_readiness
from services.market_display import portfolio_export_row, stock_card, unavailable_export_row

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy 3rd-party HTTP client logs to eliminate console clutter
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)

# ============================================================
# APP LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🐺 Wolfee Analytics starting up...")

    # Initialize database tables
    await init_db()
    logger.info("✅ Database initialized")

    # Start background refresh worker (30 min default, configurable via REFRESH_INTERVAL_MINUTES)
    refresh_interval = int(os.getenv("REFRESH_INTERVAL_MINUTES", "30"))
    refresh_task = asyncio.create_task(start_periodic_refresh(interval_minutes=refresh_interval))
    logger.info(f"✅ Background refresh worker started (every {refresh_interval} min, market-aware)")

    yield

    # Shutdown
    refresh_task.cancel()
    logger.info("🛑 Wolfee Analytics shutting down")


import re
from fastapi.responses import JSONResponse

# Valid stock tickers: e.g. THYAO.IS, AAPL, BRK.B, GC=F. Rejects path traversal and consecutive dots.
SYMBOL_REGEX = re.compile(r"^[A-Za-z0-9]+(?:[\.\-=][A-Za-z0-9]+)*$")

def validate_symbol_input(symbol: str) -> str:
    """Sanitize and validate stock/commodity ticker symbols against injection."""
    sym = (symbol or "").strip()
    if not sym or len(sym) > 20 or not SYMBOL_REGEX.match(sym):
        raise HTTPException(
            status_code=400,
            detail="Invalid symbol format. Symbols must be 1-20 alphanumeric characters, dots, or dashes."
        )
    return sym


app = FastAPI(title="Wolfee Analytics", lifespan=lifespan, debug=False)

# ============================================================
# GLOBAL EXCEPTION HANDLERS (Prevent stack trace / DB error leakage)
# ============================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


# ============================================================
# CORS (Strict origin allowlist - no wildcard with credentials)
# ============================================================
origins = [
    "http://localhost:8080",
    "http://localhost:8000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8000",
    "https://wolfee-backend.onrender.com",
    "https://solitary-scene-04bc.ozanggnr.workers.dev",
]

# Add Railway domain dynamically
railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if railway_domain:
    origins.append(f"https://{railway_domain}")

# Support custom allowed CORS origins from environment
custom_cors = os.getenv("CORS_ORIGINS")
if custom_cors:
    origins.extend([o.strip() for o in custom_cors.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https:\/\/.*\.up\.railway\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Register security middleware (IP rate limiting, CSRF validation, security headers)
app.add_middleware(SecurityMiddleware)

# Register Authentication and Watchlist API routers
app.include_router(auth_routes.router)
app.include_router(watchlist_routes.router)

# /api/v1 routers (API_CONTRACT §5). Imported here so they register before the static mount.
from routers import analytics as analytics_router, portfolios as portfolio_router, transactions as transaction_router
app.include_router(portfolio_router.router)
app.include_router(transaction_router.router)
app.include_router(analytics_router.router)


# ============================================================
# HEALTH & ROOT
# ============================================================

@app.get("/")
@app.head("/")
async def read_root():
    """Serve frontend index.html or API welcome"""
    index_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to Wolfee Analytics API"}


@app.get("/healthz")
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "service": "Wolfee Analytics API", "database": "connected"}
    except Exception:
        return {"status": "degraded", "service": "Wolfee Analytics API", "database": "disconnected"}


# ============================================================
# MARKET DATA ENDPOINTS (DB-first, instant response)
# ============================================================

@app.get("/api/stocks")
async def get_stocks():
    """Returns list of supported symbols."""
    return {
        "stocks": BIST_SYMBOLS + GLOBAL_SYMBOLS,
        "commodities": list(COMMODITIES_SYMBOLS.keys()),
        "bist_count": len(BIST_SYMBOLS),
        "global_count": len(GLOBAL_SYMBOLS),
        "commodity_count": len(COMMODITIES_SYMBOLS),
    }


@app.get("/api/market-data/quick")
async def get_quick_market_data(background_tasks: BackgroundTasks):
    """
    Fetch market data from PostgreSQL (instant).
    If DB is empty, triggers background refresh and returns what's available.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(StockData).order_by(StockData.market_type, StockData.symbol)
            )
            stocks = result.scalars().all()

            if not stocks:
                # DB is empty — trigger refresh and return empty
                background_tasks.add_task(_sync_refresh)
                return {"stocks": [], "status": "loading", "message": "First load — data is being fetched. Refresh in 30 seconds."}

            stock_list = _deduplicate_stocks(stocks)
            # Include the most recent update timestamp so the frontend can show data age
            latest_update = max((s.updated_at for s in stocks if s.updated_at), default=None)
            return {
                "stocks": stock_list,
                "updated_at": ai_insight_service.utc(latest_update).isoformat() if latest_update else None
            }

    except Exception as e:
        logger.error(f"Quick market data error: {e}")
        return {"stocks": [], "error": str(e)}


@app.get("/api/market-data/full")
async def get_full_market_data():
    """Returns ALL stocks from DB."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(StockData).order_by(StockData.market_type, StockData.symbol)
            )
            stocks = result.scalars().all()
            return {"stocks": _deduplicate_stocks(stocks)}
    except Exception as e:
        logger.error(f"Full market data error: {e}")
        return {"stocks": []}


@app.get("/api/market-data")
async def get_market_data(background_tasks: BackgroundTasks):
    """Legacy endpoint."""
    return await get_quick_market_data(background_tasks)


# ============================================================
# TURKISH GOLD & EXCHANGE RATES
# ============================================================

@app.get("/api/turkish-gold")
async def get_turkish_gold():
    """Returns Turkish gold prices from DB."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(TurkishGold))
            gold = result.scalars().all()
            return {
                "gold": [{
                    "gold_type": g.gold_type,
                    "display_name": g.display_name,
                    "buying_price": g.buying_price,
                    "selling_price": g.selling_price,
                    "change_pct": g.change_pct,
                    "updated_at": ai_insight_service.utc(g.updated_at).isoformat() if g.updated_at else None
                } for g in gold]
            }
    except Exception as e:
        logger.error(f"Turkish gold error: {e}")
        return {"gold": []}


@app.get("/api/exchange-rates")
async def get_exchange_rates():
    """Returns exchange rates from DB."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(ExchangeRate))
            rates = result.scalars().all()
            return {
                "rates": [{
                    "pair": r.pair,
                    "display_name": r.display_name,
                    "buying": r.buying,
                    "selling": r.selling,
                    "change_pct": r.change_pct,
                    "updated_at": ai_insight_service.utc(r.updated_at).isoformat() if r.updated_at else None
                } for r in rates]
            }
    except Exception as e:
        logger.error(f"Exchange rates error: {e}")
        return {"rates": []}


# ============================================================
# STOCK ANALYSIS & HISTORY
# ============================================================

@app.get("/api/analyze/{symbol}")
async def get_stock_analysis_endpoint(symbol: str):
    """Returns analysis for a specific stock."""
    symbol = validate_symbol_input(symbol)
    # Auto-append .IS if needed
    if "=" not in symbol and not symbol.endswith(".IS"):
        # Check if it's a global symbol
        if symbol.upper() not in [s.upper() for s in GLOBAL_SYMBOLS]:
            symbol += ".IS"

    is_commodity = "=" in symbol
    data = analyze_stock(symbol, is_commodity, detailed=True)
    if not data:
        raise HTTPException(status_code=404, detail="Stock data not found")
    return data


@app.get("/api/live-price/{symbol}")
async def get_live_price(symbol: str, background_tasks: BackgroundTasks):
    """
    Fetch a real-time price directly from yfinance (bypasses DB cache).
    Used when a user opens a stock detail modal to show the freshest possible price.
    Also queues a background DB update so the next poll sees fresh data.
    """
    symbol = validate_symbol_input(symbol)
    # Resolve symbol
    if "=" not in symbol and not symbol.endswith(".IS"):
        if symbol.upper() not in [s.upper() for s in GLOBAL_SYMBOLS]:
            symbol += ".IS"

    is_commodity = "=" in symbol

    try:
        data = analyze_stock(symbol, is_commodity, detailed=True)
        if not data:
            raise HTTPException(status_code=404, detail="Live price unavailable")

        # Queue background DB update so next poll benefits from fresh data
        async def _update_db(sym, d):
            try:
                from workers import _DB_WRITE_LOCK, _enrich_quotes, _upsert_stock
                # Re-enriched from stored history: the analyze_stock result may still carry
                # its legacy single-day estimates, which must not reach the card cache (D4).
                market_type = d.get("market_type", "GLOBAL")
                enriched = (await _enrich_quotes([dict(d)], market_type,
                                                 lambda quote: quote.get("currency") or "USD"))[0]
                async with _DB_WRITE_LOCK, AsyncSessionLocal() as sess:
                    await _upsert_stock(sess, enriched)
                    await sess.commit()
            except Exception as ex:
                logger.warning(f"Live-price DB update failed for {sym}: {ex}")

        background_tasks.add_task(_update_db, symbol, data)
        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Live price error for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Live price temporarily unavailable.")


@app.get("/api/history/{symbol}")
async def get_stock_history(symbol: str, period: str = "1y"):
    """Returns historical price data for charts."""
    symbol = validate_symbol_input(symbol)
    if period not in ["1d", "5d", "1wk", "1mo", "3mo", "6mo", "1y", "5y", "max"]:
        raise HTTPException(status_code=400, detail="Invalid period parameter.")

    is_global = symbol.upper() in [s.upper() for s in GLOBAL_SYMBOLS]
    is_commodity = "=" in symbol

    if not is_global and not is_commodity and not symbol.endswith(".IS"):
        symbol += ".IS"

    try:
        if symbol.endswith(".IS"):
            from data_sources.turkish_market import fetch_bist_history
            data = await asyncio.to_thread(fetch_bist_history, symbol, period)
        else:
            from data_sources.global_market import fetch_global_history
            data = await asyncio.to_thread(fetch_global_history, symbol, period)

        # data is a list of OHLCV dicts (not a dict with 'history' key)
        if not data:
            raise HTTPException(status_code=404, detail="No history found")

        return {
            "symbol": symbol,
            "name": symbol,
            "history": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"History error for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Historical data temporarily unavailable.")


@app.get("/api/chart/{symbol}/{period}")
async def get_chart_data(symbol: str, period: str):
    """Chart data endpoint for frontend."""
    symbol = validate_symbol_input(symbol)
    if period not in ["1d", "5d", "1wk", "1mo", "3mo", "6mo", "1y", "5y", "max"]:
        raise HTTPException(status_code=400, detail="Invalid period parameter.")

    is_global = symbol.upper() in [s.upper() for s in GLOBAL_SYMBOLS]

    if not symbol.endswith('.IS') and not is_global and "=" not in symbol:
        symbol += '.IS'

    try:
        if symbol.endswith(".IS"):
            from data_sources.turkish_market import fetch_bist_history
            data = await asyncio.to_thread(fetch_bist_history, symbol, period)
        else:
            from data_sources.global_market import fetch_global_history
            data = await asyncio.to_thread(fetch_global_history, symbol, period)

        # Last resort: one more try of the direct chart API through Agent 3's helpers, which
        # keep a missing open/high/low null (chart_row) instead of filling it with the close.
        if not data:
            if symbol.endswith(".IS"):
                from data_sources.turkish_market import PERIOD_MAP as chart_periods, _fetch_yahoo_chart as fetch_chart
            else:
                from data_sources.global_market import PERIOD_MAP as chart_periods, _fetch_yahoo_chart_global as fetch_chart
            yf_period, yf_interval = chart_periods.get(period, ("1y", "1d"))
            data = await asyncio.to_thread(fetch_chart, symbol, yf_period, yf_interval)

        if not data:
            raise HTTPException(status_code=404, detail="No chart data available")

        return {"history": data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Chart data unavailable")


# ============================================================
# OPPORTUNITIES & AI INSIGHTS
# ============================================================

@app.get("/api/opportunities")
async def get_opportunities():
    """Returns buy opportunities from DB."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(StockData))
            stocks = result.scalars().all()
            stock_list = _deduplicate_stocks(stocks)
            opps = get_market_opportunities(cached_data=stock_list)
            # Strictly deduplicate opportunities by canonical symbol
            seen_opps = set()
            unique_opps = []
            for o in (opps or []):
                sym = (o.get("symbol") or "").upper().replace(".IS", "").strip()
                if not sym or sym in seen_opps:
                    continue
                seen_opps.add(sym)
                unique_opps.append(o)
            return {"opportunities": unique_opps}
    except Exception as e:
        logger.error(f"Opportunities error: {e}")
        return {"opportunities": []}


# One on-demand insight generation at a time, so concurrent first requests make one model call.
_insight_generation_lock = asyncio.Lock()


async def _stored_insight() -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        row = await ai_insight_service.latest_with_provenance(session)
    return None if row is None else ai_insight_service.stored_response(row)


@app.get("/api/insight")
async def get_insight():
    """The newest stored insight with provenance; otherwise one generated now and stored (D5, REQ-28).

    A stored row without provenance is never served. Until both markets are cached
    (REQ-20), and on any error, the response is the guarded layer's template.
    """
    try:
        stored = await _stored_insight()
        if stored is not None:
            return stored

        async with _insight_generation_lock:
            stored = await _stored_insight()  # another request may have just generated one
            if stored is not None:
                return stored
            async with AsyncSessionLocal() as session:
                stocks = (await session.execute(select(StockData))).scalars().all()
            counts = insight_readiness.coverage((s.market_type, s.symbol) for s in stocks)
            if not insight_readiness.is_ready(counts):
                return ai_insight_service.market_placeholder(loading=True)

            response = await ai_insight_service.market_response(
                [_stock_to_dict(s) for s in stocks], ai_insight_service.oldest_quote_time(stocks))
            async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
                await ai_insight_service.store(session, response)
                await session.commit()
            return response

    except Exception:
        logger.exception("Insight error; serving the template")
        return ai_insight_service.market_placeholder()


@app.get("/api/ai/analyze/{symbol}")
async def get_ai_stock_analysis(symbol: str):
    """Guarded description of one instrument with provenance (D5, REQ-28); the template on any error."""
    symbol = validate_symbol_input(symbol)
    try:
        async with AsyncSessionLocal() as session:
            stock = (await session.execute(
                select(StockData).where(StockData.symbol == symbol))).scalar_one_or_none()

        if stock is not None:
            stock_data, inputs_as_of = _stock_to_dict(stock), ai_insight_service.utc(stock.updated_at)
        else:
            stock_data = await asyncio.to_thread(analyze_stock, symbol)
            inputs_as_of = datetime.now(timezone.utc)  # fetched just now
        if not stock_data:
            raise HTTPException(status_code=404, detail="Stock not found")

        return await ai_insight_service.stock_response(symbol, stock_data, inputs_as_of)

    except HTTPException:
        raise
    except Exception:
        logger.exception("AI analysis error for %s; serving the template", symbol)
        return ai_insight_service.stock_placeholder(symbol)


# ============================================================
# MANUAL REFRESH
# ============================================================

@app.post("/api/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """Manually trigger a full data refresh."""
    background_tasks.add_task(_sync_refresh)
    return {"status": "Refresh triggered", "message": "Data will be updated in the background."}


@app.get("/api/refresh")
async def trigger_refresh_get(background_tasks: BackgroundTasks):
    """GET version of refresh for easy browser access."""
    background_tasks.add_task(_sync_refresh)
    return {"status": "Refresh triggered"}


def _sync_refresh(force: bool = True):
    """Run async refresh in sync context (for BackgroundTasks)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(refresh_all_data(force=force))
    finally:
        loop.close()


# ============================================================
# ROUTE ALIASES (backward compatibility)
# ============================================================

@app.get("/insight")
async def get_insight_alias():
    return await get_insight()


@app.get("/opportunities")
async def get_opportunities_alias():
    return await get_opportunities()


# ============================================================
# EXCEL EXPORT
# ============================================================

@app.post("/api/export/portfolio")
async def export_portfolio_post(
    request: Request,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Export portfolio stocks to Excel using pre-fetched stock data sent from the frontend,
    or fallback to querying the authenticated user's database watchlist.
    """
    try:
        period = payload.get("period", "weekly")
        stocks = payload.get("stocks", [])  # List of stock objects from frontend cache

        if period not in ["daily", "weekly", "monthly"]:
            raise HTTPException(status_code=400, detail="Invalid period")

        # If frontend didn't pass stocks or passed an empty list, query user's watchlist from DB
        if not stocks:
            user = await get_optional_user(request, db)
            if user:
                result = await db.execute(
                    select(WatchlistItem).where(WatchlistItem.user_id == user.id)
                )
                items = result.scalars().all()
                if items:
                    stocks = await _enrich_watchlist_tickers(db, items)

        if not stocks:
            raise HTTPException(status_code=400, detail="No stock data provided and your watchlist is empty.")

        if not all(isinstance(stock, dict) for stock in stocks):
            raise HTTPException(status_code=400, detail="Each stock must be an object.")

        today = datetime.now().strftime("%Y-%m-%d")
        # Indicators may be null (D4): the export shows "Not available", never an estimate.
        results = [portfolio_export_row(stock, period, today) for stock in stocks]

        if not results:
            raise HTTPException(status_code=404, detail="No data found for provided symbols")

        return _create_excel_response(results, f"portfolio_{period}", f"Portfolio {period.capitalize()}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate portfolio export file.")


@app.get("/api/export/portfolio")
async def export_portfolio_get(symbols: str, period: str):
    """Fallback GET export for portfolio — re-fetches live data per symbol."""
    try:
        if period not in ["daily", "weekly", "monthly"]:
            raise HTTPException(status_code=400, detail="Invalid period. Use daily, weekly, or monthly.")

        raw_list = [s.strip() for s in symbols.split(',') if s.strip()]
        if not raw_list:
            raise HTTPException(status_code=400, detail="No symbols provided.")
        if len(raw_list) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 symbols allowed per export.")

        symbol_list = [validate_symbol_input(s) for s in raw_list]

        results = []
        today = datetime.now().strftime("%Y-%m-%d")

        for symbol in symbol_list:
            data = analyze_stock(symbol, is_commodity="=" in symbol)
            if data:
                results.append(portfolio_export_row(data, period, today, symbol=symbol))
            else:
                logger.warning(f"Could not fetch live data for {symbol}; exported as not available")
                results.append(unavailable_export_row(symbol, period, today))

        if not results:
            raise HTTPException(status_code=404, detail="No symbols provided")

        return _create_excel_response(results, f"portfolio_{period}", f"Portfolio {period.capitalize()}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate portfolio export file.")


@app.get("/api/export/{period}")
async def export_analysis(period: str):
    """Generate professional Excel export."""
    if period not in ["daily", "weekly", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period. Use daily, weekly, or monthly.")

    data = get_bulk_analysis(period)
    if not data:
        raise HTTPException(status_code=404, detail="No data available for export.")

    return _create_excel_response(data, f"wolfee_market_{period}", period.capitalize())

def _create_excel_response(data: list, filename: str, sheet_name: str) -> Response:
    """Create a professionally formatted Excel file."""
    import io
    import pandas as pd
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side, numbers

    df = pd.DataFrame(data)

    columns_order = [
        "Symbol", "Currency", "Name", "Report Period", "Analysis Date", "Trend",
        "Current Price", "Start Price", "Change %", "Change Amt",
        "Period High", "High Date", "Period Low", "Low Date",
        "RSI (14)", "RSI Status", "Volatility %", "MA(20)", "Volume (Period)"
    ]

    for col in columns_order:
        if col not in df.columns:
            df[col] = ""

    df = df.reindex(columns=columns_order)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        ws = writer.sheets[sheet_name]

        # Styles
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left = Alignment(horizontal='left', vertical='center')
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
        alt_fill = PatternFill(start_color="F0F4F8", end_color="F0F4F8", fill_type="solid")
        gain_font = Font(color="157A3B", bold=True)
        loss_font = Font(color="C0392B", bold=True)
        thin_border = Border(
            left=Side(style='thin', color='D0D5DD'),
            right=Side(style='thin', color='D0D5DD'),
            top=Side(style='thin', color='D0D5DD'),
            bottom=Side(style='thin', color='D0D5DD')
        )
        number_format_price = '#,##0.00'
        number_format_pct = '0.00"%"'
        number_format_int = '#,##0'

        # Format header row
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = thin_border

        # Format data rows
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
            fill = alt_fill if row_idx % 2 == 0 else PatternFill()

            for col_idx, cell in enumerate(row, start=1):
                cell.alignment = center
                cell.border = thin_border
                if fill.fgColor and fill.fgColor.rgb != '00000000':
                    cell.fill = fill

                col_name = columns_order[col_idx - 1] if col_idx <= len(columns_order) else ""

                # Number formatting
                if col_name in ["Current Price", "Start Price", "Change Amt", "Period High", "Period Low", "MA(20)"]:
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = number_format_price

                elif col_name == "Change %":
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = '0.00'
                        if cell.value > 0:
                            cell.font = gain_font
                        elif cell.value < 0:
                            cell.font = loss_font

                elif col_name == "Volume (Period)":
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = number_format_int

                elif col_name == "RSI (14)":
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = '0.00'

                # Name column left-aligned
                if col_name in ["Name", "Symbol"]:
                    cell.alignment = left

                # Trend column coloring
                if col_name == "Trend":
                    val = str(cell.value or "")
                    if "UP" in val:
                        cell.font = gain_font
                    elif "DOWN" in val:
                        cell.font = loss_font

                # RSI Status coloring
                if col_name == "RSI Status":
                    val = str(cell.value or "")
                    if "Overbought" in val:
                        cell.font = loss_font
                    elif "Oversold" in val:
                        cell.font = gain_font

        # Auto-fit column widths
        for col_idx, column_cells in enumerate(ws.columns, start=1):
            max_length = 0
            for cell in column_cells:
                try:
                    cell_len = len(str(cell.value or ""))
                    if cell_len > max_length:
                        max_length = cell_len
                except:
                    pass
            from openpyxl.utils import get_column_letter
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = min(max(max_length + 3, 10), 30)

        # Freeze top row
        ws.freeze_panes = 'A2'

        # Add auto-filter
        ws.auto_filter.ref = ws.dimensions

    output.seek(0)

    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}.xlsx"
        }
    )


# ============================================================
# STATIC FILE SERVING (Frontend)
# ============================================================

# Mount static files LAST so API routes take priority
frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


# ============================================================
# HELPERS
# ============================================================

# The card dict lives in services.market_display so the workers' AI insight uses the
# same rows as the routes.
_stock_to_dict = stock_card


def _deduplicate_stocks(stocks: list[StockData]) -> list[dict]:
    """Strictly deduplicate stocks by canonical symbol to eliminate duplicate cards."""
    seen = set()
    result = []
    for s in stocks:
        if not s.price or s.price <= 0:
            continue
        key = (s.symbol or "").upper().replace(".IS", "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(_stock_to_dict(s))
    return result

