"""LLM provider abstraction for OpenAI-compatible APIs and Ollama."""

import os
from dataclasses import dataclass
from typing import Literal

from langchain_openai import ChatOpenAI

from config.settings import get_settings

Tier = Literal["quick", "deep"]


@dataclass(frozen=True)
class ModelProvider:
    id: str
    name: str
    kind: Literal["openai_compatible", "ollama"]
    base_url: str
    api_key_env: str | None
    quick_model: str
    deep_model: str
    thinking_supported: bool = False

    @property
    def available(self) -> bool:
        if self.kind == "ollama":
            return True
        return bool(_configured_api_key(self.api_key_env))

    def model_for(self, tier: Tier) -> str:
        return self.deep_model if tier == "deep" else self.quick_model

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "quick_model": self.quick_model,
            "deep_model": self.deep_model,
            "thinking_supported": self.thinking_supported,
            "available": self.available,
        }


def provider_catalog() -> list[ModelProvider]:
    settings = get_settings()
    return [
        ModelProvider(
            id="deepseek",
            name="DeepSeek",
            kind="openai_compatible",
            base_url=settings.deepseek_base_url,
            api_key_env="DEEPSEEK_API_KEY",
            quick_model=settings.quick_model,
            deep_model=settings.deep_model,
            thinking_supported=True,
        ),
        ModelProvider(
            id="openai",
            name="OpenAI",
            kind="openai_compatible",
            base_url=settings.openai_base_url,
            api_key_env="OPENAI_API_KEY",
            quick_model="gpt-4o-mini",
            deep_model="gpt-4.1",
        ),
        ModelProvider(
            id="qwen",
            name="Qwen / DashScope",
            kind="openai_compatible",
            base_url=settings.qwen_base_url,
            api_key_env="QWEN_API_KEY",
            quick_model="qwen-plus",
            deep_model="qwen-max",
        ),
        ModelProvider(
            id="siliconflow",
            name="SiliconFlow",
            kind="openai_compatible",
            base_url=settings.siliconflow_base_url,
            api_key_env="SILICONFLOW_API_KEY",
            quick_model="Qwen/Qwen2.5-7B-Instruct",
            deep_model="deepseek-ai/DeepSeek-V3",
        ),
        ModelProvider(
            id="openrouter",
            name="OpenRouter",
            kind="openai_compatible",
            base_url=settings.openrouter_base_url,
            api_key_env="OPENROUTER_API_KEY",
            quick_model="openai/gpt-4o-mini",
            deep_model="anthropic/claude-3.7-sonnet",
        ),
        ModelProvider(
            id="volcengine",
            name="Volcengine Ark",
            kind="openai_compatible",
            base_url=settings.volcengine_base_url,
            api_key_env="VOLCENGINE_API_KEY",
            quick_model="doubao-seed-1-6-flash",
            deep_model="doubao-seed-1-6",
        ),
        ModelProvider(
            id="ollama",
            name="Ollama Local",
            kind="ollama",
            base_url=settings.ollama_base_url.rstrip("/") + "/v1",
            api_key_env=None,
            quick_model=settings.ollama_model,
            deep_model=settings.ollama_model,
        ),
    ]


def get_provider(provider_id: str | None = None) -> ModelProvider:
    settings = get_settings()
    provider_id = provider_id or settings.default_llm_provider
    providers = {provider.id: provider for provider in provider_catalog()}
    if provider_id not in providers:
        raise ValueError(f"Unknown LLM provider: {provider_id}")
    return providers[provider_id]


def create_chat_model(
    provider_id: str | None = None,
    *,
    tier: Tier = "deep",
    temperature: float = 0.2,
) -> ChatOpenAI:
    settings = get_settings()
    provider = get_provider(provider_id)
    api_key = "ollama" if provider.kind == "ollama" else _configured_api_key(provider.api_key_env)
    if provider.kind != "ollama" and not api_key:
        raise ValueError(f"Missing API key env var: {provider.api_key_env}")

    model_kwargs = {}
    if provider.id == "deepseek" and settings.enable_deepseek_thinking:
        model_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

    return ChatOpenAI(
        model=provider.model_for(tier),
        api_key=api_key,
        base_url=provider.base_url,
        temperature=temperature,
        timeout=180,
        model_kwargs=model_kwargs,
    )


def _configured_api_key(env_name: str | None) -> str:
    if not env_name:
        return ""
    value = os.getenv(env_name)
    if value:
        return value
    settings = get_settings()
    return str(getattr(settings, env_name.lower(), "") or "")
