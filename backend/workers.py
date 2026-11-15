import os
import asyncio
import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from sqlalchemy import select, delete, func, desc
from database import AsyncSessionLocal
from models import StockData, TurkishGold, ExchangeRate, AIInsight
from quant.signals import enrich_quote

logger = logging.getLogger(__name__)

# Import will be done lazily to avoid circular imports
_refresh_running = False
_last_refresh_time = 0

# The refreshers fetch concurrently but write one at a time. SQLite allows a single
# writer; without this, one refresher's open write transaction made the others fail
# with "database is locked" (REQ-18: exchange_rates stayed empty). Write phases are
# short and hold no network calls.
_DB_WRITE_LOCK = asyncio.Lock()
MIN_REFRESH_INTERVAL_SECONDS = 90  # Don't refresh more than once per 90s
AI_INSIGHT_CACHE_HOURS = int(os.getenv("AI_INSIGHT_CACHE_HOURS", "4"))


def is_bist_open(dt: Optional[datetime] = None) -> bool:
    """Borsa Istanbul: Monday to Friday 09:55 to 18:30 Istanbul time (UTC+3)."""
    tz = ZoneInfo("Europe/Istanbul")
    now = dt.astimezone(tz) if (dt and dt.tzinfo) else (datetime.now(tz) if not dt else dt.replace(tzinfo=tz))
    if now.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False
    t = now.time()
    return (t.hour > 9 or (t.hour == 9 and t.minute >= 55)) and (t.hour < 18 or (t.hour == 18 and t.minute <= 30))


def is_us_market_open(dt: Optional[datetime] = None) -> bool:
    """US Markets (NYSE/NASDAQ): Monday to Friday 09:25 to 16:30 US Eastern time."""
    tz = ZoneInfo("America/New_York")
    now = dt.astimezone(tz) if (dt and dt.tzinfo) else (datetime.now(tz) if not dt else dt.replace(tzinfo=tz))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (t.hour > 9 or (t.hour == 9 and t.minute >= 25)) and (t.hour < 16 or (t.hour == 16 and t.minute <= 30))


def is_commodities_open(dt: Optional[datetime] = None) -> bool:
    """Global commodities (CME/ICE): Sunday 18:00 ET to Friday 17:00 ET."""
    tz = ZoneInfo("America/New_York")
    now = dt.astimezone(tz) if (dt and dt.tzinfo) else (datetime.now(tz) if not dt else dt.replace(tzinfo=tz))
    weekday = now.weekday()
    t = now.time()
    if weekday == 5:  # Saturday
        return False
    if weekday == 6 and t.hour < 18:  # Sunday before 18:00 ET
        return False
    if weekday == 4 and (t.hour > 17 or (t.hour == 17 and t.minute > 0)):  # Friday after 17:00 ET
        return False
    return True


def is_turkish_gold_and_fx_active(dt: Optional[datetime] = None) -> bool:
    """Turkish Gold & TCMB FX: Monday to Friday 09:00 to 18:30 TRT."""
    tz = ZoneInfo("Europe/Istanbul")
    now = dt.astimezone(tz) if (dt and dt.tzinfo) else (datetime.now(tz) if not dt else dt.replace(tzinfo=tz))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return 9 <= t.hour < 19


