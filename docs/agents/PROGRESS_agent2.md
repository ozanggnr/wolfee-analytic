# Agent 2 (Backend) progress

Worktree `Wolfee-backend`, branch `agent/backend`. Local commits only: no push, no merge.
Resume protocol: `git status`, read this file, continue from "In progress" / "Next".

Test commands (from the worktree root, Python 3.11.9 venv in the session scratchpad):
- Full suite: `python -m pytest backend/tests -q -p no:cacheprovider -W ignore`
- Postgres: see item 3 once committed.

## Current task (user instructions after D2/D3 decisions)

0. D2 + D3. **Done.**
   - Weighted average is the default; FIFO is available as a parameter.
   - Foreign positions convert into TRY at the cached TCMB ForexBuying rate (`services/fx_service.py`).
   - A missing or zero rate marks only that position `missing_fx_rate`. Totals cover the valued positions, and are null if none are valued.
   - Non-TRY base portfolios get no rates; we never invert a rate.
1. One migration from head `b2e4d8a31c55`. **Blocked.** We are waiting for Agent 1 to update `DATABASE_CONTRACT` on `integration`; as of 2026-11-11 only `DEPLOYMENT.md` has changed. The migration must add:
   - `stock_data`, `turkish_gold`, `exchange_rates` and `ai_insights`, exactly as `create_all` builds them
   - `ix_auth_tokens_user_id`
   - a unique constraint on `instruments.provider_symbol`
2. No `create_all` at startup on Postgres. **Next.** This depends on item 1.
3. Postgres test harness in the repo: a no-pool engine selected by an env var. **Next.** This does not depend on item 1.
4. Re-run all of these, then report. **Pending.**
   - full suite on SQLite
   - API tests on empty Postgres 16
   - migrations base→head→base→head

## Notes
- Scratch Postgres: `pgserver` 16.2 binaries in the scratch venv. Run `initdb --no-locale` (the default locale crashes on Windows), then `pg_ctl -o "-p 55432 -h 127.0.0.1"`.
- `alembic/env.py` uses `postgresql+psycopg2://`, because SQLAlchemy 2.1 defaults to psycopg 3.
