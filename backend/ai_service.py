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
        # Prepare concise market summary
        top_gainers = sorted(market_data, key=lambda x: x.get('change_pct', 0), reverse=True)[:5]
        top_losers = sorted(market_data, key=lambda x: x.get('change_pct', 0))[:5]
        
        bist_stocks = [s for s in market_data if s.get('currency') == 'TRY' or str(s.get('symbol','')).endswith('.IS')]
        global_stocks = [s for s in market_data if s.get('currency') == 'USD' and not str(s.get('symbol','')).endswith('.IS')]
        
        bist_avg = sum(s.get('change_pct', 0) for s in bist_stocks) / max(len(bist_stocks), 1)
        global_avg = sum(s.get('change_pct', 0) for s in global_stocks) / max(len(global_stocks), 1)
        
        oversold = [s for s in market_data if s.get('rsi', 50) < 30]
        overbought = [s for s in market_data if s.get('rsi', 50) > 70]
        
        prompt = f"""You are Wolfee AI 🐺, a sophisticated Turkish & Global stock market analyst. 
Generate a brief, insightful daily market brief (max 3 paragraphs, use markdown bold for emphasis).

Today's Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Market Summary:
- BIST Average Change: {bist_avg:.2f}% ({len(bist_stocks)} stocks tracked)
- Global Average Change: {global_avg:.2f}% ({len(global_stocks)} stocks tracked)

Top 5 Gainers: {json.dumps([{'s': s['symbol'], 'c': s.get('change_pct',0), 'p': s.get('price',0)} for s in top_gainers])}
Top 5 Losers: {json.dumps([{'s': s['symbol'], 'c': s.get('change_pct',0), 'p': s.get('price',0)} for s in top_losers])}
Oversold (RSI<30): {json.dumps([s['symbol'] for s in oversold[:5]])}
Overbought (RSI>70): {json.dumps([s['symbol'] for s in overbought[:5]])}

Provide:
1. A brief market overview sentence
2. Top 2-3 actionable insights or stock picks with reasoning
3. A risk warning if needed

Keep it concise, professional, and actionable. Use Turkish Lira (₺) for BIST stocks and $ for US stocks."""

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
        prompt = f"""You are Wolfee AI 🐺, a professional stock analyst.
Analyze this stock and provide a clear Buy/Hold/Sell recommendation.

Stock: {stock_data.get('name', symbol)} ({symbol})
Price: {stock_data.get('price', 0)}
Change: {stock_data.get('change_pct', 0)}%
RSI: {stock_data.get('rsi', 'N/A')}
MA(20): {stock_data.get('ma_20', 'N/A')}
Volatility: {stock_data.get('volatility', 'N/A')}
Volume: {stock_data.get('volume', 0)}
Day Range: {stock_data.get('day_low', 0)} - {stock_data.get('day_high', 0)}
Previous Close: {stock_data.get('previous_close', 0)}
Market: {'BIST (Turkish)' if str(symbol).endswith('.IS') else 'Global (US)'}

Provide:
1. **Recommendation**: Buy / Hold / Sell with confidence (High/Medium/Low)
2. **Technical Analysis**: Brief RSI and trend interpretation
3. **Key Levels**: Support and resistance estimates
4. **Risk Assessment**: What could go wrong
5. **1-Month Outlook**: Brief price direction expectation

Keep it under 200 words. Be specific with numbers."""

        response = model.generate_content(prompt)
        return response.text if response.text else _fallback_stock_analysis(symbol, stock_data)
        
    except Exception as e:
        logger.error(f"Gemini stock analysis error: {e}")
        return _fallback_stock_analysis(symbol, stock_data)

def _fallback_stock_analysis(symbol: str, stock_data: dict) -> str:
    """Template-based fallback for individual stock analysis."""
    if not stock_data:
        return "🐺 **Wolfee AI**: Data is currently missing for this asset."
    
    price = stock_data.get('price', 0)
    change = stock_data.get('change_pct', 0)
    rsi = stock_data.get('rsi', 50)
    
    analysis = f"🐺 **Wolfee AI Basic Analysis for {symbol}**:\n\n"
    
    # Trend
    if change > 2:
        analysis += f"**Trend**: Positive momentum detected (+{change}%). The asset is showing strength in the current session.\n"
    elif change < -2:
        analysis += f"**Trend**: Downward pressure observed ({change}%). Exercise caution as sellers currently dominate.\n"
    else:
        analysis += f"**Trend**: Neutral price action. The asset is consolidating around {price}.\n"
        
    # RSI
    if rsi > 70:
        analysis += f"**Momentum (RSI)**: High ({rsi:.1f}). Approaching overbought territory, suggesting limited upside in the short term without a pullback.\n"
    elif rsi < 30:
        analysis += f"**Momentum (RSI)**: Low ({rsi:.1f}). Approaching oversold territory. Watch for potential reversal or bounce opportunities.\n"
    else:
        analysis += f"**Momentum (RSI)**: Neutral ({rsi:.1f}). Neither overbought nor oversold, typical of ranging markets.\n"
        
    # Conclusion
    if change > 0 and rsi < 65:
        analysis += "\n**Recommendation**: Potential Buy. Favorable risk-reward profile."
    elif change < 0 and rsi > 50:
        analysis += "\n**Recommendation**: Hold/Sell. Trend is weakening."
    else:
        analysis += "\n**Recommendation**: Hold. Wait for clearer signals."
        
    return analysis

def _fallback_insight(market_data, opportunities=None):
    """Template-based fallback when Gemini is unavailable"""
    import random
    if not market_data:
        return "🐺 **Wolfee AI**: Market is quiet. No strong signals detected. Keeping cash ready for dips."
    
    gainers = [s for s in market_data if s.get('change_pct', 0) > 1]
    losers = [s for s in market_data if s.get('change_pct', 0) < -1]
    
    templates = [
        f"🐺 **Wolfee AI Protocol**: Tracking {len(market_data)} instruments. {len(gainers)} showing gains, {len(losers)} declining. ",
        f"🚀 **Market Scan Complete**: Analyzed {len(market_data)} stocks across BIST & Global markets. ",
        f"🤖 **Algorithmic Insight**: Processing {len(market_data)} data points for patterns. "
    ]
    
    text = random.choice(templates)
    
    if gainers:
        top = max(gainers, key=lambda x: x.get('change_pct', 0))
        text += f"Top performer: **{top['symbol'].replace('.IS', '')}** at +{top.get('change_pct',0):.1f}%. "
    
    if losers:
        worst = min(losers, key=lambda x: x.get('change_pct', 0))
        text += f"Watch out for **{worst['symbol'].replace('.IS', '')}** at {worst.get('change_pct',0):.1f}%."
    
    return text
