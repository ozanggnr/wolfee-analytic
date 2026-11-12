import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Railway and Render provide DATABASE_URL as postgresql://...
# asyncpg needs postgresql+asyncpg://...
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback to local SQLite for seamless local dev and tests if no Postgres URL is provided
    DATABASE_URL = "sqlite+aiosqlite:///./wolfee.db"
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")

# DB_POOL=null opens a connection per checkout instead of pooling. Use it behind an
# external pooler, or when connections must not outlive one event loop (the
# Postgres test run, see tests/conftest.py). Default: SQLAlchemy's queue pool.
DB_POOL = os.getenv("DB_POOL", "queue").strip().lower()
if DB_POOL not in ("queue", "null"):
    raise ValueError(f"DB_POOL must be 'queue' or 'null', got {DB_POOL!r}")

engine_kwargs = {"echo": False}
if not is_sqlite:
    connect_args = {}
    if "sslmode=" in DATABASE_URL:
        import re
        DATABASE_URL = re.sub(r'[\?\&]sslmode=[^&]+', '', DATABASE_URL)
        connect_args["ssl"] = "require"

    if DB_POOL == "null":
        engine_kwargs.update({"poolclass": NullPool, "connect_args": connect_args})
    else:
        engine_kwargs.update({
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "connect_args": connect_args
        })

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create missing tables, on SQLite only (local development and tests).

    On Postgres, migrations are the only source of the schema (DATABASE_CONTRACT
    §4.2): the deploy release step runs `alembic upgrade head`, and start-up
    creates nothing, so a missing table fails loudly instead of appearing silently.
    """
    if not is_sqlite:
        logger.info("Postgres: schema is managed by Alembic; init_db creates nothing")
        return
    import models  # Ensure all models are registered on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite tables created/verified")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
