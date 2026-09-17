import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

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

engine_kwargs = {"echo": False}
if not is_sqlite:
    connect_args = {}
    if "sslmode=" in DATABASE_URL:
        import re
        DATABASE_URL = re.sub(r'[\?\&]sslmode=[^&]+', '', DATABASE_URL)
        connect_args["ssl"] = "require"

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
    """Create all tables on startup"""
    import models  # Ensure all models are registered on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
