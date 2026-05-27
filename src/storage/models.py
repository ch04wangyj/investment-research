"""SQLAlchemy ORM models for operational storage.

Tables:
- market_daily: Daily OHLCV snapshots
- agent_reports: Agent-generated analysis reports
- tracked_symbols: Active watchlist
"""

from datetime import date, datetime

from sqlalchemy import (
    Column, Float, Integer, String, Text, Date, DateTime, JSON,
    BigInteger, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class MarketDaily(Base):
    __tablename__ = "market_daily"
    __table_args__ = (
        UniqueConstraint("date", "symbol", "exchange", name="uq_market_daily"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    name = Column(String(100))
    exchange = Column(String(10), nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(BigInteger)
    change_pct = Column(Float)
    currency = Column(String(10))


class AgentReport(Base):
    __tablename__ = "agent_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    ticker = Column(String(20), nullable=False, index=True)
    report_type = Column(String(30), nullable=False)
    # JSON content: {summary: str, data: dict, confidence: float, ...}
    content = Column(JSON, nullable=False)
    trigger_type = Column(String(20), default="manual")  # manual, scheduled, event


class TrackedSymbol(Base):
    __tablename__ = "tracked_symbols"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(String(100))
    exchange = Column(String(10), nullable=False)
    sector = Column(String(50))
    active = Column(Integer, default=1)
    added_at = Column(DateTime, default=datetime.now)
