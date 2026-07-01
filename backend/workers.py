import asyncio
import logging
import time
from datetime import datetime
from sqlalchemy import select, delete
from database import AsyncSessionLocal
from models import StockData, TurkishGold, ExchangeRate, AIInsight

logger = logging.getLogger(__name__)

# Import will be done lazily to avoid circular imports
_refresh_running = False
_last_refresh_time = 0

async def refresh_all_data():
    """Master refresh function — called every 10 minutes or on manual refresh"""
    global _refresh_running, _last_refresh_time
    
    if _refresh_running:
        logger.info("Refresh already in progress, skipping...")
        return False
    
    _refresh_running = True
    logger.info("🔄 Starting full data refresh...")
    start_time = time.time()
    
    try:
        # Run all refreshes concurrently where possible
        results = await asyncio.gather(
            refresh_bist_stocks(),
            refresh_global_stocks(),
            refresh_commodities(),
            refresh_turkish_gold(),
            refresh_exchange_rates(),
            return_exceptions=True
        )
        
        # Log results
        labels = ['BIST', 'Global', 'Commodities', 'Gold', 'Exchange']
        for label, result in zip(labels, results):
            if isinstance(result, Exception):
                logger.error(f"{label} refresh failed: {result}")
            else:
                logger.info(f"{label} refresh: {result} items")
        
        # Refresh AI insight (depends on stock data being fresh)
        await refresh_ai_insight()
        
        elapsed = time.time() - start_time
        _last_refresh_time = time.time()
        logger.info(f"✅ Full refresh complete in {elapsed:.1f}s")
        return True
        
    except Exception as e:
        logger.error(f"Full refresh error: {e}")
        return False
    finally:
        _refresh_running = False

async def refresh_bist_stocks() -> int:
    """Refresh all BIST stocks"""
    from analysis import BIST_SYMBOLS
    from data_sources.turkish_market import fetch_bist_stock, fetch_bist_stock_fallback
    
    count = 0
    async with AsyncSessionLocal() as session:
        for symbol in BIST_SYMBOLS:
            try:
                # Try primary source
                data = await asyncio.to_thread(fetch_bist_stock, symbol)
                if not data:
                    data = await asyncio.to_thread(fetch_bist_stock_fallback, symbol)
                if not data:
                    continue
                
                # Add analysis fields
                data = _enrich_stock_data(data, market_type='BIST', currency='TRY')
                
                # Upsert to DB
                await _upsert_stock(session, data)
                count += 1
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"BIST refresh error {symbol}: {e}")
        
        await session.commit()
    return count

async def refresh_global_stocks() -> int:
    """Refresh all global stocks"""
    from analysis import GLOBAL_SYMBOLS
    from data_sources.global_market import fetch_global_stock
    
    count = 0
    async with AsyncSessionLocal() as session:
        for symbol in GLOBAL_SYMBOLS:
            try:
                data = await asyncio.to_thread(fetch_global_stock, symbol)
                if not data:
                    continue
                
                data = _enrich_stock_data(data, market_type='GLOBAL', currency=data.get('currency', 'USD') or 'USD')
                await _upsert_stock(session, data)
                count += 1
                
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"Global refresh error {symbol}: {e}")
        
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

async def refresh_ai_insight() -> bool:
    """Generate fresh AI insight"""
    try:
        # Get current stock data from DB
        async with AsyncSessionLocal() as session:
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
            await session.commit()
            
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
    
    # Prediction
    if change_pct > 5:
        prediction = f"Strong momentum with +{change_pct:.1f}% gain"
    elif change_pct > 2:
        prediction = f"Positive trend with +{change_pct:.1f}% gain"
    elif change_pct > 0:
        prediction = "Slight upward movement"
    elif change_pct < -5:
        prediction = f"Strong decline with {change_pct:.1f}% loss"
    elif change_pct < -2:
        prediction = f"Downward trend with {change_pct:.1f}% loss"
    else:
        prediction = "Stable price action"
    
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
    existing = result.scalar_one_or_none()
    
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

async def start_periodic_refresh(interval_minutes: int = 10):
    """Start the periodic refresh loop"""
    logger.info(f"Starting periodic refresh every {interval_minutes} minutes")
    
    # Initial refresh on startup
    await refresh_all_data()
    
    while True:
        await asyncio.sleep(interval_minutes * 60)
        await refresh_all_data()
