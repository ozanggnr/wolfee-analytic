"""REQ-26: price_history holds real daily bars from the /api/chart source (DATABASE_CONTRACT §4.3)."""
import asyncio
import copy
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import workers  # noqa: E402
from database import Base  # noqa: E402
from models import Instrument, PriceHistory  # noqa: E402
from repositories import price_history_repository  # noqa: E402
from services import daily_bars, price_history_service  # noqa: E402
from services.daily_bars import DailyBar, DailyBars  # noqa: E402

RECORDED = json.loads(Path(BACKEND_DIR, "tests", "fixtures", "yahoo_chart_THYAO.IS_1d_2026-11-13.json")
                      .read_text(encoding="utf-8"), parse_float=Decimal)
AFTER_FRIDAY_CLOSE = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
FRIDAY_SESSION_END = 1794582000  # meta.currentTradingPeriod.regular.end in the recording
RECORDED_DAYS = [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11),
                 date(2026, 11, 12), date(2026, 11, 13)]


def _quote(body):
    return body["chart"]["result"][0]["indicators"]["quote"][0]


# ---- parsing the recorded response -------------------------------------------------

def test_the_recorded_response_gives_exchange_local_days_and_exact_values():
    parsed = daily_bars.parse_chart(RECORDED, AFTER_FRIDAY_CLOSE)

    assert parsed.currency == "TRY"
    assert [bar.date for bar in parsed.bars] == RECORDED_DAYS
    assert parsed.bars[-1] == DailyBar(date(2026, 11, 13), Decimal("315.750000"), Decimal("323.500000"),
                                       Decimal("315.000000"), Decimal("320.250000"), Decimal("29607838.00"))


def test_todays_unfinished_bar_is_not_stored():
    during_friday = datetime.fromtimestamp(FRIDAY_SESSION_END - 3600, timezone.utc)

    parsed = daily_bars.parse_chart(RECORDED, during_friday)

    assert [bar.date for bar in parsed.bars] == RECORDED_DAYS[:-1]


def test_missing_values_stay_missing_and_impossible_ones_are_dropped():
    body = copy.deepcopy(RECORDED)
    quote = _quote(body)
    quote["open"][0] = None           # missing open: stays None, not the close
    quote["close"][1] = None          # no close: the bar is dropped
    quote["high"][2], quote["low"][2] = Decimal("300"), Decimal("310")  # high below low: both dropped
    quote["volume"][3] = None

    bars = {bar.date: bar for bar in daily_bars.parse_chart(body, AFTER_FRIDAY_CLOSE).bars}

    assert date(2026, 11, 9) not in bars
    assert bars[date(2026, 11, 6)].open is None and bars[date(2026, 11, 6)].close == Decimal("299.250000")
    assert (bars[date(2026, 11, 10)].high, bars[date(2026, 11, 10)].low) == (None, None)
    assert bars[date(2026, 11, 11)].volume is None


@pytest.mark.parametrize("mutate", [
    lambda body: body["chart"]["result"][0]["meta"].update(dataGranularity="1h"),
    lambda body: body["chart"].update(result=[]),
    lambda body: body["chart"]["result"][0]["meta"].pop("currency"),
])
def test_responses_that_are_not_a_daily_series_are_refused(mutate):
    body = copy.deepcopy(RECORDED)
    mutate(body)

    assert daily_bars.parse_chart(body, AFTER_FRIDAY_CLOSE) is None


# ---- scheduling rules ---------------------------------------------------------------

@pytest.mark.parametrize("today, expected", [(date(2026, 11, 16), date(2026, 11, 13)),   # Monday -> Friday
                                             (date(2026, 11, 14), date(2026, 11, 13)),   # Saturday -> Friday
                                             (date(2026, 11, 13), date(2026, 11, 12))])
def test_last_complete_weekday(today, expected):
    assert price_history_service.last_complete_weekday(today) == expected


@pytest.mark.parametrize("latest, expected", [(None, "1y"), (date(2026, 11, 13), "5d"),
                                              (date(2026, 10, 30), "1mo"), (date(2025, 1, 2), "1y")])
def test_the_fetch_covers_the_gap_with_the_smallest_range(latest, expected):
    assert price_history_service.fetch_range(latest, date(2026, 11, 17)) == expected


# ---- the job against a database -----------------------------------------------------

@pytest.fixture
def factory(monkeypatch):
    monkeypatch.setattr(price_history_service, "_failed_until", {})
    engine = create_async_engine("sqlite+aiosqlite://")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            session.add_all([
                Instrument(symbol="THYAO", exchange="BIST", provider_symbol="THYAO.IS", currency="TRY",
                           asset_class="equity", is_active=True),
                Instrument(symbol="AAPL", exchange="US", provider_symbol="AAPL", currency="USD",
                           asset_class="equity", is_active=True),
            ])
            await session.commit()

    asyncio.run(create())
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    asyncio.run(engine.dispose())


class FakeChart:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, provider_symbol, yahoo_range, now):
        self.calls.append((provider_symbol, yahoo_range))
        answer = self.answers.get(provider_symbol)
        return answer(now) if callable(answer) else answer