async def refresh_all_data(force: bool = False):
    """
    Master refresh function — market-aware scheduling.
    Only refreshes active markets unless force=True or database is uninitialized.
    """
    global _refresh_running, _last_refresh_time

    if _refresh_running:
        logger.info("Refresh already in progress, skipping...")
        return False

    now = time.time()
    if not force and (now - _last_refresh_time < MIN_REFRESH_INTERVAL_SECONDS):
        logger.info(f"Refresh throttled — last refresh was {now - _last_refresh_time:.0f}s ago")
        return False

    # Check baseline data counts in DB
    async with AsyncSessionLocal() as session:
        bist_count = (await session.execute(
            select(func.count(StockData.id)).where(StockData.market_type == 'BIST')
        )).scalar() or 0
        global_count = (await session.execute(
            select(func.count(StockData.id)).where(StockData.market_type == 'GLOBAL')
        )).scalar() or 0
        comm_count = (await session.execute(
            select(func.count(StockData.id)).where(StockData.market_type == 'COMMODITY')
        )).scalar() or 0
        gold_count = (await session.execute(
            select(func.count(TurkishGold.id))
        )).scalar() or 0
        exchange_count = (await session.execute(
            select(func.count(ExchangeRate.id))
        )).scalar() or 0

    bist_active = force or is_bist_open() or bist_count == 0
    us_active = force or is_us_market_open() or global_count == 0
    comm_active = force or is_commodities_open() or comm_count == 0
    gold_active = force or is_turkish_gold_and_fx_active() or gold_count == 0
    exchange_active = force or is_turkish_gold_and_fx_active() or exchange_count == 0

    if not (bist_active or us_active or comm_active or gold_active or exchange_active):
        logger.info("⏸️ All markets closed & baseline data present — skipping background refresh.")
        return True

    _refresh_running = True
    start_time = time.time()

    tasks = []
    task_labels = []

    if bist_active:
        tasks.append(refresh_bist_stocks())
        task_labels.append('BIST')
    else:
        logger.debug("⏸️ BIST closed — skipping BIST refresh")

    if us_active:
        tasks.append(refresh_global_stocks())
        task_labels.append('Global')
    else:
        logger.debug("⏸️ US market closed — skipping Global refresh")

    if comm_active:
        tasks.append(refresh_commodities())
        task_labels.append('Commodities')

    if gold_active:
        tasks.append(refresh_turkish_gold())
        task_labels.append('Gold')

    if exchange_active:
        tasks.append(refresh_exchange_rates())
        task_labels.append('Exchange')

    logger.info(f"🔄 Starting refresh for active markets: {', '.join(task_labels)}...")

    # History before quotes, so this cycle's cards use the newest closes (REQ-10). On an
    # empty cache the quotes go first: the first year-long backfill must not hold back the
    # cards, whose indicators then fill in on the next cycle.
    history_first = bist_count > 0 and global_count > 0 and comm_count > 0
    try:
        if history_first:
            await refresh_history_for_active_markets(bist_active, us_active, comm_active)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for label, result in zip(task_labels, results):
            if isinstance(result, Exception):
                logger.error(f"{label} refresh failed: {result}")
            else:
                logger.info(f"{label} refresh: {result} items")

        if not history_first:
            await refresh_history_for_active_markets(bist_active, us_active, comm_active)

        # Refresh AI insight only if stock data was refreshed or forced
        if bist_active or us_active or force:
            await refresh_ai_insight(force=force)

        elapsed = time.time() - start_time
        _last_refresh_time = time.time()
        logger.info(f"✅ Refresh complete in {elapsed:.1f}s")
        return True
    except Exception as e:
        logger.error(f"Full refresh error: {e}")
        return False
    finally:
        _refresh_running = False

async def refresh_history_for_active_markets(bist_active: bool, us_active: bool, comm_active: bool):
    """Daily closes into price_history for the markets refreshed this cycle (REQ-26).

    A failure is logged and leaves the quote refresh untouched; indicators stay null.
    """
    from quant.symbols import EXCHANGE_BIST, EXCHANGE_COMMODITY, EXCHANGE_US
    from services.price_history_service import refresh_price_history

    exchanges = [exchange for exchange, active in
                 ((EXCHANGE_BIST, bist_active), (EXCHANGE_US, us_active), (EXCHANGE_COMMODITY, comm_active))
                 if active]
    if not exchanges:
        return None
    try:
        return await refresh_price_history(AsyncSessionLocal, _DB_WRITE_LOCK, exchanges)
    except Exception:
        logger.exception("Price history refresh failed; price_history left unchanged")
        return None


