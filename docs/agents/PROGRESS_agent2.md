# Agent 2 (Backend) progress

Worktree `Wolfee-backend`, branch `agent/backend`, rebased onto `integration` 48ef971 on 2026-11-12. Local commits only: no push, no merge.
Resume protocol: `git status`, read this file, continue from "In progress" / "Next".

Test commands (from the worktree root, Python 3.11.9 venv in the session scratchpad):
- Full suite: `python -m pytest backend/tests -q -p no:cacheprovider -W ignore`
- Postgres API tests (empty, disposable DB): `WOLFEE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/wolfee_tests python -m pytest backend/tests/api -q -p no:cacheprovider -W ignore`

## Current task (2026-11-12): rebase, then REQ-13/15/16/9, then verify

- [x] Rebase onto `integration` 48ef971. No conflicts.
- [x] REQ-13: weighted average is the default; FIFO is a parameter. (`5e464a7`, rebased)
- [x] REQ-9: the Postgres harness, enabled by `WOLFEE_TEST_POSTGRES_URL` together with `DB_POOL=null`. (`6a168a5`, rebased)
- [x] REQ-15: valuation FX comes from `exchange_rates`.
  - It uses the **selling** rate, with `source="exchange_rates"`.
  - TRY is the only accepted base currency.
- [ ] REQ-16. **Next.**
  - The migration from DATABASE_CONTRACT §4.2, chained from `b2e4d8a31c55`:
    - `stock_data`, `turkish_gold`, `exchange_rates`, `ai_insights`
    - `ix_auth_tokens_user_id`
    - `uq_instruments_provider_symbol`; also add this to `Instrument.__table_args__` in `models.py`
  - `init_db` `create_all` limited to SQLite.
  - Evidence needed: upgrade → downgrade → upgrade, then a clean `alembic check`, on both PG16 and SQLite.
- [ ] Verify, then report:
  - full suite on SQLite with pinned `backend/requirements.lock`
  - API tests on empty PG16
  - migrations base→head→base→head
  - seed run twice

## Waiting on others
- REQ-14 (Agent 3): partial totals and weights in `quant.value_positions`. Until then `analytics_service._totals` sums the valued positions, and `weight` stays null when the total is partial. Switch over when Agent 3 delivers.
- REQ-17 (Agent 3): a quant function for realised-P/L sums. Then replace `_realized_by_currency` and `_realized_in_base`. Not yet.

## Notes
- Scratch Postgres: `pgserver` 16.2 binaries in the scratch venv. Run `initdb --no-locale` (the default locale crashes on Windows), then `pg_ctl -o "-p 55432 -h 127.0.0.1"`.
- `alembic/env.py` uses `postgresql+psycopg2://`, because SQLAlchemy 2.1 defaults to psycopg 3.
