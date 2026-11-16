# Agent 2 (Backend) progress

Worktree `Wolfee-backend`, branch `agent/backend`, rebased onto `integration` 92a5ca0 on 2026-11-16 (no conflicts). Local commits only: no push, no merge.
Resume protocol: `git status`, read this file, continue from "In progress" / "Next".

## Current task (2026-11-16, second): REQ-36 (c) and the REQ-35 import

- [x] Rebase onto `integration` 92a5ca0: clean (commit hashes of the task below changed: ccfc76d, 41a47c9, 85fd500).
- [x] REQ-36 (c) `d2ac740`: no provider → forgot-password / resend-verification 503 for every address, before any lookup, no token; registration creates no verification token; the email fallback and provider errors never log the link, body, exception text or recipient. `test_email_unavailable.py` (7, incl. a known token string scanned in log records and stdout/stderr).
- [x] `08b8d33`: public `GET /api/auth/config` → `{"email_enabled", "registration_open"}`. `test_auth_config.py` (8).
- [x] `8bd0220`: `ai_insight_service` imports `MARKET_DISCLAIMER` (fallback to `DISCLAIMER` until agent/quant-ai f8bef1d is merged; drop it then). `test_insight_disclaimer_import.py` (2).
- [x] `7d00ac2`: rejected invite code → 403 (REQ-36 a), was 400.
- Verification (WSL): SQLite 641 passed; PG16.16 API 194 passed; base→head→base→head ok, `alembic check` clean at `e4a8c2f6b1d3`.
- API_CONTRACT §2.7 changes for Agent 1 (REQ-36 d): register `{"email","password","invite_code"}`, 403 "Registration requires a valid invite code." (missing/wrong/closed), 429 + Retry-After after 5 rejections/h/IP; no `captcha_token` anywhere, no `X-Captcha-Required`; forgot-password and resend-verification 503 without a provider; new `GET /api/auth/config`.

Tests run in WSL (docs/agents/TESTING.md §2, §3.1, §3.2), with agent-private names so other agents' runs cannot delete my database mid-run: SQLite file `~/wolfee-test/agent2/test.db`, Postgres databases `wolfee_tests_agent2` and `wolfee_migrations_agent2` on the PG16 cluster (port 55432). (The shared `~/wolfee-test/test.db` gave one run with 6 "readonly database" failures; the same commit passed 525/525 on rerun.)

## Current task (2026-11-16): invite code (D1), REQ-33 (a)(b)

Decisions: D1 = no CAPTCHA, registration by invite code; D2 = REQUIRE_EMAIL_VERIFICATION off for launch.

- [x] Rebase onto `integration` f9e64d2: clean.
- [x] Invite code `f82010f`: `invite_code` checked first, constant time, against `REGISTRATION_INVITE_CODE` (unset/blank = closed); one generic 400 for missing/wrong/closed; 5 rejections/h/IP → 429 even with the right code; audited `REGISTER_INVITE_REJECTED`. CAPTCHA removed (register + login after 3 failures, `X-Captcha-Required`). `test_registration_invite.py` (18).
- [x] REQ-33 (a) `4ca2c5a`: the four naive columns get `default`/`onupdate` = `models.utc_now_naive` (no DDL, no migration); API sends their `updated_at` with `+00:00`. `tests/api/test_utc_timestamps.py` (3, session at Asia/Tokyo on PG; fail on PG16 without the fix).
- [x] REQ-33 (b) `2518d91`: CORS = localhost + `CORS_ORIGINS` only. `test_cors_origins.py` (7).
- Verification (WSL, own DB names): SQLite 625 passed; PG16.16 API 194 passed; base→head→base→head ok, `alembic check` clean at `e4a8c2f6b1d3`.
- For Agent 4: register form needs an `invite_code` field (without it nobody can register from the UI); remove the CAPTCHA inputs and the `X-Captcha-Required` handling (auth.js:274-359, index.html:396-426).
- For Agent 1: API_CONTRACT §register (`invite_code`, no `captcha_token`, 400 invite / 429); DEPLOYMENT: set the `REGISTRATION_INVITE_CODE` secret, drop the `CAPTCHA_*` / `ALLOW_DEV_CAPTCHA_BYPASS` rows, D2 → `REQUIRE_EMAIL_VERIFICATION = "false"` in fly.toml; D3 no longer blocking.