async def _enrich_quotes(quotes: list, market_type: str, currency_of) -> list:
    """Enrich raw quotes with real daily closes from price_history (REQ-10, D4).

    ``quant.signals.enrich_quote`` is the single copy of the card enrichment (H1).
    A quote without stored history, or every quote when the history read fails,
    gets ``history=None``: its indicators and labels are null, never estimated.
    """
    from services import card_history

    try:
        async with AsyncSessionLocal() as session:
            histories = await card_history.histories_for(session, market_type, [q.get('symbol') for q in quotes])
    except Exception:
        logger.exception("%s: reading price history failed; indicators stay null this cycle", market_type)
        histories = {}

    enriched = []
    for quote in quotes:
        currency = currency_of(quote)
        try:
            enriched.append(enrich_quote(quote, market_type, currency, history=histories.get(quote.get('symbol'))))
        except (ValueError, ArithmeticError):
            logger.exception("Indicators failed for %s; stored without them", quote.get('symbol'))
            enriched.append(enrich_quote(quote, market_type, currency, history=None))
    return enriched


async def refresh_bist_stocks() -> int:
    """Refresh all BIST stocks with bounded concurrency"""
    from analysis import BIST_SYMBOLS
    from data_sources.turkish_market import fetch_bist_stock, fetch_bist_stock_fallback

    sem = asyncio.Semaphore(6)

    async def fetch_one(symbol: str):
        async with sem:
            try:
                data = await asyncio.to_thread(fetch_bist_stock, symbol)
                if not data:
                    data = await asyncio.to_thread(fetch_bist_stock_fallback, symbol)
                if not data:
                    return None
                return data
            except Exception as e:
                logger.error(f"BIST refresh error {symbol}: {e}")
                return None

    tasks = [fetch_one(s) for s in BIST_SYMBOLS]
    results = await asyncio.gather(*tasks)
    valid_data = [d for d in results if d]
    valid_data = await _enrich_quotes(valid_data, 'BIST', lambda quote: 'TRY')

    count = 0
    async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
        for data in valid_data:
            try:
                await _upsert_stock(session, data)
                count += 1
            except Exception as e:
                logger.error(f"BIST upsert error {data.get('symbol')}: {e}")
        await session.commit()
    return count

async def refresh_global_stocks() -> int:
    """Refresh all global stocks with bounded concurrency"""
    from analysis import GLOBAL_SYMBOLS
    from data_sources.global_market import fetch_global_stock

    sem = asyncio.Semaphore(6)

    async def fetch_one(symbol: str):
        async with sem:
            try:
                data = await asyncio.to_thread(fetch_global_stock, symbol)
                if not data:
                    return None
                return data
            except Exception as e:
                logger.error(f"Global refresh error {symbol}: {e}")
                return None

    tasks = [fetch_one(s) for s in GLOBAL_SYMBOLS]
    results = await asyncio.gather(*tasks)
    valid_data = [d for d in results if d]
    valid_data = await _enrich_quotes(valid_data, 'GLOBAL', lambda quote: quote.get('currency') or 'USD')

    count = 0
    async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
        for data in valid_data:
            try:
                await _upsert_stock(session, data)
                count += 1
            except Exception as e:
                logger.error(f"Global upsert error {data.get('symbol')}: {e}")
        await session.commit()
    return count

async def refresh_commodities() -> int:
    """Refresh commodities"""
    from analysis import COMMODITIES_SYMBOLS
    from data_sources.global_market import fetch_commodity_data
    
    # Fetch everything first: a session left open across network calls kept a
    # write transaction open and locked SQLite for the other refreshers (REQ-18).
    fetched = []
    for symbol, name in COMMODITIES_SYMBOLS.items():
        try:
            data = await asyncio.to_thread(fetch_commodity_data, symbol)
            if not data:
                continue
            data['name'] = name
            fetched.append(data)
        except Exception as e:
            logger.error(f"Commodity refresh error {symbol}: {e}")

    fetched = await _enrich_quotes(fetched, 'COMMODITY', lambda quote: 'USD')

    count = 0
    async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
        for data in fetched:
            try:
                await _upsert_stock(session, data)
                count += 1
            except Exception as e:
                logger.error(f"Commodity upsert error {data.get('symbol')}: {e}")
        await session.commit()
    return count

