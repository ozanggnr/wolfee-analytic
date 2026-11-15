import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from quant.signals import enrich_quote
# The symbol lists now live in quant.universe; re-exported for existing importers.
from quant.universe import BIST_SYMBOLS, COMMODITIES_SYMBOLS, GLOBAL_SYMBOLS  # noqa: F401

logger = logging.getLogger(__name__)


# ============================================================
# TECHNICAL ANALYSIS FUNCTIONS (preserved)
# ============================================================

def calculate_rsi(series, period=14):
    """Calculate RSI (Relative Strength Index)"""
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_indicators(df: pd.DataFrame):
    """Calculate technical indicators on a DataFrame"""
    if df is None or df.empty:
        return None

    df['MA_5'] = df['Close'].rolling(window=5).mean()
    df['MA_10'] = df['Close'].rolling(window=10).mean()
    df['MA_20'] = df['Close'].rolling(window=20).mean()
    df['MA_50'] = df['Close'].rolling(window=50).mean()

    df['Returns'] = df['Close'].pct_change()
    df['Volatility'] = df['Returns'].rolling(window=20).std() * np.sqrt(252) * 100

    df['RSI'] = calculate_rsi(df['Close'])

    df['High_6Mo'] = df['Close'].rolling(window=126).max()

    df.dropna(inplace=True)
    return df


def analyze_stock(symbol: str, is_commodity=False, detailed=False, history=None):
    """
    Fetch and analyze stock data using data_sources.

    ``history`` is the instrument's real daily closes
    (``Sequence[quant.types.DailyClose]``). rsi, ma_20, volatility and the
    labels built on them come from it, and are None where it is missing or too
    short. A day high or low the provider did not supply is None. Nothing is
    estimated (decision D4). ``indicators_as_of`` is set only when at least one
    indicator could be computed.
    """
    try:
        data = None

        # Determine source
        if is_commodity or "=" in symbol:
            from data_sources.global_market import fetch_commodity_data
            data = fetch_commodity_data(symbol)
            if data:
                data['name'] = COMMODITIES_SYMBOLS.get(symbol, data.get('name', symbol))
        elif symbol.endswith('.IS'):
            from data_sources.turkish_market import fetch_bist_stock, fetch_bist_stock_fallback
            data = fetch_bist_stock(symbol)
            if not data:
                data = fetch_bist_stock_fallback(symbol)
        else:
            from data_sources.global_market import fetch_global_stock
            data = fetch_global_stock(symbol)

        if not data:
            logger.warning(f"No data available for {symbol}")
            return None

        # Enrich with analysis
        price = data.get('price', 0)
        change_pct = data.get('change_pct', 0)
        prev_close = data.get('previous_close', 0)

        # Currency — use actual currency from data source (yfinance reports EUR for European stocks, etc.)
        if symbol.endswith('.IS'):
            currency = "TRY"
        else:
            currency = data.get('currency', 'USD') or 'USD'

        market_type = "COMMODITY" if is_commodity or "=" in symbol else ("BIST" if symbol.endswith('.IS') else "GLOBAL")

        # Indicators and the labels built on them — one shared copy in quant.signals.
        # They come from real daily closes or are None; the day range is never estimated.
        enriched = enrich_quote(
            {
                "price": price,
                "change_pct": change_pct,
                "day_high": data.get('day_high', 0) or data.get('high', 0),
                "day_low": data.get('day_low', 0) or data.get('low', 0),
            },
            market_type,
            currency,
            history,
        )
        day_high = enriched["day_high"]
        day_low = enriched["day_low"]
        open_price = data.get('open', 0) or data.get('open_price', 0)
        volume = data.get('volume', 0)

        result = {
            "symbol": symbol,
            "name": data.get('name', symbol.replace('.IS', '')),
            "price": round(price, 2) if price else 0,
            "change_pct": round(change_pct, 2),
            "currency": currency,
            "market_cap": data.get('market_cap', 0),
            "volume": int(volume) if volume else 0,
            "day_high": round(day_high, 2) if day_high else None,
            "day_low": round(day_low, 2) if day_low else None,
            # None when the provider gave none: they are never derived from each other
            # or from the day's change.
            "open": round(open_price, 2) if open_price else None,
            "previous_close": round(prev_close, 2) if prev_close else None,
            "bid": data.get('bid', 0),
            "ask": data.get('ask', 0),
            "rsi": enriched["rsi"],
            "ma_20": enriched["ma_20"],
            "prediction": enriched["prediction"],
            "reason": enriched["reason"],
            "buy_signals": [],
            "is_favorable": enriched["is_favorable"],
            "is_buyable": enriched["is_buyable"],
            "volatility": enriched["volatility"],
            "volatility_pct": enriched["volatility_pct"],
            "indicators_as_of": enriched["indicators_as_of"],
            "indicator_method": enriched["indicator_method"],
            "market_type": market_type,
        }

        return result

    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return None


