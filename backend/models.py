from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean, Text, Index, ForeignKey, UniqueConstraint
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
    day_high = Column(Float, default=0)
    day_low = Column(Float, default=0)
    open_price = Column(Float, default=0)
    previous_close = Column(Float, default=0)
    bid = Column(Float, default=0)
    ask = Column(Float, default=0)
    rsi = Column(Float, default=50)
    ma_20 = Column(Float, default=0)
    volatility = Column(String(10), default='LOW')
    currency = Column(String(5), default='TRY')
    market_type = Column(String(20), default='BIST')  # BIST, GLOBAL, COMMODITY
    prediction = Column(String(500))
    reason = Column(String(500))
    is_favorable = Column(Boolean, default=False)
    is_buyable = Column(Boolean, default=False)
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
