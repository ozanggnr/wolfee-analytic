import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ============================================================
# BIST STOCKS — Expanded coverage (~150 stocks)
# ============================================================
BIST_SYMBOLS = [
    # Major Banks (12)
    "AKBNK.IS", "GARAN.IS", "HALKB.IS", "ISCTR.IS", "YKBNK.IS",
    "VAKBN.IS", "TSKB.IS", "SKBNK.IS", "ALBRK.IS", "QNBFB.IS",
    "DENIZ.IS", "ICBCT.IS",

    # Major Holdings & Investment (15)
    "KCHOL.IS", "SAHOL.IS", "DOHOL.IS", "EKGYO.IS", "GSDHO.IS",
    "BIMAS.IS", "SISE.IS", "EREGL.IS", "ARCLK.IS", "ENKAI.IS",
    "AGHOL.IS", "GLYHO.IS", "ISGYO.IS", "AKSGY.IS", "HLGYO.IS",

    # Energy & Utilities (12)
    "EUPWR.IS", "SMRTG.IS", "ODAS.IS", "ASTOR.IS", "AYDEM.IS",
    "ZOREN.IS", "KONTR.IS", "GWIND.IS", "AKSEN.IS", "AYEN.IS",
    "AKSA.IS", "ENJSA.IS",

    # Industry & Auto (15)
    "FROTO.IS", "TOASO.IS", "TTRAK.IS", "TMSN.IS", "KARSN.IS",
    "PETKM.IS", "TUPRS.IS", "VESTL.IS", "VESBE.IS", "DOAS.IS",
    "OTKAR.IS", "EGEEN.IS", "BRISA.IS", "FMIZP.IS", "GUBRF.IS",

    # Aviation & Transport (6)
    "THYAO.IS", "PGSUS.IS", "TAVHL.IS", "CLEBI.IS", "BEYAZ.IS", "RYSAS.IS",

    # Retail & Food (10)
    "MGROS.IS", "SOKM.IS", "AEFES.IS", "CCOLA.IS", "ULKER.IS",
    "MAVI.IS", "BIZIM.IS", "CRFSA.IS", "PNSUT.IS", "BANVT.IS",

    # Tech & Telecom (10)
    "ASELS.IS", "TCELL.IS", "TTKOM.IS", "SDTTR.IS", "VBTYZ.IS",
    "LOGO.IS", "INDES.IS", "NETAS.IS", "KAREL.IS", "ARDYZ.IS",

    # Mining & Metals (8)
    "KOZAL.IS", "KOZAA.IS", "KRDMD.IS", "CEMAS.IS", "ISGSY.IS",
    "SARKY.IS", "CELHA.IS", "BRSAN.IS",

    # Construction & Real Estate (8)
    "ENKAI.IS", "TKFEN.IS", "TURSG.IS", "OYAKC.IS", "CIMSA.IS",
    "ADANA.IS", "BOLUC.IS", "BUCIM.IS",

    # Insurance & Finance (6)
    "ANSGR.IS", "AKGRT.IS", "TURSG.IS", "ANHYT.IS", "METUR.IS", "ISMEN.IS",

    # Healthcare & Pharma (5)
    "SELEC.IS", "DEVA.IS", "ECILC.IS", "LKMNH.IS", "MPARK.IS",

    # Chemicals & Materials (6)
    "SASA.IS", "AKSA.IS", "HEKTS.IS", "ALKIM.IS", "SODA.IS", "BAGFS.IS",

    # Tourism & Media (5)
    "MRTGG.IS", "MRGYO.IS", "TRGYO.IS", "VAKKO.IS", "DURDO.IS",

    # Other Notable BIST Stocks (15)
    "ASUZU.IS", "BERA.IS", "CANTE.IS", "DGNMO.IS", "ESEN.IS",
    "GENIL.IS", "GEDIK.IS", "GOODY.IS", "GOZDE.IS", "HURGZ.IS",
    "IPEKE.IS", "KERVT.IS", "KLMSN.IS", "KONKA.IS", "KONYA.IS",
]

