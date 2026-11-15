"""Opt-in Postgres run (REQ-9).

Set WOLFEE_TEST_POSTGRES_URL to an empty, disposable Postgres database to run the
API tests against it instead of the default SQLite file:

    WOLFEE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/wolfee_tests \\
        python -m pytest backend/tests/api -q -p no:cacheprovider -W ignore

The tests write users and ledgers into that database, so never point it at real data.
The API fixtures migrate it with `alembic upgrade head` first. The engine runs
without a connection pool (DB_POOL=null) because the fixtures open a fresh event
loop per call and asyncpg connections cannot move between loops.

This file is loaded before any test module, so the settings apply before
`database` creates its engine.
"""
import os

_POSTGRES_URL = os.getenv("WOLFEE_TEST_POSTGRES_URL")
if _POSTGRES_URL:
    if not _POSTGRES_URL.startswith(("postgresql://", "postgres://")):
        raise ValueError("WOLFEE_TEST_POSTGRES_URL must be a postgresql:// URL")
    os.environ["DATABASE_URL"] = _POSTGRES_URL
    os.environ["DB_POOL"] = "null"
