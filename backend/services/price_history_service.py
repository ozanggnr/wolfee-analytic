"""Keep price_history filled with real daily closes for the market-card instruments (REQ-26).

Runs inside the worker's market-aware refresh, only for the exchanges being
refreshed in that cycle, and fetches only instruments whose history is missing
days. A first fetch backfills a year (DATABASE_CONTRACT §4.3 sizing); later ones
fetch the smallest range that covers the gap. A failed instrument stores nothing
and is retried after RETRY_AFTER_FAILURE; its indicators stay null (D4).

The closes are read back with ``price_history_repository.daily_closes`` in the
shape of Agent 3's ``quant.types.DailyClose``. Passing them to ``enrich_quote``
waits until Agent 3's REQ-24 change is on integration (TEAM_STRUCTURE H1).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional, Sequence

from models import Instrument
from repositories import instrument_repository, price_history_repository
from services import daily_bars

logger = logging.getLogger(__name__)

BACKFILL_RANGE = "1y"
# Smallest Yahoo range covering a gap of up to N calendar days since the latest stored day.
GAP_RANGES = ((4, "5d"), (28, "1mo"), (85, "3mo"), (175, "6mo"))
MIN_REFETCH_INTERVAL = timedelta(hours=6)
RETRY_AFTER_FAILURE = timedelta(hours=6)
FETCH_CONCURRENCY = 4
SATURDAY = 5

Fetcher = Callable[[str, str, datetime], Optional[daily_bars.DailyBars]]
SessionFactory = Callable[[], AbstractAsyncContextManager]

_failed_until: dict[int, datetime] = {}  # in memory: a cold start simply retries


@dataclass(frozen=True)
class RefreshStats:
    due: int
    fetched: int
    failed: int
    rows: int


def last_complete_weekday(today: date) -> date:
    """The most recent Monday–Friday strictly before ``today`` (holidays are not known here)."""
    day = today - timedelta(days=1)
    while day.weekday() >= SATURDAY:
        day -= timedelta(days=1)
    return day


def fetch_range(latest: Optional[date], today: date) -> str:
    if latest is None:
        return BACKFILL_RANGE
    gap = (today - latest).days
    return next((name for limit, name in GAP_RANGES if gap <= limit), BACKFILL_RANGE)


def is_due(latest: Optional[price_history_repository.LatestBar], now: datetime) -> bool:
    if latest is None:
        return True
    fetched_at = latest.fetched_at if latest.fetched_at.tzinfo else latest.fetched_at.replace(tzinfo=timezone.utc)
    if now - fetched_at < MIN_REFETCH_INTERVAL:
        return False
    return latest.date < last_complete_weekday(now.date())


def _recently_failed(instrument_id: int, now: datetime) -> bool:
    until = _failed_until.get(instrument_id)
    return until is not None and now < until


async def _fetch_one(instrument: Instrument, yahoo_range: str, now: datetime, fetch: Fetcher,
                     limit: asyncio.Semaphore) -> Optional[daily_bars.DailyBars]:
    async with limit:
        try:
            fetched = await asyncio.to_thread(fetch, instrument.provider_symbol, yahoo_range, now)
        except Exception:  # a provider bug must not stop the other instruments
            logger.exception("Daily history fetch raised for %s", instrument.provider_symbol)
            return None
    if fetched is None:
        return None
    if fetched.currency != instrument.currency.strip().upper():
        logger.error("Daily history for %s is in %s, instrument currency is %s; not stored",
                     instrument.provider_symbol, fetched.currency, instrument.currency)
        return None
    return fetched


async def refresh_price_history(
    sessions: SessionFactory,
    write_lock: asyncio.Lock,
    exchanges: Sequence[str],
    now: Optional[datetime] = None,
    fetch: Fetcher = daily_bars.fetch_daily_bars,
) -> RefreshStats:
    now = now or datetime.now(timezone.utc)
    async with sessions() as session:
        instruments = await instrument_repository.active_on_exchanges(session, exchanges)
        latest = await price_history_repository.latest_by_instrument(session, [i.id for i in instruments])
    due = [i for i in instruments if is_due(latest.get(i.id), now) and not _recently_failed(i.id, now)]
    if not due:
        return RefreshStats(0, 0, 0, 0)

    limit = asyncio.Semaphore(FETCH_CONCURRENCY)
    ranges = [fetch_range(latest[i.id].date if i.id in latest else None, now.date()) for i in due]
    results = await asyncio.gather(*(_fetch_one(i, r, now, fetch, limit) for i, r in zip(due, ranges)))

    stored, failed = 0, 0
    async with write_lock, sessions() as session:
        for instrument, result in zip(due, results):
            if result is None or not result.bars:
                failed += 1
                _failed_until[instrument.id] = now + RETRY_AFTER_FAILURE
                continue
            _failed_until.pop(instrument.id, None)
            stored += await price_history_repository.upsert_bars(
                session, instrument.id, result.currency, daily_bars.SOURCE,
                (asdict(bar) for bar in result.bars), fetched_at=now)
        await session.commit()

    stats = RefreshStats(due=len(due), fetched=len(due) - failed, failed=failed, rows=stored)
    log = logger.warning if failed else logger.info
    log("Price history: %d due, %d fetched, %d failed (indicators stay null), %d rows written",
        stats.due, stats.fetched, stats.failed, stats.rows)
    return stats
