"""Walking-skeleton runner: inject one fault and drive the whole agent graph
end-to-end against the mock model. No GPU, no external services required.

    python scripts/run_skeleton.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.llm.factory import get_llm_client
from app.orchestration.state import IncidentState
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Signal
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool


def auto_approve(_: IncidentState) -> ApprovalDecision:
    return ApprovalDecision(approved=True, approver="auto", reason="auto-approved (skeleton)")


def main() -> None:
    cluster = MockCluster()
    cluster.register("payments-api")
    cluster.inject_fault("payments-api")  # <-- the injected incident

    signal = Signal(
        service="payments-api",
        metric="error_rate",
        value=0.38,
        threshold=0.02,
        message="5xx error rate breached threshold",
    )
    state = IncidentState(signal=signal)

    supervisor = Supervisor(
        llm=get_llm_client(),
        knowledge=KnowledgeTool(),
        telemetry=TelemetryTool(),
        executor=RemediationExecutor(cluster),
    )
    state = supervisor.run(state, approval_provider=auto_approve)

    print(f"\nIncident {state.id}  ->  {state.status.value.upper()}\n")
    for e in state.audit:
        print(f"  [{e.actor:>11}]  {e.event:<16}  {e.detail or ''}")
    print(f"\nCluster state: {cluster.services}\n")


if __name__ == "__main__":
    main()
