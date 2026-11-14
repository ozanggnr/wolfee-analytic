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
- [ ] REQ-24 support (added by the user 2026-11-14). **Next.**
  - `watchlist_routes.py` 161–163 call `round()` on `rsi`, `day_high` and `day_low`.
  - Make them, and every other caller of `analyze_stock` values, accept null: show "not available" in the export, and never a 500.
  - Add a test with null indicators. Agent 3 removes `legacy_estimates` only after this lands.
- [ ] REQ-19 (`normalize_symbol` for the watchlist market), REQ-20 (no insight from empty data), REQ-21 (watchlist summary cache invalidation).
- [ ] REQ-26: `price_history` migration (DATABASE_CONTRACT §4.3), plus a fetch/cache job from the `/api/chart` source, in Agent 3's REQ-24 input shape.
- [ ] REQ-25 routes. Waits until Agent 3 delivers the guarded layer.

## Earlier (done, see git log)
REQ-9, REQ-13, REQ-15, REQ-16. These were the analytics endpoints, the migration `c3f5a7e91d20`, and `create_all` limited to SQLite.

## Notes
- Scratch Postgres: `pgserver` 16.2 binaries in the scratch venv. Run `initdb --no-locale` (the default locale crashes on Windows), then `pg_ctl -o "-p 55432 -h 127.0.0.1"`.
- `alembic/env.py` uses `postgresql+psycopg2://`, because SQLAlchemy 2.1 defaults to psycopg 3.
