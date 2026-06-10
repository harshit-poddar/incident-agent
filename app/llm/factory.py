from __future__ import annotations

from app.config import settings
from app.llm.base import LLMClient


class TracingLLMClient:
    """Wraps any LLMClient and raises an `llm.generate` span around every call,
    so each model invocation shows up in the trace waterfall with its latency
    and the schema it returned. It implements the LLMClient protocol, so agents
    remain unaware of it -- tracing is layered on at the seam, not in the agents."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner

    def generate(self, *, system, user, output_model):
        from app.obs.tracer import span

        with span(
            f"llm · {output_model.__name__}",
            kind="llm",
            output_model=output_model.__name__,
            model_mode=settings.model_mode,
            prompt_chars=len(system) + len(user),
        ):
            return self._inner.generate(system=system, user=user, output_model=output_model)


def _raw_client() -> LLMClient:
    if settings.model_mode == "mock":
        from app.llm.mock import default_mock_client

        return default_mock_client()
    if settings.model_mode == "replay":
        from app.llm.replay import ReplayLLMClient

        return ReplayLLMClient(settings.fixtures_dir)
    from app.llm.vllm import VLLMClient

    return VLLMClient()


def get_llm_client() -> LLMClient:
    """The model seam, now trace-instrumented. Every agent's LLM call is timed
    and nested under its agent span automatically."""
    return TracingLLMClient(_raw_client())
