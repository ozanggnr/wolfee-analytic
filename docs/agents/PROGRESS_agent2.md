# Agent 2 (Backend) progress

Worktree `Wolfee-backend`, branch `agent/backend`. Local commits only: no push, no merge.
Resume protocol: `git status`, read this file, continue from "In progress" / "Next".

Test commands (from the worktree root, Python 3.11.9 venv in the session scratchpad):
- Full suite: `python -m pytest backend/tests -q -p no:cacheprovider -W ignore`
- Postgres API tests (empty, disposable DB): `WOLFEE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/wolfee_tests python -m pytest backend/tests/api -q -p no:cacheprovider -W ignore`

## Current task (user instructions after D2/D3 decisions)

0. D2 + D3. **Done.**
   - Weighted average is the default; FIFO is available as a parameter.
   - Foreign positions convert into TRY at the cached TCMB ForexBuying rate (`services/fx_service.py`).
   - A missing or zero rate marks only that position `missing_fx_rate`. Totals cover the valued positions, and are null if none are valued.
   - Non-TRY base portfolios get no rates; we never invert a rate.
1. One migration from head `b2e4d8a31c55`. **In progress (unblocked).** Agent 1 approved it in `DATABASE_CONTRACT` §4.2 on `integration`, commit `3fd0585`. Read that section first.
   - Nothing is written yet. Plan:
     - In `models.py`, add `UniqueConstraint("provider_symbol", name="uq_instruments_provider_symbol")` to `Instrument.__table_args__`.
     - Autogenerate against a freshly migrated DB, then review it. Add no `server_default` beyond the models'. `downgrade` drops the same objects in reverse.
   - Already checked: `gold_type` and `pair` are already unique in the models; `AuthToken.user_id` has `index=True`.
   - Pass condition: `alembic check` reports no differences on SQLite and on PG16.
   - The migration must add:
   - `stock_data`, `turkish_gold`, `exchange_rates` and `ai_insights`, exactly as `create_all` builds them
   - `ix_auth_tokens_user_id`
   - a unique constraint on `instruments.provider_symbol`
2. Limit `init_db` `create_all` to SQLite, per §4.2. **Next.** Do it in the same change as item 1.
3. Postgres test harness in the repo. **Done.**
   - `DB_POOL=null` in `database.py` gives a NullPool engine.
   - `tests/conftest.py` reads `WOLFEE_TEST_POSTGRES_URL`.
   - The API fixtures run `alembic upgrade head` on Postgres before the tests.
   - Result: 132/132 API tests pass on empty Postgres 16; 357/357 pass on SQLite.
4. Re-run all of these, then report. **Pending.**
   - full suite on SQLite
   - API tests on empty Postgres 16
   - migrations base→head→base→head

## Notes
- Scratch Postgres: `pgserver` 16.2 binaries in the scratch venv. Run `initdb --no-locale` (the default locale crashes on Windows), then `pg_ctl -o "-p 55432 -h 127.0.0.1"`.
- `alembic/env.py` uses `postgresql+psycopg2://`, because SQLAlchemy 2.1 defaults to psycopg 3.