async def refresh_turkish_gold() -> int:
    """Refresh Turkish gold prices"""
    from data_sources.turkish_market import fetch_turkish_gold
    
    try:
        gold_data = await asyncio.to_thread(fetch_turkish_gold)
        if not gold_data:
            return 0
        
        async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
            for item in gold_data:
                existing = await session.execute(
                    select(TurkishGold).where(TurkishGold.gold_type == item['gold_type'])
                )
                existing = existing.scalar_one_or_none()
                
                if existing:
                    existing.buying_price = item['buying_price']
                    existing.selling_price = item['selling_price']
                    existing.change_pct = item.get('change_pct')
                    existing.display_name = item['display_name']
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(TurkishGold(**item))
            
            await session.commit()
        return len(gold_data)
    except Exception as e:
        logger.error(f"Gold refresh error: {e}")
        return 0

async def refresh_exchange_rates() -> int:
    """Refresh exchange rates"""
    from data_sources.turkish_market import fetch_exchange_rates
    
    try:
        rates = await asyncio.to_thread(fetch_exchange_rates)
        if not rates:
            # Never filled in: TRY conversion reports missing_fx_rate until a fetch succeeds.
            logger.error("Exchange rate refresh: TCMB returned no rates; exchange_rates left unchanged")
            return 0
        
        async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
            for item in rates:
                existing = await session.execute(
                    select(ExchangeRate).where(ExchangeRate.pair == item['pair'])
                )
                existing = existing.scalar_one_or_none()
                
                if existing:
                    existing.buying = item['buying']
                    existing.selling = item['selling']
                    existing.change_pct = item.get('change_pct')
                    existing.display_name = item['display_name']
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(ExchangeRate(**item))
            
            await session.commit()
        return len(rates)
    except Exception:
        logger.exception("Exchange rate refresh failed; exchange_rates left unchanged")
        return 0

async def refresh_ai_insight(force: bool = False) -> bool:
    """Store a new guarded market insight with provenance, at most once per AI_INSIGHT_CACHE_HOURS.

    Only a stored row with provenance that came from the model counts as fresh: an old
    row without provenance (never served, DATABASE_CONTRACT §4.4) or a template fallback
    is replaced on the next cycle.
    """
    from services import ai_insight_service, insight_readiness
    from services.market_display import stock_card

    try:
        async with AsyncSessionLocal() as session:
            if not force:
                latest = await ai_insight_service.latest_with_provenance(session)
                if latest is not None and not latest.is_fallback:
                    age_hours = (datetime.now(timezone.utc)
                                 - ai_insight_service.utc(latest.generated_at)).total_seconds() / 3600.0
                    if age_hours < AI_INSIGHT_CACHE_HOURS:
                        logger.info(f"ℹ️ AI insight is fresh ({age_hours:.1f}h old < {AI_INSIGHT_CACHE_HOURS}h) — skipping regeneration.")
                        return True

            stocks = (await session.execute(select(StockData))).scalars().all()

        # REQ-20: never build (or store) an insight from an empty or partial cache.
        counts = insight_readiness.coverage((s.market_type, s.symbol) for s in stocks)
        if not insight_readiness.is_ready(counts):
            logger.warning("AI insight not generated: stock data incomplete (%s)",
                           insight_readiness.describe(counts))
            return False

        # No session is open during the model call (REQ-18).
        response = await ai_insight_service.market_response(
            [stock_card(s) for s in stocks], ai_insight_service.oldest_quote_time(stocks))

        async with _DB_WRITE_LOCK, AsyncSessionLocal() as session:
            await ai_insight_service.store(session, response)
            await session.commit()
        logger.info("✅ Stored AI market insight (generated_by=%s, is_fallback=%s).",
                    response["generated_by"], response["is_fallback"])
        return True
    except Exception as e:
        logger.error(f"AI insight refresh error: {e}")
        return False

