# Agent 2 (Backend) progress

Worktree `Wolfee-backend`, branch `agent/backend`, rebased onto `integration` acfd92e on 2026-11-13. Local commits only: no push, no merge.
Resume protocol: `git status`, read this file, continue from "In progress" / "Next".

Test commands (from the worktree root, Python 3.11.9 venv in the session scratchpad):
- Full suite: `python -m pytest backend/tests -q -p no:cacheprovider -W ignore`
- Postgres API tests (empty, disposable DB): `WOLFEE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/wolfee_tests python -m pytest backend/tests/api -q -p no:cacheprovider -W ignore`

## Current task (2026-11-13/14): rebase, then REQ-17, 14, 18, 24-support, 19, 20, 21, 26, 25 in order

Verify after each item with the scratch script `verify.sh`:
- full suite on SQLite, pinned deps
- API tests on empty PG16
- a clean `alembic check` on a migrated PG16

- [x] Rebase onto `integration` acfd92e. No conflicts.
- [x] REQ-17: `quant.sum_realized` replaces `_realized_by_currency` and `_realized_in_base`. Results: 381 on SQLite, 134 on PG16, check clean.
- [x] REQ-14: totals and weights come from `value_positions`; `_totals` is removed. Results: 381 on SQLite, 134 on PG16, check clean.
- [x] REQ-18 (HIGH): empty `/api/exchange-rates`.
  - Cause, reproduced on a fresh SQLite DB: the TCMB fetch worked, but the insert failed with "database is locked". `refresh_commodities` held a write transaction open across its network fetches; the error was swallowed and the refresh reported 0 items.
  - Fix in `workers.py`:
    - Commodities are fetched first, then written once.
    - `_DB_WRITE_LOCK` serializes every refresher's write phase.
    - When no rates arrive or the write fails, an error is logged and the table is left unchanged. Rates are never filled in.
  - Tests: a recorded TCMB response (`tests/fixtures/tcmb_today_2026-11-13.xml`), a lock-collision test that fails without the fix, and a source-unreachable test.
  - Results: 385 on SQLite, 134 on PG16, check clean.
- [x] REQ-24 support (added by the user 2026-11-14). Agent 3 can now remove `legacy_estimates`.
  - `services/market_display.py` holds the null-safe helpers and the export row. The export shows "Not available"; JSON keeps null.
  - Watchlist enrichment (cache, live fallback, placeholder):
    - The `round()` on null that caused a 500 is gone.
    - Nothing is filled in: no RSI 50, no day range taken from the price.
  - Both `/api/export/portfolio` routes:
    - They use one row builder.
    - No more `price*1.01`, `rsi or 50` or `'MEDIUM'` fill-ins.
    - A failed symbol shows "Not available", not 0.
    - The POST route returns 400 for stock entries that are not objects.
  - `_stock_to_dict` passes null indicators and labels through.
  - Found and fixed in the cache:
    - The `stock_data` ORM defaults (rsi 50, ma_20 0, volatility LOW, is_buyable False) turned an explicit None into estimates.
    - `_upsert_stock` skipped None, so old estimates would have stayed.
    - The Python defaults are removed; there is no DDL change, so no migration.
  - Tests:
    - `tests/api/test_null_indicators.py` (22) and `tests/services/test_stock_cache_nulls.py` (5).
    - The route tests reproduced the 500 before the fix. 3 of the cache tests fail without it.
  - Results: 412 on SQLite, 156 on PG16, check clean.
  - Left for others:
    - **Agent 3:** `ai_service.get_market_insight` compares `rsi < 30`, and `get_stock_analysis` formats `rsi`/`ma_20` with `:.0f`. Both raise on null. The callers catch it, so there's no 500, but the insight or analysis is lost. Also `analysis.py`: the 100–102 day-range estimate and the 253–283 bulk export.
    - **Agent 2 (H1):** `workers._enrich_stock_data` still estimates, until Agent 3's canonical enrichment lands.
    - **Agent 1:** DATABASE_CONTRACT §2.6 still says `rsi` "default 50".
    - **Agent 1 sign-off needed:** `models.py` is a shared contract. bb00a11 removed the Python-side defaults of seven `stock_data` columns (rsi, ma_20, day_high, day_low, volatility, is_favorable, is_buyable). There is no DDL change and `alembic check` is clean, but it was committed without prior sign-off.
    - **Agent 4:** legacy endpoints may now send null for these fields (REQ-27).
- [x] REQ-19: the watchlist market is decided by the server.
  - Cause: the frontend (`frontend/js/portfolio.js:73-74`, Agent 4) sends `market: "US"` whenever its own BIST list lookup misses, and the backend trusted the hint.
  - `services/watchlist_symbols.resolve` decides the market in this order:
    1. an explicit suffix;
    2. the `instruments` table;
    3. the `quant.universe` lists;
    4. the hint, only for a symbol known nowhere.
  - A hint that is impossible for the symbol's form returns 422. FX maps to `GLOBAL`, which has no watchlist value of its own.
  - Tests: `tests/api/test_watchlist_market.py` covers THYAO, THYAO.IS, AAPL and GC=F, each with and without a hint (14 tests, 9 failed before the fix).
  - Results: 426 on SQLite, 170 on PG16, check clean.
  - Existing rows stored as "US" are not rewritten; production starts with an empty database (D8).
