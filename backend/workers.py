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

logger = logging.getLogger(__name__)

# Import will be done lazily to avoid circular imports
_refresh_running = False
_last_refresh_time = 0
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

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for label, result in zip(task_labels, results):
            if isinstance(result, Exception):
                logger.error(f"{label} refresh failed: {result}")
            else:
                logger.info(f"{label} refresh: {result} items")

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
                return _enrich_stock_data(data, market_type='BIST', currency='TRY')
            except Exception as e:
                logger.error(f"BIST refresh error {symbol}: {e}")
                return None

    tasks = [fetch_one(s) for s in BIST_SYMBOLS]
    results = await asyncio.gather(*tasks)
    valid_data = [d for d in results if d]

    count = 0
    async with AsyncSessionLocal() as session:
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
                return _enrich_stock_data(data, market_type='GLOBAL', currency=data.get('currency', 'USD') or 'USD')
            except Exception as e:
                logger.error(f"Global refresh error {symbol}: {e}")
                return None

    tasks = [fetch_one(s) for s in GLOBAL_SYMBOLS]
    results = await asyncio.gather(*tasks)
    valid_data = [d for d in results if d]

    count = 0
    async with AsyncSessionLocal() as session:
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
    
    count = 0
    async with AsyncSessionLocal() as session:
        for symbol, name in COMMODITIES_SYMBOLS.items():
            try:
                data = await asyncio.to_thread(fetch_commodity_data, symbol)
                if not data:
                    continue
                
                data['name'] = name
                data = _enrich_stock_data(data, market_type='COMMODITY', currency='USD')
                await _upsert_stock(session, data)
                count += 1
                
            except Exception as e:
                logger.error(f"Commodity refresh error {symbol}: {e}")
        
        await session.commit()
    return count

async def refresh_turkish_gold() -> int:
    """Refresh Turkish gold prices"""
    from data_sources.turkish_market import fetch_turkish_gold
    
    try:
        gold_data = await asyncio.to_thread(fetch_turkish_gold)
        if not gold_data:
            return 0
        
        async with AsyncSessionLocal() as session:
            for item in gold_data:
                existing = await session.execute(
                    select(TurkishGold).where(TurkishGold.gold_type == item['gold_type'])
                )
                existing = existing.scalar_one_or_none()
                
                if existing:
                    existing.buying_price = item['buying_price']
                    existing.selling_price = item['selling_price']
                    existing.change_pct = item.get('change_pct', 0)
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
            return 0
        
        async with AsyncSessionLocal() as session:
            for item in rates:
                existing = await session.execute(
                    select(ExchangeRate).where(ExchangeRate.pair == item['pair'])
                )
                existing = existing.scalar_one_or_none()
                
                if existing:
                    existing.buying = item['buying']
                    existing.selling = item['selling']
                    existing.change_pct = item.get('change_pct', 0)
                    existing.display_name = item['display_name']
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(ExchangeRate(**item))
            
            await session.commit()
        return len(rates)
    except Exception as e:
        logger.error(f"Exchange rate refresh error: {e}")
        return 0

async def refresh_ai_insight(force: bool = False) -> bool:
    """Generate fresh AI insight with caching (max once per AI_INSIGHT_CACHE_HOURS, default 4h)"""
    try:
        async with AsyncSessionLocal() as session:
            # Check latest insight age
            if not force:
                latest_res = await session.execute(
                    select(AIInsight)
                    .where(AIInsight.insight_type == 'daily')
                    .order_by(desc(AIInsight.created_at))
                    .limit(1)
                )
                latest_insight = latest_res.scalar_one_or_none()
                if latest_insight and latest_insight.created_at:
                    created_at = latest_insight.created_at
                    now_utc = datetime.now(timezone.utc)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    age_hours = (now_utc - created_at).total_seconds() / 3600.0
                    if age_hours < AI_INSIGHT_CACHE_HOURS:
                        logger.info(f"ℹ️ AI insight is fresh ({age_hours:.1f}h old < {AI_INSIGHT_CACHE_HOURS}h) — skipping regeneration.")
                        return True

            # Get current stock data from DB
            result = await session.execute(select(StockData))
            stocks = result.scalars().all()

            if not stocks:
                return False

            market_data = [{
                'symbol': s.symbol,
                'name': s.name,
                'price': s.price,
                'change_pct': s.change_pct,
                'rsi': s.rsi,
                'volume': s.volume,
                'currency': s.currency,
                'volatility': s.volatility,
                'day_high': s.day_high,
                'day_low': s.day_low,
                'previous_close': s.previous_close
            } for s in stocks]

            from ai_service import get_market_insight
            insight_text = await asyncio.to_thread(get_market_insight, market_data)

            # Save to DB
            insight = AIInsight(
                insight_type='daily',
                insight_text=insight_text
            )
            session.add(insight)

            # Prune old insights beyond latest 10 to keep database compact
            subq = select(AIInsight.id).where(AIInsight.insight_type == 'daily').order_by(desc(AIInsight.created_at)).offset(10)
            old_ids = (await session.execute(subq)).scalars().all()
            if old_ids:
                await session.execute(delete(AIInsight).where(AIInsight.id.in_(old_ids)))

            await session.commit()
            logger.info("✅ Generated fresh AI market insight.")

        return True
    except Exception as e:
        logger.error(f"AI insight refresh error: {e}")
        return False