# Values computed from price history, and the labels built on them (decision D4). A None
# here means "not available" and must reach the cache, replacing any earlier estimate.
_INDICATOR_FIELDS = ('day_high', 'day_low', 'rsi', 'ma_20', 'volatility', 'is_favorable', 'is_buyable',
                     'prediction', 'reason')
# Provider values that are None when not supplied (REQ-30); None replaces a stale value.
_PROVIDER_OPTIONAL_FIELDS = ('open', 'open_price', 'previous_close')
# Where the indicators came from. stock_data has no columns for these (DATABASE_CONTRACT
# §4 M4 is still open), so they live in the JSON extra_data column, replaced on every write.
_PROVENANCE_FIELDS = ('indicators_as_of', 'indicator_method', 'volatility_pct')


def _indicator_provenance(data: dict) -> dict:
    return {field: data.get(field) for field in _PROVENANCE_FIELDS}


async def _upsert_stock(session, data: dict):
    """Insert or update a stock record"""
    result = await session.execute(
        select(StockData).where(StockData.symbol == data['symbol'])
    )
    existing = result.scalars().first()
    
    if existing:
        # Only update if new price is valid (non-zero)
        if not data.get('price') or data['price'] <= 0:
            return  # Skip update with bad data
        field_map = {
            'name': 'name', 'price': 'price', 'change_pct': 'change_pct',
            'volume': 'volume', 'day_high': 'day_high', 'day_low': 'day_low',
            'open': 'open_price', 'open_price': 'open_price',
            'previous_close': 'previous_close', 'bid': 'bid', 'ask': 'ask',
            'rsi': 'rsi', 'ma_20': 'ma_20', 'volatility': 'volatility',
            'currency': 'currency', 'market_type': 'market_type',
            'prediction': 'prediction', 'reason': 'reason',
            'is_favorable': 'is_favorable', 'is_buyable': 'is_buyable',
            'market_cap': 'market_cap'
        }
        for src_key, db_key in field_map.items():
            if src_key not in data or not hasattr(existing, db_key):
                continue
            if data[src_key] is not None or src_key in _INDICATOR_FIELDS + _PROVIDER_OPTIONAL_FIELDS:
                setattr(existing, db_key, data[src_key])
        if 'indicators_as_of' in data:
            existing.extra_data = _indicator_provenance(data)
        existing.updated_at = datetime.utcnow()
    else:
        # Map field names
        stock = StockData(
            symbol=data.get('symbol'),
            name=data.get('name', data.get('symbol', '')),
            price=data.get('price', 0),
            change_pct=data.get('change_pct', 0),
            volume=data.get('volume', 0),
            day_high=data.get('day_high'),
            day_low=data.get('day_low'),
            open_price=data.get('open', data.get('open_price')),
            previous_close=data.get('previous_close'),
            bid=data.get('bid', 0),
            ask=data.get('ask', 0),
            rsi=data.get('rsi'),
            ma_20=data.get('ma_20'),
            volatility=data.get('volatility'),
            currency=data.get('currency', 'USD'),
            market_type=data.get('market_type', 'GLOBAL'),
            prediction=data.get('prediction'),
            reason=data.get('reason'),
            is_favorable=data.get('is_favorable'),
            is_buyable=data.get('is_buyable'),
            market_cap=data.get('market_cap', 0),
            extra_data=_indicator_provenance(data),
        )
        session.add(stock)

async def start_periodic_refresh(interval_minutes: int = 30):
    """Start the periodic refresh loop with intelligent market-aware scheduling"""
    interval_env = os.getenv("REFRESH_INTERVAL_MINUTES")
    if interval_env:
        try:
            interval_minutes = int(interval_env)
        except ValueError:
            pass
    logger.info(f"Starting market-aware periodic refresh (interval: {interval_minutes} min)")

    # Initial refresh on startup (loads baseline data if DB is empty)
    await refresh_all_data(force=False)

    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await refresh_all_data(force=False)
        except Exception as e:
            logger.error(f"Error in periodic refresh cycle: {e}")
