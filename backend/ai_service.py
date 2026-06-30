import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def _get_model():
    """Get Gemini model, returns None if not configured"""
    try:
        import google.generativeai as genai
        if not GEMINI_API_KEY:
            return None
        genai.configure(api_key=GEMINI_API_KEY)
        return genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        logger.error(f"Gemini init error: {e}")
        return None

def get_market_insight(market_data: list, opportunities: list = None) -> str:
    """Generate daily market insight using Gemini AI."""
    model = _get_model()

    if not model or not market_data:
        return _fallback_insight(market_data, opportunities)

    try:
        top_gainers = sorted(market_data, key=lambda x: x.get('change_pct', 0), reverse=True)[:5]
        top_losers = sorted(market_data, key=lambda x: x.get('change_pct', 0))[:5]

        bist_stocks = [s for s in market_data if s.get('currency') == 'TRY' or str(s.get('symbol', '')).endswith('.IS')]
        global_stocks = [s for s in market_data if s.get('currency') == 'USD' and not str(s.get('symbol', '')).endswith('.IS')]

        bist_avg = sum(s.get('change_pct', 0) for s in bist_stocks) / max(len(bist_stocks), 1)
        global_avg = sum(s.get('change_pct', 0) for s in global_stocks) / max(len(global_stocks), 1)

        oversold = [s for s in market_data if s.get('rsi', 50) < 30]

        # Build readable gainer/loser summaries
        gainer_lines = "\n".join(
            f"- {s.get('name', s['symbol'])}: +{s.get('change_pct', 0):.1f}% at {s.get('price', 0):.2f}"
            for s in top_gainers
        )
        loser_lines = "\n".join(
            f"- {s.get('name', s['symbol'])}: {s.get('change_pct', 0):.1f}% at {s.get('price', 0):.2f}"
            for s in top_losers
        )
        oversold_names = ", ".join(s.get('name', s['symbol']) for s in oversold[:4]) if oversold else "None"

        prompt = f"""You are Wolfee AI, a friendly and professional stock market analyst for Turkish and global markets.

Write a short, clear daily market summary for investors. Write in plain English — no bullet points with dashes, no markdown symbols like **, no technical abbreviations.
Instead of "RSI" write "momentum indicator". Instead of "MA" write "average price trend". Keep it conversational but professional.

Date: {datetime.now().strftime('%B %d, %Y at %H:%M')}

Turkish Market (BIST) average movement today: {bist_avg:+.2f}%
Global Market (US stocks) average movement today: {global_avg:+.2f}%

Today's top gaining stocks:
{gainer_lines}

Today's biggest decliners:
{loser_lines}

Stocks that may be oversold and worth watching (momentum is low, potential bounce):
{oversold_names}

Instructions:
Write exactly 2 to 3 short paragraphs. 
First paragraph: describe how the overall market is moving today in simple terms.
Second paragraph: highlight 1 or 2 specific stocks that look interesting to buy today and clearly explain WHY — what is happening with the company, why the price moved, and why now could be a good entry point.
Third paragraph (optional): mention any caution or risk if the market looks uncertain.

Do not use abbreviations. Do not use symbols like ** or ##. Write full stock names. Speak like a trusted financial advisor explaining to a client."""

        response = model.generate_content(prompt)
        return response.text if response.text else _fallback_insight(market_data, opportunities)

    except Exception as e:
        logger.error(f"Gemini market insight error: {e}")
        return _fallback_insight(market_data, opportunities)


def get_stock_analysis(symbol: str, stock_data: dict) -> str:
    """Get deep AI analysis for a single stock"""
    model = _get_model()

    if not model or not stock_data:
        return _fallback_stock_analysis(symbol, stock_data)

    try:
        name = stock_data.get('name', symbol.replace('.IS', ''))
        price = stock_data.get('price', 0)
        change = stock_data.get('change_pct', 0)
        rsi = stock_data.get('rsi', 50)
        ma_20 = stock_data.get('ma_20', 0)
        volume = stock_data.get('volume', 0)
        day_low = stock_data.get('day_low', 0)
        day_high = stock_data.get('day_high', 0)
        prev_close = stock_data.get('previous_close', 0)
        market = 'Turkish (BIST)' if str(symbol).endswith('.IS') else 'Global (US)'
        currency = '₺' if str(symbol).endswith('.IS') else '$'

        # Interpret RSI in plain language
        if rsi > 70:
            rsi_plain = f"{rsi:.0f} — the stock has been rising strongly and may be getting expensive short-term"
        elif rsi < 30:
            rsi_plain = f"{rsi:.0f} — the stock has been sold off heavily and may be undervalued, a potential bounce opportunity"
        else:
            rsi_plain = f"{rsi:.0f} — the stock is in a balanced zone, neither overpriced nor overly cheap"

        prompt = f"""You are Wolfee AI, a professional stock analyst. Write a clear investment analysis for the following stock.

Stock: {name} (ticker: {symbol.replace('.IS', '')})
Market: {market}
Current Price: {currency}{price:.2f}
Today's Change: {change:+.2f}%
Today's Range: {currency}{day_low:.2f} — {currency}{day_high:.2f}
Previous Close: {currency}{prev_close:.2f}
20-day Average Price: {currency}{ma_20:.2f}
Momentum Indicator (RSI): {rsi_plain}
Trading Volume Today: {int(volume):,}

Write a clear analysis in plain English. Do NOT use abbreviations like RSI, MA, EMA, MACD. Do NOT use markdown formatting. Write full sentences only.

Structure your response as follows:

Decision: State clearly whether this stock is a BUY, HOLD, or SELL right now. One sentence.

Why this decision: Explain in 2-3 sentences what is happening with this stock right now. Mention the price movement, whether the stock is above or below its recent average price, and what the momentum indicator tells us in plain words.

Why someone should buy it (or why to wait): Explain specifically what makes this an opportunity or what risk exists. Mention the price level, what a good entry point looks like, or what the investor is waiting for.

Risk to watch: In 1-2 sentences, state what could go wrong — what news, market conditions, or price levels would change this recommendation.

Keep it under 200 words total. Write as if explaining to someone who is not a finance expert but wants to make a smart investment decision."""

        response = model.generate_content(prompt)
        return response.text if response.text else _fallback_stock_analysis(symbol, stock_data)

    except Exception as e:
        logger.error(f"Gemini stock analysis error: {e}")
        return _fallback_stock_analysis(symbol, stock_data)


