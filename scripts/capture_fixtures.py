"""Capture LLM fixtures by driving the golden-path incident through a model and
recording every structured response into the fixtures dir. Those fixtures then
power MODEL_MODE=replay -- deterministic dev + demo with no GPU.

On the GPU pod (records REAL model outputs -- do this once, share the fixtures):
    MODEL_MODE=live python scripts/capture_fixtures.py

On any CPU box (seed fixtures from the mock to exercise the replay machinery):
    python scripts/capture_fixtures.py --from-mock
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import settings
from app.llm.base import LLMClient
from app.llm.replay import RecordingLLMClient
from app.orchestration.state import IncidentState
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Signal
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool


def _inner_client(from_mock: bool) -> LLMClient:
    if from_mock or settings.model_mode == "mock":
        from app.llm.mock import default_mock_client

        return default_mock_client()
    from app.llm.vllm import VLLMClient  # lazy: avoid importing openai under mock

    return VLLMClient()


def auto_approve(_: IncidentState) -> ApprovalDecision:
    return ApprovalDecision(approved=True, approver="auto", reason="capture run")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture LLM fixtures for replay mode.")
    parser.add_argument(
        "--from-mock",
        action="store_true",
        help="Record from the mock client (no GPU) instead of the live model.",
    )
    parser.add_argument(
        "--out",
        default=settings.fixtures_dir,
        help=f"Fixtures output dir (default: {settings.fixtures_dir}).",
    )
    args = parser.parse_args()

    inner = _inner_client(args.from_mock)
    recorder = RecordingLLMClient(inner, args.out)
    source = "mock" if (args.from_mock or settings.model_mode == "mock") else "live model"
    print(f"Capturing fixtures from the {source} into {args.out!r} ...")

    cluster = MockCluster()
    cluster.register("payments-api")
    cluster.inject_fault("payments-api")
    supervisor = Supervisor(
        llm=recorder,
        knowledge=KnowledgeTool(),
        telemetry=TelemetryTool(),
        executor=RemediationExecutor(cluster),
    )
    signal = Signal(
        service="payments-api",
        metric="error_rate",
        value=0.38,
        threshold=0.02,
        message="5xx error rate breached threshold",
    )
    state = supervisor.run(IncidentState(signal=signal), approval_provider=auto_approve)

    print(f"\nIncident {state.id}  ->  {state.status.value.upper()}")
    print(f"Captured {len(recorder.captured)} fixture(s):")
    for path in recorder.captured:
        print(f"  {path.name}")
    print(f"\nNow run the graph with no model:  MODEL_MODE=replay python scripts/run_skeleton.py")


if __name__ == "__main__":
    main()
