from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config. Everything model-related is driven by env so the same
    code runs against a mock, a small CPU model, or the 70B on the MI300X."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    # "mock"   -> offline scripted responses (no GPU)
    # "replay" -> serve fixtures captured from a real model (no GPU, deterministic)
    # "live"   -> hit the vLLM endpoint on the MI300X
    model_mode: str = "mock"
    model_base_url: str = "http://localhost:8000/v1"
    model_name: str = "Qwen3-4B"
    model_api_key: str = "abc-123"

    # Where ReplayLLMClient reads, and capture_fixtures.py writes, fixtures.
    fixtures_dir: str = "fixtures"

    # Incident persistence backend. "memory" (default, no deps) keeps state in a
    # dict; "postgres" persists it so it survives restarts and the async gate.
    store_mode: str = "memory"
    database_url: str = "postgresql://agent:agent@localhost:5432/incidents"


settings = Settings()