def _fallback_stock_analysis(symbol: str, stock_data: dict) -> str:
    """Template-based fallback for individual stock analysis."""
    if not stock_data:
        return "🐺 Wolfee AI: Data is currently missing for this stock. Please try again in a moment."

    price = stock_data.get('price', 0)
    change = stock_data.get('change_pct', 0)
    rsi = stock_data.get('rsi', 50)
    ma_20 = stock_data.get('ma_20', 0)
    name = stock_data.get('name', symbol.replace('.IS', ''))
    currency = '₺' if str(symbol).endswith('.IS') else '$'

    analysis = f"🐺 Wolfee AI — {name}\n\n"

    # Decision
    if change > 2 and rsi < 65:
        decision = "BUY"
        decision_reason = f"{name} is gaining momentum today with a {change:+.1f}% increase and still has room to move higher."
    elif change < -2 and rsi > 55:
        decision = "SELL / AVOID"
        decision_reason = f"{name} is under selling pressure today, dropping {change:.1f}%. The trend is weakening."
    elif rsi < 35:
        decision = "WATCH / BUY"
        decision_reason = f"{name} has been heavily sold off recently and may be approaching a value zone worth entering."
    elif rsi > 70:
        decision = "HOLD / WAIT"
        decision_reason = f"{name} has risen significantly and may be getting expensive. Waiting for a small pullback could offer a better entry."
    else:
        decision = "HOLD"
        decision_reason = f"{name} is moving sideways without a clear direction. There is no strong reason to buy or sell right now."

    analysis += f"Decision: {decision}\n\n"
    analysis += f"What is happening: {decision_reason}\n\n"

    # Price vs average context
    if ma_20 and price:
        if price > ma_20 * 1.03:
            analysis += f"The stock is currently trading {((price/ma_20 - 1)*100):.1f}% above its 20-day average price of {currency}{ma_20:.2f}, which means it has been in a sustained uptrend recently.\n\n"
        elif price < ma_20 * 0.97:
            analysis += f"The stock is trading {((1 - price/ma_20)*100):.1f}% below its 20-day average price of {currency}{ma_20:.2f}, suggesting it has been underperforming recently and may be approaching a support level.\n\n"
        else:
            analysis += f"The stock is trading close to its 20-day average price of {currency}{ma_20:.2f}, indicating it is in a consolidation phase.\n\n"

    # Risk
    if rsi > 65:
        analysis += "Risk to watch: If the stock cannot maintain this price level, a quick pullback is possible. Consider setting a stop-loss just below today's low."
    elif rsi < 35:
        analysis += "Risk to watch: The stock may continue falling before reversing. Do not rush into a full position — consider buying in stages."
    else:
        analysis += "Risk to watch: Broader market conditions and macroeconomic news could push this stock in either direction regardless of its individual performance."

    return analysis


def _fallback_insight(market_data, opportunities=None):
    """Template-based fallback when Gemini is unavailable"""
    if not market_data:
        return "🐺 Wolfee AI: Market data is being collected. Check back in a moment for today's market summary."

    gainers = [s for s in market_data if s.get('change_pct', 0) > 1]
    losers = [s for s in market_data if s.get('change_pct', 0) < -1]

    bist = [s for s in market_data if str(s.get('symbol', '')).endswith('.IS')]
    global_s = [s for s in market_data if not str(s.get('symbol', '')).endswith('.IS')]
    bist_avg = sum(s.get('change_pct', 0) for s in bist) / max(len(bist), 1)
    global_avg = sum(s.get('change_pct', 0) for s in global_s) / max(len(global_s), 1)

    direction_bist = "gaining" if bist_avg > 0 else "declining"
    direction_global = "gaining" if global_avg > 0 else "declining"

    text = (
        f"🐺 Wolfee AI — Today's Market Overview. "
        f"The Turkish stock market (BIST) is broadly {direction_bist} with an average movement of {bist_avg:+.2f}% across {len(bist)} tracked stocks. "
        f"Global markets are {direction_global} with an average of {global_avg:+.2f}% across {len(global_s)} stocks. "
    )

    if gainers:
        top = max(gainers, key=lambda x: x.get('change_pct', 0))
        top_name = top.get('name', top['symbol'].replace('.IS', ''))
        text += (
            f"The strongest performer today is {top_name}, up {top.get('change_pct', 0):.1f}%, "
            f"which may indicate strong investor interest or a positive company development. "
        )

    if losers:
        worst = min(losers, key=lambda x: x.get('change_pct', 0))
        worst_name = worst.get('name', worst['symbol'].replace('.IS', ''))
        text += (
            f"On the downside, {worst_name} is showing weakness at {worst.get('change_pct', 0):.1f}%, "
            f"which warrants caution before entering a position."
        )

    return text
