from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from analysis import analyze_stock, get_market_opportunities, get_bulk_analysis, BIST_SYMBOLS, GLOBAL_SYMBOLS, COMMODITIES_SYMBOLS
from ai_service import get_market_insight

app = FastAPI(title="Wolfee Analytics")

# Enable CORS for frontend
origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "https://wolfee-backend.onrender.com",
    "https://solitary-scene-04bc.ozanggnr.workers.dev" # User's Cloudflare Frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.head("/")
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

# Cache structure
cache = {
    "quick_data": [],
    "last_updated": 0,
    "is_updating": False
}

def update_cache_background():
    """
    Background task to fetch ALL stocks and update cache.
    This runs after the response is returned to the user.
    """
    global cache
    if cache["is_updating"]:
        print("Cache update already in progress...")
        return

    print("🔄 Starting background cache update...")
    cache["is_updating"] = True
    
    try:
        results = []
        # Fetch all symbols
        all_symbols = BIST_SYMBOLS + GLOBAL_SYMBOLS
        total = len(all_symbols)
        
        for i, symbol in enumerate(all_symbols):
            try:
                # Reuse existing analyze_stock logic (now uses Google Finance Scraper)
                stock_data = analyze_stock(symbol, is_commodity=False)
                if stock_data:
                    results.append(stock_data)
                
                # Small delay to be nice to CPUs
                time.sleep(0.5) 
                
            except Exception as e:
                print(f"Background fetch error {symbol}: {e}")

        # Commodities
        for symbol in COMMODITIES_SYMBOLS:
             c_data = analyze_stock(symbol, is_commodity=True)
             if c_data:
                 results.append(c_data)

        # Update cache
        cache["quick_data"] = results
        cache["last_updated"] = time.time()
        print(f"✅ Background cache update complete. {len(results)} stocks cached.")
        
    except Exception as e:
        print(f"Background update failed: {e}")
    finally:
        cache["is_updating"] = False

@app.get("/api/market-data/quick")
def get_quick_market_data(background_tasks: BackgroundTasks):
    """
    Fetch stocks with timeout protection.
    1. Returns Cached data if available (< 5 mins old).
    2. If no cache, fetches TOP 10 stocks synchronously (fast).
    3. Triggers Background Task to fetch the rest.
    """
    global cache
    now = time.time()
    
    # 1. Return Cache if valid (5 min TTL)
    if cache["quick_data"] and (now - cache["last_updated"]) < 300:
        print(f"✓ Returning cached data ({len(cache['quick_data'])} stocks)")
        return {"stocks": cache["quick_data"]}
    
    # 2. Fetch Top 10 Sync (Fast boot)
    print("🚀 Cache empty/stale. Fetching Top 10...")
    
    # Select important stocks for initial view
    # 3 BIST, 3 Global, 2 Commodity
    initial_symbols = BIST_SYMBOLS[:3] + GLOBAL_SYMBOLS[:3] 
    
    results = []
    
    for symbol in initial_symbols:
        data = analyze_stock(symbol) # Now uses optimized api_router
        if data:
            results.append(data)
    
    # Add commodities for dashboard
    for symbol in list(COMMODITIES_SYMBOLS.keys())[:2]:
         data = analyze_stock(symbol, is_commodity=True)
         if data:
             results.append(data)
             
    # 3. Trigger Full Update in Background
    background_tasks.add_task(update_cache_background)
    
    # Update cache partially so subsequent immediate requests get something
    if not cache["quick_data"]:
        cache["quick_data"] = results
    
    return {"stocks": results}

@app.get("/api/market-data/full")
def get_full_market_data():
    """Returns ALL stocks using existing background cache."""
    global cache
    
    # Check cache
    now = time.time()
    if cache["quick_data"] and (now - cache["last_updated"]) < 300:
        print(f"Serving full batch from cache ({len(cache['quick_data'])} stocks)")
        return {"stocks": cache["quick_data"]}
    
    # If no cache (first run), return whatever we have or empty list
    # The background task should be running from the first 'quick' call
    if cache["quick_data"]:
         return {"stocks": cache["quick_data"]}
         
    return {"stocks": []}
    


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
    global cache
    # Use cached data if available (much faster!)
    data_source = cache.get("quick_data") 
    return {"opportunities": get_market_opportunities(cached_data=data_source)}

@app.get("/api/insight")
def get_insight():
    """Returns dynamic AI insight."""
    global cache
    data_source = cache.get("quick_data")
    opps = get_market_opportunities(cached_data=data_source)
    return {"insight": get_market_insight(opps)}

from analysis import analyze_stock, get_market_opportunities, get_bulk_analysis, BIST_SYMBOLS, COMMODITIES_SYMBOLS, GLOBAL_SYMBOLS

# ... existing imports ...

@app.get("/api/history/{symbol}")
def get_stock_history(symbol: str, period: str = "5y"):
    """Returns closing prices for charts using API router."""
    from api_router import get_router
    
    # Auto-append .IS logic
    is_global = symbol in GLOBAL_SYMBOLS or symbol.upper() in GLOBAL_SYMBOLS
    is_commodity = "=" in symbol
    
    if not is_global and not is_commodity and not symbol.endswith(".IS"):
        symbol += ".IS"
        
    try:
        router = get_router()
        data = router.fetch_history(symbol, period)
        
        if not data:
            raise HTTPException(status_code=404, detail="No history found via APIs")
            
        return {
            "symbol": symbol,
            "name": symbol, # Full name fetch not supported in router yet, use symbol
            "history": data["history"]
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

# ========== FRONTEND COMPATIBILITY FIXES ==========

# Chart endpoint (frontend calls /api/chart/{symbol}/{period})
@app.get("/api/chart/{symbol}/{period}")
def get_chart_data_frontend(symbol: str, period: str):
    """Chart data using multi-API router (Finnhub/Polygon)"""
    from api_router import get_router
    
    try:
        # Handle Turkish stocks
        if not symbol.endswith('.IS') and symbol not in GLOBAL_SYMBOLS and "=" not in symbol:
            symbol += '.IS'
            
        router = get_router()
        data = router.fetch_history(symbol, period)
        
        if not data:
            raise HTTPException(status_code=404, detail="No chart data available from APIs")
            
        return data  # Already formatted in api_router matches this structure
        
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
    global cache
    data_source = cache.get("quick_data")
    opps = get_market_opportunities(cached_data=data_source)
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
