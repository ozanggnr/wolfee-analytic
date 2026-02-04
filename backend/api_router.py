"""
Multi-API Stock Data Fetcher
Supports: Finnhub, Alpha Vantage, Polygon, Alpaca
Falls back gracefully when APIs fail or hit rate limits
"""

import os
import requests
from typing import Optional, Dict
import time
from datetime import datetime
from bs4 import BeautifulSoup


class StockAPIRouter:
    def __init__(self):
        # API Keys from environment
        self.finnhub_key = os.getenv('FINNHUB_API_KEY')
        self.alphavantage_key = os.getenv('ALPHA_VANTAGE_API_KEY') # Renamed from alpha_vantage_key
        self.polygon_key = os.getenv('POLYGON_API_KEY')
        # Alpaca keys removed as per instruction
        
        # Rate limiting (simple counter)
        self.last_call = {}
        self.min_interval = 1.0  # 1 second between calls
        
    def _rate_limit(self, api_name: str):
        """Simple rate limiting"""
        now = time.time()
        if api_name in self.last_call:
            elapsed = now - self.last_call[api_name]
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
        self.last_call[api_name] = time.time()
    
    def fetch_from_finnhub(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock data from Finnhub (60 calls/min free tier)
        Best for: Real-time quotes for US and global stocks
        """
        if not self.finnhub_key:
            return None
            
        try:
            self._rate_limit('finnhub')
            
            # Remove .IS suffix for Turkish stocks - Finnhub uses different format
            clean_symbol = symbol.replace('.IS', '.IST')  # Istanbul exchange
            
            # Get quote
            url = f"https://finnhub.io/api/v1/quote"
            params = {'symbol': clean_symbol, 'token': self.finnhub_key}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if data.get('c') == 0:  # No data
                return None
                
            # Calculate change percentage
            current_price = data.get('c', 0)
            prev_close = data.get('pc', current_price)
            change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
            
            return {
                'symbol': symbol,
                'price': round(current_price, 2),
                'change_pct': round(change_pct, 2),
                'high': data.get('h', current_price),
                'low': data.get('l', current_price),
                'open': data.get('o', current_price),
                'prev_close': prev_close,
                'timestamp': data.get('t', int(time.time()))
            }
            
        except Exception as e:
            print(f"Finnhub error for {symbol}: {e}")
            return None
    
    def fetch_from_alpha_vantage(self, symbol: str) -> Optional[Dict]:
        """
        Fetch from Alpha Vantage (25 requests/day free - USE SPARINGLY)
        Best for: Daily data when Finnhub fails
        """
        if not self.alphavantage_key:
            return None
            
        try:
            self._rate_limit('alpha_vantage')
            
            # Alpha Vantage doesn't support Turkish stocks well
            if symbol.endswith('.IS'):
                return None
            
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': self.alphavantage_key
            }
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            quote = data.get('Global Quote', {})
            if not quote:
                return None
            
            price = float(quote.get('05. price', 0))
            change_pct = float(quote.get('10. change percent', '0').replace('%', ''))
            
            return {
                'symbol': symbol,
                'price': round(price, 2),
                'change_pct': round(change_pct, 2),
                'high': float(quote.get('03. high', price)),
                'low': float(quote.get('04. low', price)),
                'open': float(quote.get('02. open', price)),
                'prev_close': float(quote.get('08. previous close', price)),
                'volume': int(quote.get('06. volume', 0))
            }
            
        except Exception as e:
            print(f"Alpha Vantage error for {symbol}: {e}")
            return None
    
    def fetch_from_polygon(self, symbol: str) -> Optional[Dict]:
        """
        Fetch from Polygon.io (5 calls/min free)
        Best for: US stocks previous day data
        """
        if not self.polygon_key:
            return None
            
        try:
            self._rate_limit('polygon')
            
            # Polygon doesn't support Turkish stocks
            if symbol.endswith('.IS'):
                return None
            
            # Get previous day's data
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
            params = {'apiKey': self.polygon_key}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if not results:
                return None
            
            quote = results[0]
            close_price = quote.get('c', 0)
            open_price = quote.get('o', close_price)
            change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0
            
            return {
                'symbol': symbol,
                'price': round(close_price, 2),
                'change_pct': round(change_pct, 2),
                'high': quote.get('h', close_price),
                'low': quote.get('l', close_price),
                'open': open_price,
                'volume': quote.get('v', 0)
            }
            
        except Exception as e:
            print(f"Polygon error for {symbol}: {e}")
            return None
    
    def fetch_google_finance(self, symbol: str) -> Optional[Dict]:
        """
        Scrape current price data from Google Finance.
        Note: Scraping can be fragile and may break with website changes.
        """
        try:
            # Google Finance text scraping is fragile.
            # We ONLY use it for Turkish stocks (.IS) because Finnhub/Poly often lack them or delay.
            if not symbol.endswith('.IS'):
                return None

            # Map .IS to BIST:
            gf_symbol = f"BIST:{symbol.replace('.IS', '')}"
            
            # Simple User-Agent to look like browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
            }
            
            url = f"https://www.google.com/finance/quote/{gf_symbol}"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the current price
            price_tag = soup.find('div', class_='YMlKec fxKbKc')
            if not price_tag:
                # Fallback for different structure or if not found
                price_tag = soup.find('div', class_='YMlKec')
            
            if not price_tag:
                return None
            
            price_str = price_tag.text.strip().replace(',', '') # Remove comma for thousands
            current_price = float(price_str)
            
            # Find change and change percentage
            change_tag = soup.find('div', class_='JwB6zf')
            if change_tag:
                change_text = change_tag.text.strip()
                parts = change_text.split('(')
                if len(parts) == 2:
                    change_value_str = parts[0].strip().replace(',', '')
                    change_pct_str = parts[1].replace(')', '').replace('%', '').strip()
                    
                    change_value = float(change_value_str)
                    change_pct = float(change_pct_str)
                    
                    # Determine previous close from current price and change
                    prev_close = current_price - change_value
                    
                    return {
                        'symbol': symbol,
                        'price': round(current_price, 2),
                        'change_pct': round(change_pct, 2),
                        'prev_close': round(prev_close, 2),
                        'timestamp': int(time.time()) # Current time as timestamp
                        # Google Finance scraping typically doesn't provide high/low/open directly on the main quote page
                    }
            
            # If change info not found, return just price
            return {
                'symbol': symbol,
                'price': round(current_price, 2),
                'timestamp': int(time.time())
            }
            
        except requests.exceptions.RequestException as req_e:
            print(f"Google Finance request error for {symbol}: {req_e}")
            return None
        except Exception as e:
            print(f"Google Finance scraping error for {symbol}: {e}")
            return None

    def fetch_price(self, symbol: str) -> Optional[Dict]:
        """
        Fetch current price data.
        Priority: Google Finance (Scrape) -> Finnhub -> Alpha Vantage -> Polygon
        """
        
        # 0. Try Google Finance (Scraping) - Requested by User
        # Note: scraping is slow but gets around API limits if careful.
        gf_data = self.fetch_google_finance(symbol)
        if gf_data:
            return gf_data

        # 1. Try Finnhub (Fastest API)
        data = self.fetch_from_finnhub(symbol)
        if data:
            return data
        
        # 2. Try Alpha Vantage (limited calls)
        data = self.fetch_from_alpha_vantage(symbol)
        if data:
            return data
        
        # Try Polygon (US stocks only)
        data = self.fetch_from_polygon(symbol)
        if data:
            return data
        
        return None

    def fetch_history(self, symbol: str, period: str = "1mo") -> Optional[Dict]:
        """
        Fetch historical candle data for charts.
        Priority: Finnhub -> Polygon -> Alpha Vantage
        """
        # Convert period to timestamps (start/end)
        end_ts = int(time.time())
        start_ts = end_ts - (30 * 24 * 3600) # Default 1mo
        resolution = "D"
        
        if period == "1d":
            start_ts = end_ts - (24 * 3600)
            resolution = "15" # 15 min
        elif period == "1wk":
            start_ts = end_ts - (7 * 24 * 3600)
            resolution = "60"
        elif period == "1mo":
            start_ts = end_ts - (30 * 24 * 3600)
            resolution = "D" 
        elif period == "1y":
            start_ts = end_ts - (365 * 24 * 3600)
            resolution = "D" # Daily is best for 1y to avoid limits
        elif period == "5y":
            start_ts = end_ts - (5 * 365 * 24 * 3600)
            resolution = "W" # Weekly
            
        # Try Finnhub (Best for candles)
        if self.finnhub_key:
            try:
                self._rate_limit('finnhub')
                clean_symbol = symbol.replace('.IS', '.IST')
                
                # Finnhub resolution mapping
                # Supported: 1, 5, 15, 30, 60, D, W, M
                fh_res = resolution
                if resolution == "15": fh_res = "15"
                if resolution == "60": fh_res = "60"
                if resolution == "W": fh_res = "W"
                
                url = "https://finnhub.io/api/v1/stock/candle"
                params = {
                    'symbol': clean_symbol,
                    'resolution': fh_res,
                    'from': start_ts,
                    'to': end_ts,
                    'token': self.finnhub_key
                }
                
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 429:
                     print(f"Finnhub History 429 for {symbol}")
                     # Fallthrough
                else:
                    data = response.json()
                    
                    if data.get('s') == 'ok':
                        # Convert to our format
                        history = []
                        times = data.get('t', [])
                        opens = data.get('o', [])
                        highs = data.get('h', [])
                        lows = data.get('l', [])
                        closes = data.get('c', [])
                        
                        for i in range(len(times)):
                            ts = datetime.fromtimestamp(times[i])
                            time_str = ts.strftime("%Y-%m-%d %H:%M") if "m" in period or period=="1d" else ts.strftime("%Y-%m-%d")
                            history.append({
                                "time": time_str,
                                "open": opens[i],
                                "high": highs[i],
                                "low": lows[i],
                                "close": closes[i]
                            })
                        return {"symbol": symbol, "history": history}
                    
            except Exception as e:
                print(f"Finnhub history error: {e}")

        # Try Polygon (US only)
        if self.polygon_key and not symbol.endswith(".IS"):
            try:
                self._rate_limit('polygon')
                multiplier = 1
                timespan = "day"
                
                if period == "1d": 
                    timespan = "minute"
                    multiplier = 15
                elif period == "1y":
                    timespan = "day"
                elif period == "5y":
                    timespan = "week"
                    
                start_date = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")
                end_date = datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d")
                
                url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
                params = {'apiKey': self.polygon_key, 'limit': 500}
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 429:
                    print(f"Polygon History 429 for {symbol}")
                    # Fallthrough
                else:
                    data = response.json()
                    
                    if data.get('results'):
                        history = []
                        for bar in data['results']:
                            ts = datetime.fromtimestamp(bar['t'] / 1000)
                            time_str = ts.strftime("%Y-%m-%d %H:%M") if period=="1d" else ts.strftime("%Y-%m-%d")
                            history.append({
                                "time": time_str,
                                "open": bar.get('o'),
                                "high": bar.get('h'),
                                "low": bar.get('l'),
                                "close": bar.get('c')
                            })
                        return {"symbol": symbol, "history": history}
                    
            except Exception as e:
                print(f"Polygon history error: {e}")

        return None


# Global router instance
_router = None

def get_router() -> StockAPIRouter:
    """Get singleton router instance"""
    global _router
    if _router is None:
        _router = StockAPIRouter()
    return _router
