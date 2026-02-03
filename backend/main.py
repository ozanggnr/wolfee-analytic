from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from analysis import analyze_stock, get_market_opportunities, get_bulk_analysis, BIST_SYMBOLS, GLOBAL_SYMBOLS, COMMODITIES_SYMBOLS
from ai_service import get_market_insight
from api_router import get_router

app = FastAPI(title="Wolfee Analytics")

# Enable CORS for frontend (including file:// protocol for local testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins including file://
    allow_credentials=False,  # Must be False when using allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to BIST Stock Analysis API"}

@app.get("/healthz")
@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "service": "Wolfee Analytics API"}

@app.get("/api/stocks")
def get_stocks():
    """Returns list of supported BIST, Global symbols and Commodities."""
    return {
        "stocks": BIST_SYMBOLS + GLOBAL_SYMBOLS,  # Combine both
        "commodities": list(COMMODITIES_SYMBOLS.keys())
    }

# Cache for market data (prevents re-analyzing every request)
from datetime import datetime, timedelta
import time

# Two-tier cache: quick (100 stocks) and full (all stocks)
quick_cache = {"data": None, "timestamp": None}
full_cache = {"data": None, "timestamp": None}

@app.get("/api/market-data/quick")
def get_quick_market_data():
    """
    Fetch stocks with resilient error handling.
    Only returns successfully loaded stocks.
    """
    global quick_cache
    now = time.time()
    
    # Check cache (5 min)
    if quick_cache["data"] and quick_cache["timestamp"] and (now - quick_cache["timestamp"]) < 300:
        print(f"✓ Returning cached data ({len(quick_cache['data'])} stocks)")
        return {"stocks": quick_cache["data"]}
    
    print("🚀 Fetching market data (resilient mode)...")
    results = []
    
    # Phase 1: Turkish stocks (~50 stocks)
    print(f"📊 Phase 1: Fetching {len(BIST_SYMBOLS)} Turkish stocks...")
    for symbol in BIST_SYMBOLS:
        try:
            data = analyze_stock(symbol, is_commodity=False)
            if data:  # Only add if successful
                results.append(data)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    
    print(f"✓ Turkish stocks loaded: {len(results)}")
    
    # Phase 2: Global stocks (~100 stocks for quick load)
    global_quick = GLOBAL_SYMBOLS[:100]  # First 100 for speed
    print(f"🌍 Phase 2: Fetching {len(global_quick)} Global stocks...")
    
    for symbol in global_quick:
        try:
            data = analyze_stock(symbol, is_commodity=False)
            if data:  # Only add if successful
                results.append(data)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    
    print(f"✓ Global stocks loaded: {len(results) - len([r for r in results if r['symbol'].endswith('.IS') ])}") 
    
    # Phase 3: Commodities
    print(f"💰 Phase 3: Fetching {len(COMMODITIES_SYMBOLS.keys())} Commodity ETFs...")
    for symbol in COMMODITIES_SYMBOLS.keys():
        try:
            data = analyze_stock(symbol, is_commodity=True)
            if data:  # Only add if successful
                results.append(data)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    
    quick_cache["data"] = results
    quick_cache["timestamp"] = now
    
    print(f"🎉 Complete: {len(results)} stocks loaded successfully")
    return {"stocks": results}

@app.get("/api/market-data/full")
def get_full_market_data():
    """Returns ALL stocks using multi-API intelligent rotation."""
    global full_cache
    
    # Check cache
    now = datetime.now()
    if full_cache["data"] is not None and full_cache["timestamp"]:
        if now - full_cache["timestamp"] < timedelta(minutes=5):
            print(f"Serving full batch from cache ({len(full_cache['data'])} stocks)")
            return {"stocks": full_cache["data"]}
    
    print("🚀 Loading FULL batch with multi-API rotation...")
    results = []
    
    # Get API router
    router = get_router()
    
    # All Turkish stocks
    print(f"📊 Loading {len(BIST_SYMBOLS)} Turkish stocks...")
    for symbol in BIST_SYMBOLS:
        try:
            data = analyze_stock(symbol, is_commodity=False)
            if data:
                results.append(data)
        except Exception as e:
            print(f"Error {symbol}: {e}")
    
    # All Global stocks
    print(f"🌍 Loading {len(GLOBAL_SYMBOLS)} Global stocks...")
    for symbol in GLOBAL_SYMBOLS:
        try:
            data = analyze_stock(symbol, is_commodity=False)
            if data:
                results.append(data)
        except Exception as e:
            print(f"Error {symbol}: {e}")
    
    # Commodities
    print("💰 Loading commodities...")
    for symbol in COMMODITIES_SYMBOLS.keys():
        try:
            data = analyze_stock(symbol, is_commodity=True)
            if data:
                results.append(data)
        except Exception as e:
            print(f"Error {symbol}: {e}")
    
    # Cache and return
    full_cache["data"] = results
    full_cache["timestamp"] = now
    print(f"✅ Full batch loaded: {len(results)} stocks")
    print(f"API stats: {router.get_api_stats()}")
    return {"stocks": results}

