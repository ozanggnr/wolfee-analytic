import logging
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
import yfinance as yf
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

GOLD_TYPE_MAP = {
    "gram-altin": ("gram_altin", "Gram Altın"),
    "ceyrek-altin": ("ceyrek_altin", "Çeyrek Altın"),
    "yarim-altin": ("yarim_altin", "Yarım Altın"),
    "tam-altin": ("tam_altin", "Tam Altın"),
    "cumhuriyet-altini": ("cumhuriyet_altini", "Cumhuriyet Altını"),
}

PERIOD_MAP = {
    "1d": ("5d", "15m"),
    "1w": ("5d", "15m"),
    "1mo": ("1mo", "1d"),
    "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
}


def fetch_bist_stock(symbol: str) -> Optional[dict]:
    """Fetch BIST stock data using yfinance. Symbol should include .IS suffix."""
    try:
        ticker_symbol = symbol if symbol.endswith(".IS") else f"{symbol}.IS"
        ticker = yf.Ticker(ticker_symbol)

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

        # Try to get the human-readable name (can be slow, so wrap carefully)
        name = ticker_symbol.replace(".IS", "")
        try:
            info = ticker.info
            name = info.get("shortName") or info.get("longName") or name
        except Exception:
            pass

        # Attempt to get bid/ask from info if available
        bid = 0.0
        ask = 0.0
        try:
            if "info" not in dir() or info is None:
                info = ticker.info
            bid = float(info.get("bid", 0) or 0)
            ask = float(info.get("ask", 0) or 0)
        except Exception:
            pass

        return {
            "symbol": ticker_symbol.replace(".IS", ""),
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
            "currency": "TRY",
            "market_type": "BIST",
        }
    except Exception as e:
        logger.error("Failed to fetch BIST stock %s via yfinance: %s", symbol, e)
        return None


def fetch_bist_stock_fallback(symbol: str) -> Optional[dict]:
    """Fallback: scrape stock data from Google Finance."""
    try:
        clean_symbol = symbol.replace(".IS", "")
        url = f"https://www.google.com/finance/quote/{clean_symbol}:IST"

        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Price is in the div with data-last-price attribute or class YMlKec
        price = 0.0
        price_el = soup.find("div", class_="YMlKec")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_text = price_text.replace("₺", "").replace(",", "").replace("\xa0", "").strip()
            try:
                price = float(price_text)
            except ValueError:
                pass

        # Change percentage
        change_pct = 0.0
        change_el = soup.find("div", class_="JwB6zf")
        if change_el:
            pct_text = change_el.get_text(strip=True)
            pct_text = pct_text.replace("%", "").replace("+", "").replace(",", ".").strip()
            try:
                change_pct = float(pct_text)
            except ValueError:
                pass

        # Name
        name = clean_symbol
        name_el = soup.find("div", class_="zzDege")
        if name_el:
            name = name_el.get_text(strip=True)

        # Try to extract additional data from the info table
        prev_close = 0.0
        day_high = 0.0
        day_low = 0.0
        volume = 0.0
        open_price = 0.0

        rows = soup.find_all("div", class_="P6K39c")
        for row in rows:
            label = row.get_text(strip=True).lower()
            value_el = row.find_next_sibling("div", class_="YMlKec")
            if not value_el:
                continue
            val_text = value_el.get_text(strip=True).replace(",", "").replace("₺", "").strip()
            try:
                val = float(val_text)
            except ValueError:
                continue

            if "previous close" in label or "önceki kapanış" in label:
                prev_close = val
            elif "day range" in label or "gün aralığı" in label:
                pass  # range format, skip
            elif "open" in label or "açılış" in label:
                open_price = val
            elif "volume" in label or "hacim" in label:
                volume = val
            elif "high" in label or "yüksek" in label:
                day_high = val
            elif "low" in label or "düşük" in label:
                day_low = val

        if prev_close > 0 and price > 0 and change_pct == 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        return {
            "symbol": clean_symbol,
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
            "currency": "TRY",
            "market_type": "BIST",
        }
    except Exception as e:
        logger.error("Failed to fetch BIST stock %s via Google Finance fallback: %s", symbol, e)
        return None


