import logging
from typing import Optional

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

PERIOD_MAP = {
    "1d": ("5d", "15m"),
    "1w": ("5d", "15m"),
    "1mo": ("1mo", "1d"),
    "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
}


def fetch_global_stock(symbol: str) -> Optional[dict]:
    """Fetch global/US stock data using yfinance. No suffix needed for US stocks."""
    try:
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info

        price = float(fi.last_price) if fi.last_price else 0.0
        prev_close = float(fi.previous_close) if fi.previous_close else 0.0
        day_high = float(fi.day_high) if fi.day_high else 0.0
        day_low = float(fi.day_low) if fi.day_low else 0.0
        open_price = float(fi.open) if fi.open else 0.0
        volume = float(fi.last_volume) if fi.last_volume else 0.0
        market_cap = float(fi.market_cap) if fi.market_cap else 0.0
        fifty_day_avg = float(fi.fifty_day_average) if fi.fifty_day_average else 0.0

        change_pct = 0.0
        if prev_close and prev_close > 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        # Try to get human-readable name
        name = symbol
        try:
            info = ticker.info
            name = info.get("shortName") or info.get("longName") or name
        except Exception:
            pass

        # Attempt bid/ask
        bid = 0.0
        ask = 0.0
        try:
            if "info" not in dir() or info is None:
                info = ticker.info
            bid = float(info.get("bid", 0) or 0)
            ask = float(info.get("ask", 0) or 0)
        except Exception:
            pass

        # Detect currency from info
        currency = "USD"
        try:
            if "info" not in dir() or info is None:
                info = ticker.info
            currency = info.get("currency", "USD") or "USD"
        except Exception:
            pass

        return {
            "symbol": symbol,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "volume": volume,
            "day_high": day_high,
            "day_low": day_low,
            "open": open_price,
            "previous_close": prev_close,
            "bid": bid,
            "ask": ask,
            "market_cap": market_cap,
            "fifty_day_average": fifty_day_avg,
            "currency": currency,
            "market_type": "GLOBAL",
        }
    except Exception as e:
        logger.error("Failed to fetch global stock %s via yfinance: %s", symbol, e)
        return None


def fetch_global_stock_finnhub(symbol: str, api_key: str) -> Optional[dict]:
    """Fallback: fetch stock quote from Finnhub API."""
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"

        with httpx.Client(timeout=15) as client:
            resp = client.get(url)
            resp.raise_for_status()

        data = resp.json()

        if not data or data.get("c") is None or data.get("c") == 0:
            logger.warning("Finnhub returned empty data for %s", symbol)
            return None

        price = float(data.get("c", 0))
        prev_close = float(data.get("pc", 0))
        day_high = float(data.get("h", 0))
        day_low = float(data.get("l", 0))
        open_price = float(data.get("o", 0))

        change_pct = 0.0
        if prev_close and prev_close > 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        return {
            "symbol": symbol,
            "name": symbol,
            "price": price,
            "change_pct": change_pct,
            "volume": 0.0,
            "day_high": day_high,
            "day_low": day_low,
            "open": open_price,
            "previous_close": prev_close,
            "bid": 0.0,
            "ask": 0.0,
            "market_cap": 0.0,
            "fifty_day_average": 0.0,
            "currency": "USD",
            "market_type": "GLOBAL",
        }
    except Exception as e:
        logger.error("Failed to fetch global stock %s via Finnhub: %s", symbol, e)
        return None