def _enrich_stock_data(data: dict, market_type: str, currency: str) -> dict:
    """Add analysis fields to raw stock data"""
    price = data.get('price', 0)
    change_pct = data.get('change_pct', 0)
    prev_close = data.get('previous_close', 0)
    
    # Calculate RSI estimate from change if not available
    rsi = data.get('rsi', 0)
    if not rsi or rsi == 0:
        rsi = 50 + (change_pct * 3)
        rsi = max(5, min(95, rsi))
    
    # MA_20 estimate
    ma_20 = data.get('ma_20', 0)
    if not ma_20 or ma_20 == 0:
        ma_20 = price * (1 - change_pct / 200) if price else 0
    
    # Volatility classification
    volatility = 'HIGH' if abs(change_pct) > 5 else 'MEDIUM' if abs(change_pct) > 2 else 'LOW'
    
    # Smart prediction label — uses both change_pct and RSI for accuracy
    if change_pct > 5 and rsi < 70:
        prediction = f"PURCHASABLE — strong momentum +{change_pct:.1f}%"
    elif change_pct > 2 and rsi < 65:
        prediction = f"PURCHASABLE — positive trend +{change_pct:.1f}%"
    elif change_pct > 0.5 and rsi < 60:
        prediction = f"PURCHASABLE — rising +{change_pct:.1f}%"
    elif rsi < 35:
        prediction = "ACCUMULATE — oversold, potential bounce"
    elif change_pct >= 0 and rsi < 55:
        prediction = "ACCUMULATE — steady upward movement"
    elif change_pct >= 0 and rsi < 65:
        prediction = "WATCH TO BUY — conditions improving"
    elif rsi > 72 and change_pct > 3:
        prediction = f"TAKE PROFITS — up {change_pct:.1f}%, overbought"
    elif rsi > 65:
        prediction = "WATCH TO BUY — slightly overbought, wait for pullback"
    elif change_pct < -2:
        prediction = f"AVOID FOR NOW — declining {change_pct:.1f}%"
    elif change_pct < 0 and rsi > 40:
        prediction = "WATCH TO BUY — minor dip, monitor closely"
    elif change_pct < 0 and rsi < 40:
        prediction = "ACCUMULATE — dip into value zone"
    else:
        prediction = "WATCH TO BUY — neutral, awaiting direction"
    
    data.update({
        'currency': currency,
        'market_type': market_type,
        'rsi': round(rsi, 2),
        'ma_20': round(ma_20, 2) if ma_20 else 0,
        'volatility': volatility,
        'prediction': prediction,
        'reason': prediction,
        'is_favorable': change_pct > 0,
        'is_buyable': change_pct > 0.5 and rsi < 65,
    })
    
    return data

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
            if src_key in data and data[src_key] is not None:
                if hasattr(existing, db_key):
                    setattr(existing, db_key, data[src_key])
        existing.updated_at = datetime.utcnow()
    else:
        # Map field names
        stock = StockData(
            symbol=data.get('symbol'),
            name=data.get('name', data.get('symbol', '')),
            price=data.get('price', 0),
            change_pct=data.get('change_pct', 0),
            volume=data.get('volume', 0),
            day_high=data.get('day_high', 0),
            day_low=data.get('day_low', 0),
            open_price=data.get('open', data.get('open_price', 0)),
            previous_close=data.get('previous_close', 0),
            bid=data.get('bid', 0),
            ask=data.get('ask', 0),
            rsi=data.get('rsi', 50),
            ma_20=data.get('ma_20', 0),
            volatility=data.get('volatility', 'LOW'),
            currency=data.get('currency', 'USD'),
            market_type=data.get('market_type', 'GLOBAL'),
            prediction=data.get('prediction', ''),
            reason=data.get('reason', ''),
            is_favorable=data.get('is_favorable', False),
            is_buyable=data.get('is_buyable', False),
            market_cap=data.get('market_cap', 0)
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