def _number_or_none(value):
    """``value`` as a float, or None when it is missing, NaN or infinite."""
    if value is None or pd.isna(value) or np.isinf(value):
        return None
    return float(value)


def _round_or_none(value):
    return None if value is None else round(value, 2)


def get_market_opportunities(cached_data=None):
    """Scan for buy signals from cached data or fetch fresh."""
    opportunities = []

    if not cached_data:
        limit_scan = BIST_SYMBOLS[:5] + GLOBAL_SYMBOLS[:5]
        for symbol in limit_scan:
            data = analyze_stock(symbol, is_commodity=False)
            if data:
                opportunities.append(data)
    else:
        for stock in cached_data:
            if isinstance(stock, dict):
                if stock.get('is_favorable', False) and stock.get('change_pct', 0) > 0.5:
                    if not stock.get('reason'):
                        stock['reason'] = stock.get('prediction', 'Positive Trend')
                    opportunities.append(stock)

    opportunities.sort(key=lambda x: (
        x.get('currency', '') == 'TRY' or x.get('market_type', '') == 'BIST' or str(x.get('symbol', '')).endswith('.IS'),
        x.get('change_pct', 0)
    ), reverse=True)
    return opportunities[:15]


def get_bulk_analysis(period: str):
    """
    Bulk analysis for Excel export.
    Uses yfinance for detailed historical data.
    Period: 'daily', 'weekly', 'monthly'
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return []

    fetch_period = "6mo"

    days_back = 1
    if period == "daily":
        days_back = 1
    elif period == "weekly":
        days_back = 5
    elif period == "monthly":
        days_back = 22
    else:
        return []

    results = []
    all_symbols = list(BIST_SYMBOLS[:50]) + list(GLOBAL_SYMBOLS[:50]) + list(COMMODITIES_SYMBOLS.keys())

    for symbol in all_symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=fetch_period)

            if hist.empty or len(hist) < 30:
                continue

            # Detect actual currency (EUR for European stocks, GBP for UK, etc.)
            bulk_currency = "TRY" if symbol.endswith('.IS') else "USD"
            try:
                info = ticker.info
                bulk_currency = info.get("currency", bulk_currency) or bulk_currency
            except Exception:
                pass

            df = hist.copy()
            df['MA_5'] = df['Close'].rolling(window=5).mean()
            df['MA_20'] = df['Close'].rolling(window=20).mean()

            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            df['Returns'] = df['Close'].pct_change()
            df['Volatility'] = df['Returns'].rolling(window=20).std() * np.sqrt(252) * 100

            current_row = df.iloc[-1]
            current_close = current_row['Close']
            current_date = df.index[-1].strftime("%Y-%m-%d")

            lookback_idx = -1 - days_back
            if abs(lookback_idx) > len(df):
                lookback_idx = 0

            past_row = df.iloc[lookback_idx]
            past_close = past_row['Close']

            period_slice = df.iloc[lookback_idx:]
            period_high = period_slice['High'].max()
            period_low = period_slice['Low'].min()
            period_high_date = period_slice['High'].idxmax().strftime("%Y-%m-%d")
            period_low_date = period_slice['Low'].idxmin().strftime("%Y-%m-%d")

            change_amt = current_close - past_close
            change_pct = (change_amt / past_close) * 100

            trend_icon = "➖"
            if change_pct > 0:
                trend_icon = "📈 UP"
            elif change_pct < 0:
                trend_icon = "📉 DOWN"

            # A figure that cannot be computed is left empty in the export, never filled in (D4).
            rsi_val = _number_or_none(current_row.get('RSI'))
            if rsi_val is None:
                rsi_status = "Not available"
            elif rsi_val > 70:
                rsi_status = "Overbought"
            elif rsi_val < 30:
                rsi_status = "Oversold"
            else:
                rsi_status = "Neutral"

            vol_val = _number_or_none(current_row.get('Volatility'))
            ma20_val = _number_or_none(current_row.get('MA_20'))

            name = COMMODITIES_SYMBOLS.get(symbol, symbol)

            results.append({
                "Symbol": symbol,
                "Name": name,
                "Currency": bulk_currency,
                "Report Period": period.capitalize(),
                "Analysis Date": current_date,
                "Trend": trend_icon,
                "Current Price": round(current_close, 2),
                "Start Price": round(past_close, 2),
                "Change %": round(change_pct, 2),
                "Change Amt": round(change_amt, 2),
                "Period High": round(period_high, 2),
                "High Date": period_high_date,
                "Period Low": round(period_low, 2),
                "Low Date": period_low_date,
                "RSI (14)": _round_or_none(rsi_val),
                "RSI Status": rsi_status,
                "Volatility %": _round_or_none(vol_val),
                "MA(20)": _round_or_none(ma20_val),
                "Volume (Period)": int(period_slice['Volume'].sum())
            })

        except Exception as e:
            continue

    return results
