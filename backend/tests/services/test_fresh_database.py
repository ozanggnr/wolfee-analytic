"""REQ-7: on an empty database migrated base -> head, the instrument sync makes the
ledger usable, is idempotent, and the migrations still roll back cleanly.

Runs alembic and the sync command as real subprocesses against a temporary SQLite
file, the way a deploy step would.
"""
import asyncio
import os
import sqlite3
import subprocess
import sys
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models import User  # noqa: E402
from quant.symbols import instrument_seed  # noqa: E402
from schemas.portfolio import PortfolioCreate  # noqa: E402
from schemas.transaction import TransactionCreate  # noqa: E402
from services import portfolio_service, transaction_service  # noqa: E402
from services.errors import InvalidInputError  # noqa: E402

LEDGER_TABLES = {"instruments", "portfolios", "transactions"}


def run_backend(args, database_url):
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def tables(path) -> set:
    with sqlite3.connect(path) as connection:
        return {name for (name,) in connection.execute("select name from sqlite_master where type='table'")}


@pytest.fixture
def migrated_database(tmp_path):
    path = tmp_path / "fresh.db"
    url = f"sqlite+aiosqlite:///{path.as_posix()}"
    run_backend(["-m", "alembic", "upgrade", "head"], url)
    return path, url


async def buy_thyao(url: str):
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            user = User(email="fresh@example.com", password_hash="unusable", email_verified=True,
                        failed_login_count=0)
            db.add(user)
            await db.commit()
            portfolio = await portfolio_service.create_portfolio(
                db, user.id, PortfolioCreate(name="Main", base_currency="TRY"))
            return await transaction_service.record_transaction(
                db, user.id, portfolio.id,
                TransactionCreate(type="BUY", symbol="THYAO", quantity="10", price="300.25",
                                  trade_date=date(2026, 3, 10)))
    finally:
        await engine.dispose()


def test_migrations_create_the_ledger_tables_on_an_empty_database(migrated_database):
    path, _ = migrated_database

    assert LEDGER_TABLES <= tables(path)


def test_sync_command_seeds_every_instrument_once_and_is_idempotent(migrated_database):
    path, url = migrated_database
    expected = len(instrument_seed())

    first = run_backend(["-m", "services.instrument_service"], url)
    second = run_backend(["-m", "services.instrument_service"], url)

    assert f"{expected} inserted, 0 updated" in first
    assert "0 inserted, 0 updated" in second
    with sqlite3.connect(path) as connection:
        assert connection.execute("select count(*) from instruments").fetchone() == (expected,)


def test_a_buy_of_thyao_succeeds_after_sync(migrated_database):
    _, url = migrated_database
    run_backend(["-m", "services.instrument_service"], url)

    created = asyncio.run(buy_thyao(url))

    assert (created.symbol, created.exchange, created.currency) == ("THYAO", "BIST", "TRY")
    assert created.quantity == Decimal("10") and created.fx_rate_to_base == Decimal("1")


def test_a_buy_of_thyao_is_rejected_before_sync(migrated_database):
    _, url = migrated_database

    with pytest.raises(InvalidInputError):
        asyncio.run(buy_thyao(url))


def test_migrations_roll_back_to_base_and_forward_again(migrated_database):
    path, url = migrated_database
    run_backend(["-m", "services.instrument_service"], url)

    run_backend(["-m", "alembic", "downgrade", "base"], url)
    assert tables(path) == {"alembic_version"}

    run_backend(["-m", "alembic", "upgrade", "head"], url)
    assert LEDGER_TABLES <= tables(path)


def pool_class_for(db_pool: str):
    env = {**os.environ, "DATABASE_URL": "postgresql://user@127.0.0.1:1/none", "DB_POOL": db_pool}
    return subprocess.run([sys.executable, "-c", "import database; print(type(database.engine.pool).__name__)"],
                          cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60)


def test_db_pool_null_gives_an_unpooled_engine_and_unknown_values_are_refused():
    assert pool_class_for("null").stdout.strip() == "NullPool"
    assert pool_class_for("queue").stdout.strip() == "AsyncAdaptedQueuePool"
    refused = pool_class_for("bogus")
    assert refused.returncode != 0 and "DB_POOL must be" in refused.stderr