def fetch_turkish_gold() -> Optional[list[dict]]:
    """Scrape Turkish gold prices from bigpara.hurriyet.com.tr."""
    try:
        url = "https://bigpara.hurriyet.com.tr/altin/"

        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        # Look for the gold price table/list
        rows = soup.select("ul.mPrices li, div.tBody ul li")

        for row in rows:
            try:
                # Try to find the link/identifier
                link = row.find("a")
                if not link:
                    continue

                href = link.get("href", "")
                row_text = link.get_text(strip=True).lower()

                # Match against known gold types
                matched_key = None
                for key in GOLD_TYPE_MAP:
                    if key in href.lower() or key.replace("-", " ") in row_text:
                        matched_key = key
                        break

                if not matched_key:
                    # Also try matching display names
                    for key, (_, display) in GOLD_TYPE_MAP.items():
                        if display.lower() in row_text:
                            matched_key = key
                            break

                if not matched_key:
                    continue

                gold_type, display_name = GOLD_TYPE_MAP[matched_key]

                # Extract prices — typically in span elements
                spans = row.find_all("span")
                prices = []
                for span in spans:
                    txt = span.get_text(strip=True).replace(".", "").replace(",", ".").strip()
                    try:
                        prices.append(float(txt))
                    except ValueError:
                        continue

                buying_price = prices[0] if len(prices) > 0 else 0.0
                selling_price = prices[1] if len(prices) > 1 else 0.0
                change_pct = prices[2] if len(prices) > 2 else 0.0

                results.append({
                    "gold_type": gold_type,
                    "display_name": display_name,
                    "buying_price": buying_price,
                    "selling_price": selling_price,
                    "change_pct": change_pct,
                })
            except Exception as e:
                logger.warning("Failed to parse gold row: %s", e)
                continue

        if results:
            logger.info("Fetched %d gold types from bigpara", len(results))
            return results

        # Fallback: try alternate selectors
        table = soup.find("div", class_="tBody")
        if table:
            items = table.find_all("ul")
            for item in items:
                try:
                    cols = item.find_all("li")
                    if len(cols) < 3:
                        continue

                    name_text = cols[0].get_text(strip=True).lower()
                    matched_key = None
                    for key, (_, display) in GOLD_TYPE_MAP.items():
                        if display.lower() in name_text or key.replace("-", " ") in name_text:
                            matched_key = key
                            break

                    if not matched_key:
                        continue

                    gold_type, display_name = GOLD_TYPE_MAP[matched_key]

                    def parse_price(text: str) -> float:
                        text = text.replace(".", "").replace(",", ".").strip()
                        try:
                            return float(text)
                        except ValueError:
                            return 0.0

                    buying_price = parse_price(cols[1].get_text(strip=True))
                    selling_price = parse_price(cols[2].get_text(strip=True))
                    change_pct = parse_price(cols[3].get_text(strip=True)) if len(cols) > 3 else 0.0

                    results.append({
                        "gold_type": gold_type,
                        "display_name": display_name,
                        "buying_price": buying_price,
                        "selling_price": selling_price,
                        "change_pct": change_pct,
                    })
                except Exception as e:
                    logger.warning("Fallback gold parse failed: %s", e)
                    continue

        if results:
            logger.info("Fetched %d gold types from bigpara (fallback)", len(results))
        else:
            logger.warning("No gold data parsed from bigpara")

        return results if results else None
    except Exception as e:
        logger.error("Failed to fetch Turkish gold prices: %s", e)
        return None


def fetch_exchange_rates() -> Optional[list[dict]]:
    """Fetch exchange rates from TCMB (Central Bank of Turkey) XML feed."""
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"

        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

        root = ET.fromstring(resp.content)

        target_currencies = {
            "USD": ("USD/TRY", "Amerikan Doları"),
            "EUR": ("EUR/TRY", "Euro"),
            "GBP": ("GBP/TRY", "İngiliz Sterlini"),
        }

        results: list[dict] = []

        for currency_el in root.findall("Currency"):
            code = currency_el.get("CurrencyCode", "")
            if code not in target_currencies:
                continue

            pair, display_name = target_currencies[code]

            forex_buying = currency_el.findtext("ForexBuying", "0") or "0"
            forex_selling = currency_el.findtext("ForexSelling", "0") or "0"

            try:
                buying = float(forex_buying)
            except ValueError:
                buying = 0.0

            try:
                selling = float(forex_selling)
            except ValueError:
                selling = 0.0

            # Calculate mid-rate based change (TCMB does not provide change directly)
            change_pct = 0.0

            results.append({
                "pair": pair,
                "display_name": display_name,
                "buying": buying,
                "selling": selling,
                "change_pct": change_pct,
            })

        if results:
            logger.info("Fetched %d exchange rates from TCMB", len(results))
        else:
            logger.warning("No exchange rate data parsed from TCMB")

        return results if results else None
    except Exception as e:
        logger.error("Failed to fetch exchange rates from TCMB: %s", e)
        return None


def fetch_bist_history(symbol: str, period: str = "1mo") -> Optional[list[dict]]:
    """Fetch historical OHLCV data for a BIST stock using yfinance."""
    try:
        ticker_symbol = symbol if symbol.endswith(".IS") else f"{symbol}.IS"
        ticker = yf.Ticker(ticker_symbol)

        yf_period, yf_interval = PERIOD_MAP.get(period, ("1mo", "1d"))

        hist = ticker.history(period=yf_period, interval=yf_interval)

        if hist.empty:
            logger.warning("No history data for %s with period=%s", ticker_symbol, period)
            return None

        results: list[dict] = []
        for idx, row in hist.iterrows():
            time_str = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)
            results.append({
                "time": time_str,
                "open": round(float(row.get("Open", 0)), 4),
                "high": round(float(row.get("High", 0)), 4),
                "low": round(float(row.get("Low", 0)), 4),
                "close": round(float(row.get("Close", 0)), 4),
                "volume": int(row.get("Volume", 0)),
            })

        logger.info("Fetched %d history records for %s (%s)", len(results), ticker_symbol, period)
        return results
    except Exception as e:
        logger.error("Failed to fetch BIST history for %s: %s", symbol, e)
        return None
