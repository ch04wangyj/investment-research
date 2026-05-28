"""Repository pattern for database operations.

All DB access goes through repositories, not raw SQLAlchemy.
This makes testing trivial (mock the repository) and isolates
storage implementation details from agent logic.
"""

from datetime import date, datetime
from typing import Any, Sequence

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

from src.storage.models import Base, MarketDaily, AgentReport, TrackedSymbol


class Repository:
    """Base repository with session management."""

    def __init__(self, db_path: str):
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

    def create_tables(self):
        Base.metadata.create_all(self.engine)

    def drop_tables(self):
        Base.metadata.drop_all(self.engine)

    def get_session(self) -> Session:
        return Session(self.engine)


class MarketDataRepository(Repository):
    """Operations on market_daily table."""

    def upsert(self, data: dict[str, Any]) -> None:
        """Insert or update a daily market record."""
        with self.get_session() as session:
            existing = session.execute(
                select(MarketDaily).where(
                    MarketDaily.date == data.get("date", date.today()),
                    MarketDaily.symbol == data["symbol"],
                    MarketDaily.exchange == data.get("exchange", ""),
                )
            ).scalar_one_or_none()

            if existing:
                for k, v in data.items():
                    if hasattr(existing, k) and k != "id":
                        setattr(existing, k, v)
            else:
                session.add(MarketDaily(**data))
            session.commit()

    def get_latest(self, symbol: str, days: int = 30) -> list[MarketDaily]:
        with self.get_session() as session:
            return list(session.execute(
                select(MarketDaily)
                .where(MarketDaily.symbol == symbol)
                .order_by(MarketDaily.date.desc())
                .limit(days)
            ).scalars().all())

    def get_by_date(self, symbol: str, start: date, end: date) -> list[MarketDaily]:
        with self.get_session() as session:
            return list(session.execute(
                select(MarketDaily)
                .where(
                    MarketDaily.symbol == symbol,
                    MarketDaily.date >= start,
                    MarketDaily.date <= end,
                )
                .order_by(MarketDaily.date)
            ).scalars().all())


class AgentReportRepository(Repository):
    """Operations on agent_reports table."""

    def save(self, data: dict[str, Any]) -> int:
        with self.get_session() as session:
            report = AgentReport(**data)
            session.add(report)
            session.commit()
            return report.id

    def get_latest(
        self, ticker: str, agent_name: str | None = None, limit: int = 5
    ) -> list[AgentReport]:
        with self.get_session() as session:
            q = (
                select(AgentReport)
                .where(AgentReport.ticker == ticker)
                .order_by(AgentReport.created_at.desc())
                .limit(limit)
            )
            if agent_name:
                q = q.where(AgentReport.agent_name == agent_name)
            return list(session.execute(q).scalars().all())

    def get_by_run(self, run_id: str) -> list[AgentReport]:
        with self.get_session() as session:
            return list(session.execute(
                select(AgentReport).where(AgentReport.run_id == run_id)
            ).scalars().all())

    def list_recent(self, limit: int = 50) -> list[AgentReport]:
        with self.get_session() as session:
            return list(session.execute(
                select(AgentReport)
                .order_by(AgentReport.created_at.desc())
                .limit(limit)
            ).scalars().all())

    def delete_by_id(self, report_id: int) -> bool:
        with self.get_session() as session:
            result = session.execute(
                delete(AgentReport).where(AgentReport.id == report_id)
            )
            session.commit()
            return bool(result.rowcount)

    def delete_many(self, report_ids: Sequence[int]) -> int:
        ids = [int(report_id) for report_id in report_ids if int(report_id) > 0]
        if not ids:
            return 0
        with self.get_session() as session:
            result = session.execute(
                delete(AgentReport).where(AgentReport.id.in_(ids))
            )
            session.commit()
            return int(result.rowcount or 0)


class TrackedSymbolRepository(Repository):
    """Operations on tracked_symbols table."""

    def get_active(self) -> list[TrackedSymbol]:
        with self.get_session() as session:
            return list(session.execute(
                select(TrackedSymbol).where(TrackedSymbol.active == 1)
            ).scalars().all())

    def add(self, symbol: str, name: str, exchange: str, sector: str = "") -> None:
        with self.get_session() as session:
            existing = session.execute(
                select(TrackedSymbol).where(TrackedSymbol.symbol == symbol)
            ).scalar_one_or_none()
            if existing:
                existing.active = 1
                existing.name = name or existing.name
            else:
                session.add(TrackedSymbol(
                    symbol=symbol, name=name, exchange=exchange, sector=sector
                ))
            session.commit()

    def remove(self, symbol: str) -> None:
        with self.get_session() as session:
            existing = session.execute(
                select(TrackedSymbol).where(TrackedSymbol.symbol == symbol)
            ).scalar_one_or_none()
            if existing:
                existing.active = 0
                session.commit()