- [x] REQ-20: no insight from empty or partial stock data.
  - Causes:
    - `refresh_ai_insight` stored an insight from whatever rows existed, even after a failed BIST or Global refresh.
    - `/api/insight` built one on the fly from `limit(50)` rows, which is partial by construction, and ran the synchronous Gemini call on the event loop.
  - `services/insight_readiness`: an insight needs ≥50% of both the BIST and Global universes, counting distinct symbols.
  - The worker logs and returns False; nothing is stored.
  - The route returns the "still loading" placeholder, unstored. Once data is ready it uses every row, via `asyncio.to_thread`, and still stores nothing.
  - Tests: `tests/services/test_insight_readiness.py` (10) and `tests/api/test_insight_api.py` (2).
  - Results: 438 on SQLite, 172 on PG16, check clean.
- [x] REQ-21: the watchlist summary changes immediately after POST or DELETE.
  - Cause: the server cache was already evicted, but `/summary` sent `Cache-Control: private, max-age=60`. The frontend refetches without `force_refresh`, so the browser served its HTTP-cached copy.
  - Fix:
    - The header is now `no-store, private`; the 60 s cache stays server-side.
    - A per-user generation counter stops a summary computed across a change from being cached.
  - Tests: `tests/api/test_watchlist_summary_cache.py` (4). The old `max-age` assertion in `tests/test_auth_and_watchlist.py` was updated.
  - Results: 442 on SQLite, 176 on PG16, check clean.
  - The deploy runs one uvicorn process, so the in-memory cache is consistent.
- [x] REQ-26: `price_history` storage, plus a fetch/cache job from the `/api/chart` source.
  - Migration `d7b2e6f4a913` (after `c3f5a7e91d20`) and the `PriceHistory` model, exactly as in §4.3:
    - BigInteger id;
    - foreign key `ON DELETE RESTRICT`;
    - NUMERIC(20,6) prices and NUMERIC(24,2) volume;
    - CHAR(3) currency and `fetched_at` timestamptz;
    - `uq_price_history_instrument_date` and `ck_price_history_prices`.
  - `services/daily_bars`: daily bars from the same Yahoo v8 chart endpoint `/api/chart` uses.
    - Values are stored as supplied, as Decimal; a missing open/high/low stays None.
    - Dates are the exchange-local day (`gmtoffset`). Today's unfinished bar is skipped.
    - A bar with no close is dropped, and impossible values are dropped.
  - `services/price_history_service.refresh_price_history`:
    - Runs in `refresh_all_data` for the exchanges refreshed that cycle (BIST, US, CMDTY).
    - Fetches only instruments that are missing days: a 1-year backfill first, then the smallest range covering the gap.
    - At most 4 requests at once; writes go under `_DB_WRITE_LOCK` as upserts.
    - A failed or wrong-currency fetch stores nothing and is retried after 6 h.
  - `price_history_repository.daily_closes` returns `DailyCloseRow(date, close: Decimal)`, oldest first. These are the same fields as Agent 3's `quant.types.DailyClose`.
  - Tests:
    - `tests/services/test_price_history.py` (23, against the recorded `tests/fixtures/yahoo_chart_THYAO.IS_1d_2026-11-13.json`).
    - `tests/api/test_price_history_storage.py` (3, also on PG16).
    - `price_history` added to the fresh-database table check.
  - Results: 468 on SQLite, 179 on PG16, check clean at head `d7b2e6f4a913`.
  - Also on PG16: upgrade head → downgrade base → upgrade head → check, all clean.
  - Live run: THYAO, AAPL and GC=F gave 754 rows. A second run found nothing due. Agent 3's `daily_indicators` and `enrich_quote` (read-only from `agent/quant-ai` 7683167) accepted the closes unchanged.
  - **Waits:** passing these closes into `enrich_quote` (the H1 swap of `_enrich_stock_data`) waits until Agent 3's REQ-24 is on `integration`. Until then the cards keep the legacy proxies.
  - **For Agent 1 / Agent 3:**
    - `data_sources/**` belongs to Agent 3, and `_fetch_yahoo_chart` is private and fills in OHL, so the daily-bar client lives in Agent 2's `services/daily_bars.py`. It can move into `data_sources` if Agent 3 prefers.
    - The first cycle on an empty database makes about 361 history requests, then about 1 per instrument per trading day.
- [ ] REQ-25 routes. **Next, but waits** until Agent 3's guarded layer is on `integration`. It exists on `agent/quant-ai` `fc9640a`, not yet integrated.

## Earlier (done, see git log)
REQ-9, REQ-13, REQ-15, REQ-16. These were the analytics endpoints, the migration `c3f5a7e91d20`, and `create_all` limited to SQLite.

## Notes
- Scratch Postgres: `pgserver` 16.2 binaries in the scratch venv. Run `initdb --no-locale` (the default locale crashes on Windows), then `pg_ctl -o "-p 55432 -h 127.0.0.1"`.
- `alembic/env.py` uses `postgresql+psycopg2://`, because SQLAlchemy 2.1 defaults to psycopg 3.
