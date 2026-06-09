from __future__ import annotations

from app.config import settings
from app.llm.base import LLMClient


def get_llm_client() -> LLMClient:
    if settings.model_mode == "mock":
        from app.llm.mock import default_mock_client

        return default_mock_client()
    if settings.model_mode == "replay":
        from app.llm.replay import ReplayLLMClient

        return ReplayLLMClient(settings.fixtures_dir)
    from app.llm.vllm import VLLMClient

    return VLLMClient()