def _fetch_yahoo_chart_global(symbol: str, yf_period: str, yf_interval: str):
    """Direct Yahoo Finance chart API via httpx — avoids yfinance .history() cloud blocks."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": "0",
        "period2": "9999999999",
        "interval": yf_interval,
        "range": yf_period,
        "includePrePost": "false",
        "events": "div,splits",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://finance.yahoo.com/",
        "Origin": "https://finance.yahoo.com",
    }
    try:
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
        chart = body.get("chart", {})
        result = chart.get("result", [])
        if not result:
            return None
        r = result[0]
        timestamps = r.get("timestamp", [])
        quote = r.get("indicators", {}).get("quote", [{}])[0]
        opens   = quote.get("open",   [])
        highs   = quote.get("high",   [])
        lows    = quote.get("low",    [])
        closes  = quote.get("close",  [])
        volumes = quote.get("volume", [])
        from datetime import datetime as _dt
        rows = []
        for i, ts in enumerate(timestamps):
            c = closes[i] if i < len(closes) else None
            if c is None:
                continue
            rows.append({
                "time":   _dt.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "open":   round(float(opens[i])   if i < len(opens)   and opens[i]   else c, 4),
                "high":   round(float(highs[i])   if i < len(highs)   and highs[i]   else c, 4),
                "low":    round(float(lows[i])    if i < len(lows)    and lows[i]    else c, 4),
                "close":  round(float(c), 4),
                "volume": int(volumes[i]) if i < len(volumes) and volumes[i] else 0,
            })
        return rows if rows else None
    except Exception as e:
        logger.warning("Direct Yahoo chart API failed for %s: %s", symbol, e)
        return None


def fetch_global_history(symbol: str, period: str = "1mo") -> Optional[list]:
    """Fetch historical OHLCV data for a global stock."""
    try:
        yf_period, yf_interval = PERIOD_MAP.get(period, ("1mo", "1d"))

        # Try direct Yahoo Finance API first (more reliable on cloud servers)
        rows = _fetch_yahoo_chart_global(symbol, yf_period, yf_interval)
        if rows:
            logger.info("Fetched %d history records for %s via direct API", len(rows), symbol)
            return rows

        # Fallback: yfinance .history()
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=yf_period, interval=yf_interval)
        if hist.empty:
            logger.warning("No history data for %s with period=%s", symbol, period)
            return None

        results = []
        for idx, row in hist.iterrows():
            time_str = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)
            results.append({
                "time":   time_str,
                "open":   round(float(row.get("Open",   0)), 4),
                "high":   round(float(row.get("High",   0)), 4),
                "low":    round(float(row.get("Low",    0)), 4),
                "close":  round(float(row.get("Close",  0)), 4),
                "volume": int(row.get("Volume", 0)),
            })
        logger.info("Fetched %d history records for %s via yfinance", len(results), symbol)
        return results
    except Exception as e:
        logger.error("Failed to fetch global history for %s: %s", symbol, e)
        return None


def fetch_commodity_data(symbol: str) -> Optional[dict]:
    """Fetch commodity data (GC=F, SI=F, CL=F, HG=F, etc.) using yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info

        price = float(fi.last_price) if fi.last_price else 0.0
        prev_close = float(fi.previous_close) if fi.previous_close else 0.0
        day_high = float(fi.day_high) if fi.day_high else 0.0
        day_low = float(fi.day_low) if fi.day_low else 0.0
        open_price = float(fi.open) if fi.open else 0.0
        volume = float(fi.last_volume) if fi.last_volume else 0.0

        change_pct = 0.0
        if prev_close and prev_close > 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        # Commodity display names
        commodity_names = {
            "GC=F": "Gold (XAU/USD)",
            "SI=F": "Silver (XAG/USD)",
            "CL=F": "Crude Oil (WTI)",
            "HG=F": "Copper",
            "PL=F": "Platinum",
            "PA=F": "Palladium",
            "NG=F": "Natural Gas",
            "BZ=F": "Brent Crude Oil",
        }

        name = commodity_names.get(symbol, symbol)

        # Try to get the proper name from yfinance info
        try:
            info = ticker.info
            fetched_name = info.get("shortName") or info.get("longName")
            if fetched_name:
                name = fetched_name
        except Exception:
            pass

        return {
            "symbol": symbol,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "volume": volume,
            "day_high": day_high,
            "day_low": day_low,
            "open": open_price,
            "previous_close": prev_close,
            "bid": 0.0,
            "ask": 0.0,
            "market_cap": 0.0,
            "fifty_day_average": 0.0,
            "currency": "USD",
            "market_type": "COMMODITY",
        }
    except Exception as e:
        logger.error("Failed to fetch commodity data for %s: %s", symbol, e)
        return None
