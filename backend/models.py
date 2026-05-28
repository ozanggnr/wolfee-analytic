from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean, Text, Index
from sqlalchemy.sql import func
from database import Base
from datetime import datetime


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