## Earlier task (2026-11-15): REQ-31 (a)–(f)

- [x] Rebase onto `integration` 3515621: fast-forward (integration already held all my commits).
- [x] (a) HIGH `de7b239`: watchlist `round(None)` on change_pct. Cached, live and placeholder rows keep null; the summary lists a null ticker but skips it in counts, average and biggest mover; `avg_change_pct` is null when no ticker has a change. 2 tests (fail without the fix).
- [x] (b) `c924427`: `market_placeholder(loading=True)` when readiness fails ("still loading" template). Test updated (fails without).
- [x] (c) `69d20d4`: the third chart parser in `main.py` is gone; the last resort retries `_fetch_yahoo_chart` / `_fetch_yahoo_chart_global` (chart_row, missing OHL stay null). `test_chart_fallback.py` (2, fail on old code).
- [x] (d) `1e6e91e`: `stock_card` keeps null change_pct, no `estimated_fields`; export Change % / Change Amt / Trend / Start Price "Not available" when unknown. `test_market_display_change.py` (5).
- [x] (e) `d4eb20e`: FX change via `daily_change_pct` (None without previous close); gold change None when missing/unreadable; `change_pct` model defaults removed (no DDL); refreshers store None. `test_rate_and_gold_change.py` (6); recorded-TCMB test now expects null.
- [x] (f) `96f39e2`: `backend/api_router.py` deleted (no importer); guard test `tests/test_no_unused_router.py`.
- Verification (WSL, own DB names): SQLite 598 passed; PG16.16 API 191 passed; PG16 base→head→base→head ok, `alembic check` clean at `e4a8c2f6b1d3`.
- For Agent 4: the UI renders a null `change_pct` (watchlist summary, gold, FX) and a null `avg_change_pct` as "0.00%" (`portfolio.js:342-419`, `ui.js:177-218`); they should show "Not available".
- For Agent 1: TEAM_STRUCTURE.md:58 and IMPLEMENTATION_STATUS.md:29,199 still list `api_router.py`.

## Earlier task (2026-11-14, second batch): history wiring, REQ-28, REQ-30, WSL verification

- [x] Rebase onto `integration` 490995e: no conflicts (no file changed on both sides). 525 passed on SQLite.
- [x] 1. History wiring (REQ-24/26, fixes REQ-10). `workers._enrich_stock_data` and its estimate/advice-label copy are deleted.
  - `workers._enrich_quotes` calls `quant.signals.enrich_quote(data, market_type, currency, history=...)` for every BIST, Global and commodity quote and for the `/api/live-price` cache update.
  - `services/card_history.histories_for` reads the stored `price_history` closes as `DailyClose(date, Decimal(str(close)))`, two queries per market. An unknown instrument, no stored close, or a failed read (logged) gives `history=None`, so the indicators are null.
  - `indicators_as_of`, `indicator_method` and `volatility_pct` are kept in `stock_data.extra_data` (JSON, previously never written; no stock_data provenance columns exist, DATABASE_CONTRACT §4 M4 still open). `_stock_to_dict` returns them, plus `estimated_fields: []`; `prediction` / `reason` pass null through.
  - `refresh_all_data` runs the history refresh before the quotes, so the cards use the newest closes; on an empty cache the quotes go first.
  - The watchlist no longer turns a null label into "Bullish" / "Bearish".
  - Tests: `tests/services/test_card_enrichment.py` (7), `tests/api/test_live_price_cache.py` (1); 7 of the 8 fail on the old code (it stored rsi 68 and "PURCHASABLE — strong momentum +6.0%").
  - Results: SQLite 533 passed; PG16 API 180 passed; migrations base→head→base→head ok, `alembic check` clean at `d7b2e6f4a913`.
  - Still estimating: `analysis.analyze_stock` (`/api/analyze`, `/api/live-price` response) keeps Agent 3's `legacy_estimates=True` default; its result is re-enriched before it reaches the cache.
