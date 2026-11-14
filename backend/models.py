from sqlalchemy import (
    Column, String, Float, Integer, BigInteger, DateTime, Date, JSON, Boolean, Text, Numeric, CHAR,
    Index, ForeignKey, UniqueConstraint, CheckConstraint, event, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    watchlist_items = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    auth_tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False)  # 'BIST100' | 'US'
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="watchlist_items")

    __table_args__ = (
        UniqueConstraint('user_id', 'ticker', name='uq_user_ticker'),
        Index('idx_watchlist_user_ticker', 'user_id', 'ticker'),
    )


class UserSession(Base):
    """
    Server-side session storage.
    Session tokens stored here are validated against httpOnly, Secure, SameSite=Strict cookies.
    """
    __tablename__ = "user_sessions"

    id = Column(String(64), primary_key=True)  # Cryptographic session UUID / token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    user = relationship("User", back_populates="sessions")


class AuthToken(Base):
    """
    Cryptographic tokens for email verification and password resets.
    Raw tokens are never saved to DB; only their SHA-256 hash is persisted.
    """
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    token_type = Column(String(30), nullable=False)  # 'verify_email' | 'password_reset'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    is_used = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="auth_tokens")


class SecurityLog(Base):
    """
    Audit log for failed logins, lockout triggers, and suspicious security events.
    Includes timestamps, source IPs, and event context for forensic review.
    """
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)  # LOGIN_FAILED, ACCOUNT_LOCKED, etc.
    email = Column(String(255), nullable=True, index=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)



class StockData(Base):
    __tablename__ = "stock_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), index=True, nullable=False)
    name = Column(String(200))
    price = Column(Float, default=0)
    change_pct = Column(Float, default=0)
    volume = Column(Float, default=0)
    # Indicators and the labels built on them have no default: NULL means "not computed
    # from real history" (decision D4). A Python default would turn an explicit None into
    # an invented value on insert.
    day_high = Column(Float)
    day_low = Column(Float)
    open_price = Column(Float, default=0)
    previous_close = Column(Float, default=0)
    bid = Column(Float, default=0)
    ask = Column(Float, default=0)
    rsi = Column(Float)
    ma_20 = Column(Float)
    volatility = Column(String(10))
    currency = Column(String(5), default='TRY')
    market_type = Column(String(20), default='BIST')  # BIST, GLOBAL, COMMODITY
    prediction = Column(String(500))
    reason = Column(String(500))
    is_favorable = Column(Boolean)
    is_buyable = Column(Boolean)
    market_cap = Column(Float, default=0)
    extra_data = Column(JSON, default=dict)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_stock_symbol_updated', 'symbol', 'updated_at'),
        Index('idx_stock_market_type', 'market_type'),
    )


class TurkishGold(Base):
    __tablename__ = "turkish_gold"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gold_type = Column(String(50), unique=True, nullable=False)  # gram_altin, ceyrek_altin, etc.
    display_name = Column(String(100))
    buying_price = Column(Float, default=0)
    selling_price = Column(Float, default=0)
    change_pct = Column(Float, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(10), unique=True, nullable=False)  # USD/TRY, EUR/TRY
    display_name = Column(String(50))
    buying = Column(Float, default=0)
    selling = Column(Float, default=0)
    change_pct = Column(Float, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    insight_type = Column(String(20), default='daily')  # daily, stock_analysis, portfolio
    symbol = Column(String(20), nullable=True)  # null for daily insights
    insight_text = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# PORTFOLIO LEDGER (DATABASE_CONTRACT §3.1–§3.3)
# Money and quantities are NUMERIC; these tables never use Float.
# ============================================================
PORTFOLIO_KINDS = ("real", "paper")
TRANSACTION_TYPES = ("BUY", "SELL", "DIVIDEND", "FEE", "DEPOSIT", "WITHDRAWAL", "SPLIT")
TRANSACTION_SOURCES = ("manual", "import", "paper_fill")

# SQLite only auto-increments an INTEGER primary key; Postgres gets BIGINT.
_BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def _in_list(column: str, values: tuple) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Instrument(Base):
    """One canonical identity per tradable thing."""
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    provider_symbol = Column(String(30), nullable=False)
    name = Column(String(200), nullable=True)
    currency = Column(CHAR(3), nullable=False)
    asset_class = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", name="uq_instruments_symbol_exchange"),
        # One row per provider spelling (DATABASE_CONTRACT §4.2), so a cached quote
        # keyed by provider symbol resolves to exactly one instrument.
        UniqueConstraint("provider_symbol", name="uq_instruments_provider_symbol"),
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # RESTRICT: deleting a user must never silently erase a ledger.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(100), nullable=False)
    base_currency = Column(CHAR(3), nullable=False)
    kind = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("kind", PORTFOLIO_KINDS), name="ck_portfolios_kind"),
        Index("ix_portfolios_user_id", "user_id"),
        Index(
            "uq_portfolios_user_name_active", "user_id", "name", unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )


class Transaction(Base):
    """
    Append-only ledger row and the source of truth for holdings.
    A correction is a new row whose voids_transaction_id points at the row it reverses.
    """
    __tablename__ = "transactions"

    id = Column(_BigIntPK, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=False)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=True)
    type = Column(String(12), nullable=False)
    quantity = Column(Numeric(24, 8), nullable=False)
    price = Column(Numeric(20, 6), nullable=True)
    fee = Column(Numeric(20, 6), nullable=False, default=0, server_default=text("0"))
    currency = Column(CHAR(3), nullable=False)
    fx_rate_to_base = Column(Numeric(20, 8), nullable=True)
    trade_date = Column(Date, nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(String(500), nullable=True)
    source = Column(String(20), nullable=False)
    voids_transaction_id = Column(
        _BigIntPK, ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    instrument = relationship("Instrument", lazy="joined")

    __table_args__ = (
        CheckConstraint(_in_list("type", TRANSACTION_TYPES), name="ck_transactions_type"),
        CheckConstraint(_in_list("source", TRANSACTION_SOURCES), name="ck_transactions_source"),
        CheckConstraint("quantity >= 0", name="ck_transactions_quantity_non_negative"),
        CheckConstraint("fee >= 0", name="ck_transactions_fee_non_negative"),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_transactions_price_non_negative"),
        CheckConstraint(
            "fx_rate_to_base IS NULL OR fx_rate_to_base > 0", name="ck_transactions_fx_rate_positive"
        ),
        Index("ix_transactions_portfolio_date_id", "portfolio_id", "trade_date", "id"),
        Index("ix_transactions_instrument_id", "instrument_id"),
        # A row can be reversed at most once, even under concurrent requests.
        Index("uq_transactions_voids_transaction_id", "voids_transaction_id", unique=True),
    )


class LedgerImmutableError(RuntimeError):
    """Raised when application code tries to change or remove a ledger row."""


@event.listens_for(Transaction, "before_update")
def _forbid_transaction_update(mapper, connection, target):
    raise LedgerImmutableError("transactions are append-only; record a reversal instead of editing")


@event.listens_for(Transaction, "before_delete")
def _forbid_transaction_delete(mapper, connection, target):
    raise LedgerImmutableError("transactions are append-only; record a reversal instead of deleting")
