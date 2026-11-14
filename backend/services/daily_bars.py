"""Real end-of-day bars from the Yahoo chart API, the source /api/chart uses (REQ-26).

This exists beside ``data_sources.turkish_market._fetch_yahoo_chart`` because
price_history (DATABASE_CONTRACT §4.3) needs what that helper cannot give:

- values exactly as supplied: a missing open/high/low stays None (the chart helper
  fills it with the close), and prices are Decimal, not float;
- the exchange-local trading day (from the response's ``gmtoffset``), not UTC;
- today's unfinished bar left out.

Nothing is interpolated or estimated. A bar without a close is dropped; a value
the CHECK constraint would refuse (a non-positive price, high below low) is
dropped rather than corrected.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

SOURCE = "yahoo_chart"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
REQUEST_TIMEOUT_SECONDS = 20
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://finance.yahoo.com/",
}
_PRICE_PLACES = Decimal("0.000001")  # NUMERIC(20, 6)
_VOLUME_PLACES = Decimal("0.01")     # NUMERIC(24, 2)


@dataclass(frozen=True)
class DailyBar:
    date: date
    open: Optional[Decimal]
    high: Optional[Decimal]
    low: Optional[Decimal]
    close: Decimal
    volume: Optional[Decimal]


@dataclass(frozen=True)
class DailyBars:
    currency: str
    bars: tuple[DailyBar, ...]


def _decimal(value: Any, places: Decimal) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number.quantize(places) if number.is_finite() else None


def _positive(value: Any) -> Optional[Decimal]:
    number = _decimal(value, _PRICE_PLACES)
    return number if number is not None and number > 0 else None


def _at(series: Any, index: int) -> Any:
    return series[index] if isinstance(series, list) and index < len(series) else None


def _unfinished_session_date(meta: Mapping[str, Any], offset: timedelta, now: datetime) -> Optional[date]:
    """The local date of a session still in progress at ``now``, if there is one."""
    regular = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    start, end = regular.get("start"), regular.get("end")
    now_ts = now.timestamp()
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return (datetime.fromtimestamp(start, timezone.utc) + offset).date() if now_ts < end else None
    return (now.astimezone(timezone.utc) + offset).date()  # unknown session: treat today as unfinished


def parse_chart(body: Mapping[str, Any], now: datetime) -> Optional[DailyBars]:
    """Daily bars from a chart API response; None when it is not a usable daily series."""
    try:
        result = body["chart"]["result"][0]
        meta = result["meta"]
        quote = result["indicators"]["quote"][0]
        timestamps = result["timestamp"]
    except (KeyError, IndexError, TypeError):
        return None
    currency = meta.get("currency")
    if meta.get("dataGranularity") != "1d" or not isinstance(currency, str) or len(currency) != 3:
        return None

    offset = timedelta(seconds=int(meta.get("gmtoffset") or 0))
    unfinished = _unfinished_session_date(meta, offset, now)
    by_date: dict[date, DailyBar] = {}
    for index, ts in enumerate(timestamps):
        close = _positive(_at(quote.get("close"), index))
        if close is None or not isinstance(ts, (int, float)):
            continue
        day = (datetime.fromtimestamp(ts, timezone.utc) + offset).date()
        if day == unfinished:
            continue
        high, low = _positive(_at(quote.get("high"), index)), _positive(_at(quote.get("low"), index))
        if high is not None and low is not None and high < low:
            high = low = None
        volume = _decimal(_at(quote.get("volume"), index), _VOLUME_PLACES)
        by_date[day] = DailyBar(day, _positive(_at(quote.get("open"), index)), high, low, close,
                                volume if volume is not None and volume >= 0 else None)
    return DailyBars(currency.upper(), tuple(sorted(by_date.values(), key=lambda bar: bar.date)))


def fetch_daily_bars(provider_symbol: str, yahoo_range: str, now: datetime) -> Optional[DailyBars]:
    """Fetch and parse; None (logged) on any failure. Blocking: run it in a thread."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, headers=_HEADERS, follow_redirects=True) as client:
            response = client.get(CHART_URL.format(symbol=provider_symbol),
                                   params={"range": yahoo_range, "interval": "1d", "includePrePost": "false"})
            response.raise_for_status()
            body = json.loads(response.content, parse_float=Decimal)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Daily history fetch failed for %s: %s", provider_symbol, exc)
        return None
    parsed = parse_chart(body, now)
    if parsed is None:
        logger.warning("Daily history for %s: response was not a usable daily series", provider_symbol)
    return parsed
