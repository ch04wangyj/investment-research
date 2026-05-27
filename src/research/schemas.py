"""Pydantic schemas for institutional-style research reports."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Rating = Literal["BUY", "HOLD", "SELL"]


class DataSource(BaseModel):
    name: str
    as_of: str | None = None
    stale: bool = False
    error: str | None = None


class AnalystView(BaseModel):
    summary: str
    score: float = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    data_quality: Literal["high", "limited", "missing"] = "limited"


class InformationSummary(BaseModel):
    structured_facts: list[str] = Field(default_factory=list)
    unstructured_notes: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    source_count: int = 0
    summary: str = ""


class TradingStrategy(BaseModel):
    action: Literal["accumulate", "hold", "reduce", "avoid"]
    horizon: Literal["swing", "position", "long_term"] = "position"
    entry_zone: str = ""
    stop_loss: float | None = None
    take_profit: float | None = None
    position_size_pct: float = Field(default=0, ge=0, le=100)
    rationale: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)


class ResearchReport(BaseModel):
    run_id: str
    symbol: str
    market: Literal["ashare", "hk", "us"]
    company_name: str
    generated_at: datetime = Field(default_factory=datetime.now)
    rating: Rating
    confidence: Literal["low", "medium", "high"]
    current_price: float | None = None
    price_target_6m: float | None = None
    thesis: str
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    valuation: AnalystView
    financial_quality: AnalystView
    technical: AnalystView
    sentiment: AnalystView
    information_summary: InformationSummary = Field(default_factory=InformationSummary)
    trading_strategy: TradingStrategy | None = None
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    sources: list[DataSource] = Field(default_factory=list)
    llm_status: str = "not_used"
    disclaimer: str = (
        "This report is generated for personal research only and is not "
        "investment advice."
    )


class ResearchRequest(BaseModel):
    provider_id: str | None = None
    use_llm: bool = False
    period: str = "6mo"


class ResearchRunSummary(BaseModel):
    id: int
    run_id: str
    ticker: str
    created_at: datetime
    rating: str | None = None
    confidence: str | None = None
    report_type: str
    trigger_type: str | None = None
