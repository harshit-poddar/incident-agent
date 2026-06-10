from __future__ import annotations

from typing import Callable, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class MockLLMClient:
    """Deterministic, offline stand-in for a served model. Returns scripted
    structured responses keyed by the requested output model name."""

    def __init__(self, scripts: dict[str, Callable[[], BaseModel]] | None = None) -> None:
        self._scripts: dict[str, Callable[[], BaseModel]] = scripts or {}

    def register(self, model_name: str, factory: Callable[[], BaseModel]) -> None:
        self._scripts[model_name] = factory

    def generate(self, *, system: str, user: str, output_model: type[T]) -> T:
        name = output_model.__name__
        if name not in self._scripts:
            raise KeyError(
                f"MockLLMClient has no script for {name!r}. "
                "Add one in default_mock_client()."
            )
        obj = self._scripts[name]()
        return output_model.model_validate(obj.model_dump())


def default_mock_client() -> MockLLMClient:
    """Golden-path scenario: payments-api OOM -> restart -> resolved.

    Also scripts ProposedFix for the GitHub CI-failure path (the Fixer agent),
    so the same offline client drives both the runtime and code-fix demos."""
    from app.schemas.incident import Detection, Diagnosis, ProposedFix, Verification
    from app.tools.schemas import (
        RemediationAction,
        RemediationActionType,
        RemediationPlan,
    )

    c = MockLLMClient()
    c.register(
        "Detection",
        lambda: Detection(
            is_anomaly=True,
            affected_service="payments-api",
            severity="high",
            summary="Error rate on payments-api spiked to 38% over 5m",
            confidence=0.92,
        ),
    )
    c.register(
        "Diagnosis",
        lambda: Diagnosis(
            root_cause="payments-api pods hitting memory limit -> OOM kills -> 5xx",
            evidence=[
                "error_rate 0.38 > 0.02 threshold",
                "mem_usage 98% on 3/3 pods",
                "runbook RB-114 matches OOM signature",
            ],
            confidence=0.87,
            recommended_action_type=RemediationActionType.RESTART_SERVICE.value,
        ),
    )
    c.register(
        "RemediationPlan",
        lambda: RemediationPlan(
            summary="Restart payments-api to clear leaked memory; watch for recurrence",
            requires_approval=True,
            actions=[
                RemediationAction(
                    action=RemediationActionType.RESTART_SERVICE,
                    target="payments-api",
                    rationale="Clear OOM condition",
                    risk="medium",
                )
            ],
        ),
    )
    c.register(
        "Verification",
        lambda: Verification(
            resolved=True,
            summary="error_rate back to 0.4%, memory nominal across pods",
            notes="Follow-up: investigate memory leak introduced in build #482",
        ),
    )
    c.register(
        "ProposedFix",
        lambda: ProposedFix(
            file_path="payments/handler.py",
            new_content=(
                "# payments/handler.py  (excerpt)\n"
                "from functools import lru_cache\n\n"
                "@lru_cache(maxsize=10_000)\n"
                "def handle_payment(req):\n"
                "    # FIX: bound the cache so it can no longer grow unboundedly\n"
                "    return build_receipt(req)\n"
            ),
            pr_title="fix(payments): bound receipt cache to stop OOM",
            pr_body=(
                "Root cause: `CACHE` in `handle_payment` grew without bound, "
                "exhausting heap and OOM-killing the pod (see runbook RB-114).\n\n"
                "Fix: replace the unbounded dict with an LRU cache capped at 10k "
                "entries. Steady-state memory now flat under sustained load."
            ),
            rationale="Unbounded cache was the leak; an LRU cap fixes it with a minimal diff.",
        ),
    )
    return c