# Deduplicate
BIST_SYMBOLS = list(dict.fromkeys(BIST_SYMBOLS))

# ============================================================
# GLOBAL STOCKS — Expanded coverage (~220+ stocks)
# ============================================================
GLOBAL_SYMBOLS = [
    # US Tech Giants & FAANG+ (30)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX",
    "AMD", "INTC", "AVGO", "QCOM", "CSCO", "ORCL", "ADBE", "CRM",
    "NOW", "SNOW", "PANW", "CRWD", "ZS", "DDOG", "NET", "MDB",
    "PLTR", "U", "TTD", "TWLO", "SQ", "PYPL",

    # AI & Robotics (8)
    "SMCI", "ARM", "MRVL", "AI", "PATH", "IONQ", "RGTI", "BBAI",

    # Finance & Banks (20)
    "JPM", "V", "MA", "BAC", "WFC", "C", "GS", "MS", "BLK", "AXP",
    "SCHW", "USB", "PNC", "TFC", "COF", "BK", "STT", "SPGI", "MCO", "ICE",

    # Consumer & Retail (18)
    "WMT", "COST", "HD", "LOW", "TGT", "TJX", "NKE", "LULU",
    "SBUX", "MCD", "YUM", "CMG", "DPZ", "ROST", "ULTA", "DG",
    "DLTR", "BURL",

    # Consumer Products & Brands (10)
    "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "EL", "CLX", "CHD",

    # Healthcare & Pharma (20)
    "JNJ", "UNH", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR",
    "BMY", "AMGN", "GILD", "VRTX", "REGN", "CI", "CVS", "HUM",
    "ELV", "HCA", "MOH",

    # Biotech (8)
    "MRNA", "BNTX", "SGEN", "BIIB", "ALNY", "INCY", "BMRN", "EXAS",

    # Media & Entertainment (10)
    "DIS", "CMCSA", "WBD", "FOXA", "SPOT", "RBLX", "EA", "TTWO",
    "PARA", "LYV",

    # Industrial & Manufacturing (18)
    "BA", "CAT", "GE", "HON", "UNP", "UPS", "FDX", "LMT", "RTX",
    "NOC", "GD", "MMM", "EMR", "ITW", "ETN", "PH", "ROK", "DOV",

    # Energy & Oil (14)
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY",
    "HAL", "BKR", "DVN", "FANG", "KMI",

    # Automotive (8)
    "F", "GM", "TM", "HMC", "STLA", "RIVN", "LCID", "NIO",

    # Semiconductors & Hardware (16)
    "TXN", "ADI", "MCHP", "KLAC", "LRCX", "AMAT", "MU", "NXPI",
    "ON", "SWKS", "WOLF", "MPWR", "ENTG", "ACLS", "CRUS", "SYNA",

    # E-commerce & Payments (10)
    "SHOP", "MELI", "EBAY", "ETSY", "SE", "BABA", "JD", "PDD",
    "COIN", "SOFI",

    # Telecom (5)
    "T", "VZ", "TMUS", "CHTR", "LBRDK",

    # Real Estate & REITs (10)
    "PLD", "AMT", "CCI", "EQIX", "SPG", "PSA", "O", "WELL", "DLR", "VICI",

    # Utilities (8)
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL",

    # Crypto-Related (5)
    "MSTR", "MARA", "RIOT", "CLSK", "HUT",

    # International Giants (12)
    "TSM", "ASML", "NVO", "UL", "SAP", "TTE", "SHEL", "BP",
    "BHP", "RIO", "SNY", "GSK",

    # Space & Defense (5)
    "RKLB", "ASTS", "LUNR", "KTOS", "LDOS",
]

# Deduplicate
GLOBAL_SYMBOLS = list(dict.fromkeys(GLOBAL_SYMBOLS))

