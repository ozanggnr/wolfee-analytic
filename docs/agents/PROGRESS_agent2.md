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
- [x] REQ-16: migration `c3f5a7e91d20` (DATABASE_CONTRACT §4.2), plus `init_db` `create_all` limited to SQLite.
  - `models.py` gains `uq_instruments_provider_symbol`.
  - SQLite needs `batch_alter_table` for the constraint, and `server_default` uses `sa.func.now()`.
  - Evidence:
    - PG16 and SQLite: base→head→base→head with a clean `alembic check` each time.
    - The seed gives 361, then 0.
    - The SQLite downgrade keeps the instrument rows.
    - 134/134 API tests on empty PG16; 362/362 on SQLite.
- [ ] Verify with the pinned `backend/requirements.lock`. **Next.** Then report.

## Waiting on others
- REQ-14 (Agent 3): partial totals and weights in `quant.value_positions`. Until then `analytics_service._totals` sums the valued positions, and `weight` stays null when the total is partial. Switch over when Agent 3 delivers.
- REQ-17 (Agent 3): a quant function for realised-P/L sums. Then replace `_realized_by_currency` and `_realized_in_base`. Not yet.

## Notes
- Scratch Postgres: `pgserver` 16.2 binaries in the scratch venv. Run `initdb --no-locale` (the default locale crashes on Windows), then `pg_ctl -o "-p 55432 -h 127.0.0.1"`.
- `alembic/env.py` uses `postgresql+psycopg2://`, because SQLAlchemy 2.1 defaults to psycopg 3.