- [x] 2. REQ-28: `ai_insights` provenance and the AI routes on the guarded layer.
  - Migration `e4a8c2f6b1d3` (after `d7b2e6f4a913`) plus the `AIInsight` model: `generated_by` String(100), `generated_at` / `inputs_as_of` timestamptz, `is_fallback` Boolean, all nullable, no default, no backfill. downgrade drops the four columns only.
  - `services/ai_insight_service`: serve, generate (via `asyncio.to_thread(market_insight_response / stock_analysis_response, ...)`), store with all four values (newest 10 kept), and the template placeholders. No DB session is open during the model call.
  - `/api/insight` and `/insight`: the newest row with provenance; otherwise a new insight is generated once (lock), stored and returned. A row without provenance is never served. Not ready (REQ-20) or any error: the template ("Market data: not available yet"), with provenance, not stored.
  - `/api/ai/analyze/{symbol}`: guarded description with provenance; `inputs_as_of` = the cached row's `updated_at` (or now for a fresh fetch); errors give the template. `analyze_stock` now runs off the event loop.
  - Worker `refresh_ai_insight`: only a recent model-generated row with provenance counts as fresh (an old row or a fallback is replaced next cycle); it uses the same card rows as the routes (`market_display.stock_card`, moved from `main._stock_to_dict`).
  - Tests: `tests/api/test_insight_api.py` rewritten (9: old row ignored, new row carries provenance, guardrail violation → template, error → template, `violations` never in a response, analyze provenance); worker tests in `test_insight_readiness.py` (+2) and the caching test updated.
  - Results: SQLite 542 passed; PG16 API 187 passed; PG16 base→head→base→head ok, `alembic check` clean at `e4a8c2f6b1d3`; SQLite upgrade → downgrade base → upgrade, check clean.
  - Note for Agent 3: with partial data the placeholder template says "no instrument has a price", which is not literally true then; a "still loading" fact in `ai.facts` would read better.
- [x] 3. REQ-30: null, not 0.0, for a missing open / previous_close.
  - `data_sources/provided.provided_price`: a positive finite provider value, else None. Used for open / previous_close in `fetch_global_stock`, `fetch_global_stock_finnhub`, `fetch_commodity_data`, `fetch_bist_stock` and the Google Finance BIST fallback (its `prev_close > 0` check made None-safe).
  - The 5-day history fallback no longer uses today's price as the previous close when only one day comes back (that is a fabricated value); a NaN open from history is None.
  - `StockData.open_price` / `previous_close`: Python-side `default=0` removed (no DDL; same shape as bb00a11). `_upsert_stock` inserts None and lets None replace a stale value. `stock_card` returns null for null or a legacy 0.
  - Tests: `tests/services/test_provider_open_close.py` (22; 10 fail on the old code).
  - Results: SQLite 564 passed; PG16 API 187 passed; PG16 base→head→base→head ok, `alembic check` clean at `e4a8c2f6b1d3`; SQLite round trip clean.
  - `data_sources/**` is Agent 3's: only the open / previous_close lines were changed (REQ-30 is addressed to Agent 2). Left as is: `change_pct` is still 0.0 when there is no previous close, and the chart helpers fill a missing open with the close.
- [x] 4. Final WSL verification (code at `5881616`): SQLite 564 passed; PG16.16 API 187 passed (fresh `wolfee_tests_agent2`); PG16 upgrade head → downgrade base → upgrade head → downgrade base → upgrade head all ok, single head `e4a8c2f6b1d3`, `alembic check` "No new upgrade operations detected"; SQLite round trip clean. Live smoke (real Yahoo, throwaway DB): THYAO 252 closes stored, card rsi 71.32 / ma_20 279.61 / volatility HIGH (54.25 %), label "RSI above 70 (overbought)", indicators_as_of 2026-11-13; raw open 315.75 / previous_close 319.25.
- [ ] REQ-25 routes: done by REQ-28 (the guarded layer is now on integration and wired). Nothing open on my side until the next instruction.

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
