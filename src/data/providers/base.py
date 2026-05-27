from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProviderResult:
    """Uniform data envelope returned by every market data provider."""

    source: str
    payload: Any = None
    as_of: str = field(default_factory=utc_now_iso)
    stale: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.payload is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "payload": self.payload,
            "as_of": self.as_of,
            "stale": self.stale,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderResult":
        return cls(
            source=str(data.get("source", "cache")),
            payload=data.get("payload"),
            as_of=str(data.get("as_of") or utc_now_iso()),
            stale=bool(data.get("stale", False)),
            error=data.get("error"),
        )

    @classmethod
    def failure(cls, source: str, error: str) -> "ProviderResult":
        return cls(source=source, payload=None, error=error)


class MarketDataProvider(ABC):
    """Data source adapter interface.

    Providers return ProviderResult instead of raw DataFrames so callers can
    show source, freshness, and degraded fallback state consistently.
    """

    def __init__(self, name: str, market: str, currency: str, timezone_name: str):
        self.name = name
        self.market = market
        self.currency = currency
        self.timezone = timezone_name

    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        """Get latest quotes for one or more symbols."""

    @abstractmethod
    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        """Get historical OHLCV records."""

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> ProviderResult:
        """Get key fundamental data for a symbol."""

    def format_symbol(self, symbol: str) -> str:
        """Normalize ticker for this provider."""
        return symbol