# Legacy endpoint - redirects to quick batch
@app.get("/api/market-data")
def get_market_data():
    """Legacy endpoint - returns quick batch."""
    return get_quick_market_data()



@app.get("/api/analyze/{symbol}")
def get_stock_analysis(symbol: str):
    """Returns analysis for a specific stock."""
    # Append .IS for stocks if missing, but NOT for commodities (contain =)
    if "=" not in symbol and not symbol.endswith(".IS"):
        symbol += ".IS"
        
    # Check if commodity
    is_commodity = symbol in COMMODITIES_SYMBOLS
    
    # Pass detailed=True to get Bid/Ask/etc
    data = analyze_stock(symbol, is_commodity, detailed=True)
    if not data:
        # Return empty/error structure gracefully?
        raise HTTPException(status_code=404, detail="Stock data not found")
    return data

@app.get("/api/opportunities")
def get_opportunities():
    """Returns a list of buyable stocks."""
    return {"opportunities": get_market_opportunities()}

@app.get("/api/insight")
def get_insight():
    """Returns dynamic AI insight."""
    opps = get_market_opportunities()
    return {"insight": get_market_insight(opps)}

from analysis import analyze_stock, get_market_opportunities, get_bulk_analysis, BIST_SYMBOLS, COMMODITIES_SYMBOLS, GLOBAL_SYMBOLS

# ... existing imports ...

@app.get("/api/history/{symbol}")
def get_stock_history(symbol: str, period: str = "5y"):
    """Returns closing prices for charts (1d, 1mo, 1y, 5y)."""
    # Auto-append .IS only if it's not a common suffix, not a commodity, and not in global list
    is_global = symbol in GLOBAL_SYMBOLS or symbol.upper() in GLOBAL_SYMBOLS
    is_commodity = "=" in symbol
    
    if not is_global and not is_commodity and not symbol.endswith(".IS"):
        symbol += ".IS"
        
    try:
        ticker = yf.Ticker(symbol)
        
        # Determine interval based on period
        interval = "1d"
        if period == "1d":
            interval = "15m" # Intraday for 1 day view
        elif period == "1mo":
            interval = "90m" # Granular enough for month
            
        hist = ticker.history(period=period, interval=interval)
        
        if hist.empty:
             # Fallback if 1d fails (market closed etc), try 5d
             if period == "1d":
                 hist = ticker.history(period="5d", interval="60m")
             if hist.empty:
                raise HTTPException(status_code=404, detail="No history found")
             
        # Try to get full name (might be slow, so only do it here on demand)
        full_name = symbol
        try:
            info = ticker.info
            full_name = info.get('longName') or info.get('shortName') or symbol
        except:
            pass # Fallback to symbol if info fails

        # Format for frontend
        reset_hist = hist.reset_index()
        data = []
        for _, row in reset_hist.iterrows():
            # Handle different index names (Datetime vs Date) depending on interval
            date_val = row.get('Datetime') or row.get('Date')
            
            # Format: Include time if intraday
            time_fmt = "%Y-%m-%d"
            if period == "1d" or "m" in interval:
                time_fmt = "%Y-%m-%d %H:%M"
            
            data.append({
                "time": date_val.strftime(time_fmt),
                "open": round(row['Open'], 2),
                "high": round(row['High'], 2),
                "low": round(row['Low'], 2),
                "close": round(row['Close'], 2)
            })
            
        return {
            "symbol": symbol,
            "name": full_name,
            "history": data
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

# ========== FRONTEND COMPATIBILITY FIXES ==========

# Chart endpoint (frontend calls /api/chart/{symbol}/{period})
@app.get("/api/chart/{symbol}/{period}")
def get_chart_data_frontend(symbol: str, period: str):
    """Chart data formatted for frontend Plotly"""
    try:
        period_map = {
            "1d": {"period": "1d", "interval": "1h"},
            "1mo": {"period": "1mo", "interval": "1d"},
            "1y": {"period": "1y", "interval": "1wk"},
            "5y": {"period": "5y", "interval": "1wk"}
        }
        
        params = period_map.get(period, {"period": "1y", "interval": "1wk"})
        
        # Handle Turkish stocks
        if not symbol.endswith('.IS') and symbol not in GLOBAL_SYMBOLS and "=" not in symbol:
            symbol += '.IS'
        
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=params["period"], interval=params["interval"])
        
        if hist.empty:
            raise HTTPException(status_code=404, detail="No chart data")
        
        reset_hist = hist.reset_index()
        data = []
        for _, row in reset_hist.iterrows():
            date_val = row.get('Datetime') or row.get('Date')
            time_fmt = "%Y-%m-%d %H:%M" if period == "1d" else "%Y-%m-%d"
            
            data.append({
                "time": date_val.strftime(time_fmt),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close'])
            })
        
        return {"symbol": symbol, "history": data}
    except Exception as e:
        print(f"Chart error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/portfolio")