def _recorded(now):
    return daily_bars.parse_chart(RECORDED, now)


def _refresh(factory, fetch, now, exchanges=("BIST",)):
    return asyncio.run(price_history_service.refresh_price_history(factory, asyncio.Lock(), list(exchanges),
                                                                   now=now, fetch=fetch))


def _closes(factory, symbol="THYAO"):
    async def run():
        async with factory() as session:
            instrument = (await session.execute(select(Instrument).where(Instrument.symbol == symbol))).scalar_one()
            return await price_history_repository.daily_closes(session, instrument.id)

    return asyncio.run(run())


def test_a_first_refresh_backfills_a_year_and_reads_back_in_the_req24_shape(factory):
    fetch = FakeChart({"THYAO.IS": _recorded})

    stats = _refresh(factory, fetch, AFTER_FRIDAY_CLOSE)

    assert fetch.calls == [("THYAO.IS", "1y")]
    assert (stats.due, stats.fetched, stats.failed, stats.rows) == (1, 1, 0, 6)
    closes = _closes(factory)
    assert [c.date for c in closes] == RECORDED_DAYS
    assert closes[-1].close == Decimal("320.25") and isinstance(closes[-1].close, Decimal)


def test_nothing_is_fetched_when_the_history_is_current(factory):
    _refresh(factory, FakeChart({"THYAO.IS": _recorded}), AFTER_FRIDAY_CLOSE)
    again = FakeChart({"THYAO.IS": _recorded})

    _refresh(factory, again, AFTER_FRIDAY_CLOSE + timedelta(hours=12))

    assert again.calls == []


def test_a_later_refresh_fetches_the_gap_and_a_correction_replaces_the_day(factory):
    _refresh(factory, FakeChart({"THYAO.IS": _recorded}), AFTER_FRIDAY_CLOSE)
    tuesday = datetime(2026, 11, 17, 6, 0, tzinfo=timezone.utc)
    newer = DailyBars("TRY", (DailyBar(date(2026, 11, 13), None, None, None, Decimal("321.000000"), None),
                              DailyBar(date(2026, 11, 16), None, None, None, Decimal("325.500000"), None)))
    fetch = FakeChart({"THYAO.IS": newer})

    _refresh(factory, fetch, tuesday)

    assert fetch.calls == [("THYAO.IS", "5d")]
    closes = {c.date: c.close for c in _closes(factory)}
    assert closes[date(2026, 11, 13)] == Decimal("321") and closes[date(2026, 11, 16)] == Decimal("325.5")
    assert len(closes) == 7


def test_a_failed_fetch_stores_nothing_is_logged_and_waits_before_retrying(factory, caplog):
    fetch = FakeChart({"THYAO.IS": None})

    with caplog.at_level(logging.WARNING):
        stats = _refresh(factory, fetch, AFTER_FRIDAY_CLOSE)
    _refresh(factory, fetch, AFTER_FRIDAY_CLOSE + timedelta(hours=1))

    assert (stats.failed, stats.rows) == (1, 0)
    assert _closes(factory) == []
    assert fetch.calls == [("THYAO.IS", "1y")]  # not retried within RETRY_AFTER_FAILURE
    assert any("indicators stay null" in r.getMessage() for r in caplog.records)


def test_history_in_another_currency_is_not_stored(factory, caplog):
    in_usd = DailyBars("USD", _recorded(AFTER_FRIDAY_CLOSE).bars)

    stats = _refresh(factory, FakeChart({"THYAO.IS": in_usd}), AFTER_FRIDAY_CLOSE)

    assert (stats.failed, _closes(factory)) == (1, [])
    assert any("instrument currency is TRY" in r.getMessage() for r in caplog.records)


def test_only_the_exchanges_refreshed_this_cycle_are_fetched(factory):
    fetch = FakeChart({"THYAO.IS": _recorded, "AAPL": None})

    _refresh(factory, fetch, AFTER_FRIDAY_CLOSE, exchanges=("US",))

    assert fetch.calls == [("AAPL", "1y")]


@pytest.mark.parametrize("values", [{"close": Decimal("0")}, {"close": Decimal("1"), "high": Decimal("1"),
                                                                 "low": Decimal("2")},
                                    {"close": Decimal("1"), "volume": Decimal("-1")}])
def test_the_check_constraint_refuses_impossible_bars(factory, values):
    async def run():
        async with factory() as session:
            session.add(PriceHistory(instrument_id=1, date=date(2026, 11, 13), currency="TRY", source="test",
                                     **values))
            await session.commit()

    with pytest.raises(IntegrityError, match="ck_price_history_prices|CHECK"):
        asyncio.run(run())


def test_the_worker_refreshes_history_only_for_active_markets(monkeypatch):
    seen = []

    async def fake_refresh(sessions, lock, exchanges, **kwargs):
        seen.append(list(exchanges))

    monkeypatch.setattr(price_history_service, "refresh_price_history", fake_refresh)

    asyncio.run(workers.refresh_history_for_active_markets(True, False, True))
    asyncio.run(workers.refresh_history_for_active_markets(False, False, False))

    assert seen == [["BIST", "CMDTY"]]