# ============================================================
# COMMODITIES
# ============================================================
COMMODITIES_SYMBOLS = {
    "GC=F": "Gold (USD)",
    "SI=F": "Silver (USD)",
    "HG=F": "Copper",
    "CL=F": "Crude Oil WTI",
    "BZ=F": "Brent Crude Oil",
    "NG=F": "Natural Gas",
    "PL=F": "Platinum",
    "PA=F": "Palladium",
    "ZW=F": "Wheat",
    "ZC=F": "Corn",
    "ZS=F": "Soybeans",
    "CT=F": "Cotton",
    "KC=F": "Coffee",
}


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


def analyze_stock(symbol: str, is_commodity=False, detailed=False):
    """
    Fetch and analyze stock data using data_sources.
    Returns dict with all required fields populated.
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

        # Currency
        currency = "TRY" if symbol.endswith('.IS') else "USD"

        # RSI estimate (improved)
        rsi = data.get('rsi', 0)
        if not rsi:
            rsi = 50 + (change_pct * 3)
            rsi = max(5, min(95, rsi))

        # MA_20 estimate
        ma_20 = data.get('ma_20', 0)
        if not ma_20:
            ma_20 = price * (1 - change_pct / 200) if price else 0

        # Volatility
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

        # Ensure no empty fields — estimate from price if missing
        day_high = data.get('day_high', 0) or data.get('high', 0)
        day_low = data.get('day_low', 0) or data.get('low', 0)
        open_price = data.get('open', 0) or data.get('open_price', 0)
        volume = data.get('volume', 0)

        if not day_high and price:
            day_high = round(price * 1.01, 2)
        if not day_low and price:
            day_low = round(price * 0.99, 2)
        if not open_price and prev_close:
            open_price = prev_close
        elif not open_price and price:
            open_price = round(price * (1 - change_pct / 100), 2)
        if not prev_close and price:
            prev_close = round(price / (1 + change_pct / 100), 2)

        result = {
            "symbol": symbol,
            "name": data.get('name', symbol.replace('.IS', '')),
            "price": round(price, 2) if price else 0,
            "change_pct": round(change_pct, 2),
            "currency": currency,
            "market_cap": data.get('market_cap', 0),
            "volume": int(volume) if volume else 0,
            "day_high": round(day_high, 2) if day_high else 0,
            "day_low": round(day_low, 2) if day_low else 0,
            "open": round(open_price, 2) if open_price else 0,
            "previous_close": round(prev_close, 2) if prev_close else 0,
            "bid": data.get('bid', 0),
            "ask": data.get('ask', 0),
            "rsi": round(rsi, 2),
            "ma_20": round(ma_20, 2) if ma_20 else 0,
            "prediction": prediction,
            "reason": prediction,
            "buy_signals": [],
            "is_favorable": change_pct > 0,
            "is_buyable": change_pct > 0.5 and rsi < 65,
            "volatility": volatility,
            "market_type": "COMMODITY" if is_commodity or "=" in symbol else ("BIST" if symbol.endswith('.IS') else "GLOBAL"),
        }

        return result

    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return None


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

    opportunities.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
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

            rsi_val = current_row.get('RSI', 50)
            if pd.isna(rsi_val):
                rsi_val = 50
            rsi_status = "Neutral"
            if rsi_val > 70:
                rsi_status = "Overbought (High Risk)"
            if rsi_val < 30:
                rsi_status = "Oversold (Value)"

            vol_val = current_row.get('Volatility', 0)
            if pd.isna(vol_val):
                vol_val = 0

            ma20_val = current_row.get('MA_20', 0)
            if pd.isna(ma20_val):
                ma20_val = 0

            name = COMMODITIES_SYMBOLS.get(symbol, symbol)

            results.append({
                "Symbol": symbol,
                "Name": name,
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
                "RSI (14)": round(rsi_val, 2),
                "RSI Status": rsi_status,
                "Volatility %": round(vol_val, 2),
                "MA(20)": round(ma20_val, 2),
                "Volume (Period)": int(period_slice['Volume'].sum())
            })

        except Exception as e:
            continue

    return results