def export_portfolio(symbols: str, period: str):
    """
    Export selected portfolio stocks to Excel
    symbols: comma-separated list of symbols
    period: daily, weekly, or monthly
    """
    try:
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill
        from fastapi.responses import Response
        
        if period not in ["daily", "weekly", "monthly"]:
            raise HTTPException(status_code=400, detail="Invalid period")
        
        # Parse symbols
        symbol_list = [s.strip() for s in symbols.split(',')]
        
        if not symbol_list:
            raise HTTPException(status_code=400, detail="No symbols provided")
        
        # Fetch data for each symbol
        results = []
        for symbol in symbol_list:
            data = analyze_stock(symbol, is_commodity="=" in symbol)
            if data:
                results.append(data)
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = f"Portfolio {period.capitalize()}"
        
        # Headers
        headers = ["Symbol", "Name", "Price", "Change %", "RSI", "Volume", "Prediction"]
        ws.append(headers)
        
        # Style header
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
        
        # Add data
        for stock in results:
            ws.append([
                stock.get('symbol', ''),
                stock.get('name', ''),
                stock.get('price', 0),
                stock.get('change_pct', 0),
                stock.get('rsi', 0),
                stock.get('volume', 0),
                stock.get('prediction', '')
            ])
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            ws.column_dimensions[column_letter].width = max_length + 2
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=portfolio_{period}.xlsx"
            }
        )
        
    except Exception as e:
        print(f"Portfolio export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Route aliases (frontend calls /insight and /opportunities without /api)
@app.get("/insight")
def get_insight_alias():
    """Alias for /api/insight"""
    return get_insight()

@app.get("/opportunities")
def get_opportunities_alias():
    """Alias for /api/opportunities"""
    opps = get_market_opportunities()
    return {"opportunities": opps}  # Frontend expects {opportunities: [...]}


@app.get("/api/export/{period}")
def export_analysis(period: str):
    """
    Generates an Excel (.xlsx) export for the given period.
    Period: daily, weekly, monthly
    """
    if period not in ["daily", "weekly", "monthly"]:
         raise HTTPException(status_code=400, detail="Invalid period. Use daily, weekly, or monthly.")
         
    data = get_bulk_analysis(period)
    
    if not data:
         raise HTTPException(status_code=404, detail="No data available for export.")

    # Convert to DataFrame
    import pandas as pd
    import io
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    df = pd.DataFrame(data)
    
    # Reorder/Select columns matching our visual preference
    columns_order = [
         "Symbol", "Name", "Report Period", "Analysis Date", "Trend",
         "Current Price", "Start Price", "Change %", "Change Amt",
         "Period High", "High Date", "Period Low", "Low Date",
         "RSI (14)", "RSI Status", "Volatility %", "MA(20)", "Volume (Period)"
    ]
    # Ensure dataframe has these columns (safe check)
    df = df.reindex(columns=columns_order)

    output = io.BytesIO()
    
    # Write to Excel with formatting
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'{period.capitalize()} Analysis')
        
        # Access the workbook and sheet
        workbook = writer.book
        worksheet = writer.sheets[f'{period.capitalize()} Analysis']
        
        # Define styles
        center_style = Alignment(horizontal='center', vertical='center')
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        
        # 1. Format Header
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_style
            
        # 2. Iterate all cells for alignment
        for row in worksheet.iter_rows():
            for cell in row:
                cell.alignment = center_style
                
        # 3. Auto-fit Column Width
        for col_idx, column_cells in enumerate(worksheet.columns, start=1):
            max_length = 0
            # Check header
            header_val = column_cells[0].value
            if header_val:
                max_length = len(str(header_val))
            
            # Check a few rows to guess width (checking all might be slow for huge data, but here it's fine)
            for cell in column_cells[1:]:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            # Add padding
            adjusted_width = (max_length + 2) * 1.2
            col_letter = get_column_letter(col_idx)
            worksheet.column_dimensions[col_letter].width = adjusted_width

    output.seek(0)
    
    from fastapi.responses import Response
    
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=market_analysis_{period}.xlsx"
        }
    )

# Helper dummy, we used string for fill above which might be wrong in strict openpyxl
# but let's stick to standard styles. We will skip complex fill for now to avoid import errors if not standard.
