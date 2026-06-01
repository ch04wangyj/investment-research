"""Application configuration via pydantic-settings.

All configurable values are loaded from environment variables or .env file.
Sensitive defaults are empty; required keys raise validation errors at startup.
"""

from pathlib import Path
from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyConfig(BaseModel):
    """Configurable thresholds for trading strategy and research scoring."""

    # Composite score thresholds
    buy_threshold: float = 62.0
    sell_threshold: float = 42.0
    accumulate_threshold: float = 65.0
    avoid_threshold: float = 48.0
    reduce_threshold_high: float = 42.0
    reduce_threshold_low: float = 35.0

    # Position sizing (percentage of portfolio)
    accumulate_position_pct: float = 12.0
    hold_position_pct: float = 8.0
    reduce_position_pct: float = 4.0
    reduce_min_position_pct: float = 0.0

    # Risk management
    risk_band_min: float = 0.05
    risk_band_max: float = 0.14
    risk_band_default: float = 0.07
    take_profit_multiplier: float = 1.8

    # Technical indicator thresholds
    rsi_overbought: float = 75.0
    rsi_oversold: float = 25.0
    rsi_neutral_low: float = 45.0
    rsi_neutral_high: float = 65.0
    momentum_min_trend: float = 5.0
    trend_uptrend_bonus: float = 18.0
    trend_downtrend_penalty: float = 18.0
    rsi_neutral_bonus: float = 6.0
    rsi_overbought_penalty: float = 8.0
    rsi_oversold_bonus: float = 4.0

    # Valuation thresholds
    pe_low: float = 18.0
    pe_high: float = 45.0
    pb_low: float = 2.5
    pb_high: float = 8.0
    roe_high: float = 0.18
    roe_low: float = 0.06
    valuation_pe_bonus: float = 15.0
    valuation_pe_penalty: float = 15.0
    valuation_pb_bonus: float = 10.0
    valuation_pb_penalty: float = 10.0

    # Data quality
    min_history_samples: int = 40


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Project root
    project_root: Path = Path(__file__).resolve().parent.parent

    # Data directories
    data_dir: Path = Field(default=Path("./data"))
    sqlite_dir: Path = Field(default=Path("./data/sqlite"))
    chroma_dir: Path = Field(default=Path("./data/chroma"))
    parquet_dir: Path = Field(default=Path("./data/parquet"))
    cache_dir: Path = Field(default=Path("./data/cache"))

    # Audited runtime artifacts. Override STOCK_RESEARCH_ROOT when a separate
    # research archive is preferred.
    stock_research_root: Path = Field(default=Path("./data/research_runs"))

    # LLM providers
    default_llm_provider: str = "deepseek"
    enable_deepseek_thinking: bool = False

    # LLM - Deep Thinking
    deep_model: str = "deepseek-v4-pro"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # LLM - Quick Thinking
    quick_model: str = "deepseek-v4-pro"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    volcengine_api_key: str = ""
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Data APIs
    finnhub_api_key: str = ""

    # Cloud sync (Phase 3)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # Monitoring
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""

    # Agent limits
    max_tool_calls: int = 25
    agent_timeout_seconds: int = 120

    # Strategy configuration
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    # Cache TTL (seconds)
    cache_ttl_market_data_l1: int = 900   # 15 min in-memory
    cache_ttl_market_data_l2: int = 86400  # 24h SQLite
    cache_ttl_fundamentals_l1: int = 86400  # 24h in-memory
    cache_ttl_fundamentals_l2: int = 604800  # 7d SQLite

    # ── Pipeline ──
    pipeline_max_workers: int = 4
    pipeline_publish_enabled: bool = True   # Auto-convert .md → .html + .pdf after audit
    pipeline_skip_completed: bool = False   # Skip symbols with completed runs

    # ── Extension Modules (Phase 4 roadmap) ──
    screener_enabled: bool = False            # Auto stock screener (cron)
    screener_cron: str = "0 8 * * 1-5"       # Weekdays 8am
    realtime_monitor_enabled: bool = False    # Real-time price/volume/alert monitor
    realtime_poll_seconds: int = 300          # Poll interval (5 min default)
    daily_briefing_enabled: bool = False      # Daily pre-market briefing
    portfolio_tracker_enabled: bool = False   # Auto-update portfolio state
    trading_signals_enabled: bool = False     # Generate trade signals from research
    intelligence_auto_refresh_enabled: bool = False
    intelligence_refresh_hours: int = 12
    intelligence_context_items: int = 4

    def model_post_init(self, _ctx):
        # Ensure data directories exist
        for d in [self.data_dir, self.sqlite_dir, self.chroma_dir, self.parquet_dir, self.cache_dir, self.stock_research_root]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def operational_db_path(self) -> str:
        return str(self.sqlite_dir / "operational.db")

    @property
    def agents_db_path(self) -> str:
        return str(self.sqlite_dir / "agents.db")


@lru_cache
def get_settings() -> Settings:
    return Settings()
