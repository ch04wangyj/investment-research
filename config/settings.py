"""Application configuration via pydantic-settings.

All configurable values are loaded from environment variables or .env file.
Sensitive defaults are empty; required keys raise validation errors at startup.
"""

from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # LLM providers
    default_llm_provider: str = "deepseek"
    enable_deepseek_thinking: bool = False

    # LLM - Deep Thinking
    deep_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # LLM - Quick Thinking
    quick_model: str = "deepseek-chat"
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

    # Cache TTL (seconds)
    cache_ttl_market_data_l1: int = 900   # 15 min in-memory
    cache_ttl_market_data_l2: int = 86400  # 24h SQLite
    cache_ttl_fundamentals_l1: int = 86400  # 24h in-memory
    cache_ttl_fundamentals_l2: int = 604800  # 7d SQLite

    def model_post_init(self, _ctx):
        # Ensure data directories exist
        for d in [self.sqlite_dir, self.chroma_dir, self.parquet_dir, self.cache_dir]:
            d = self.data_dir / d if not d.is_absolute() else d
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
