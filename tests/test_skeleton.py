from __future__ import annotations

from app.llm.mock import default_mock_client
from app.orchestration.state import IncidentState, IncidentStatus
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Signal
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import (
    GateError,
    MockCluster,
    RemediationExecutor,
)
from app.tools.schemas import ApprovalDecision, RemediationAction, RemediationActionType
from app.tools.telemetry import TelemetryTool


def _run(approve: bool):
    cluster = MockCluster()
    cluster.register("payments-api")
    cluster.inject_fault("payments-api")
    supervisor = Supervisor(
        default_mock_client(), KnowledgeTool(), TelemetryTool(), RemediationExecutor(cluster)
    )
    state = IncidentState(
        signal=Signal(
            service="payments-api",
            metric="error_rate",
            value=0.38,
            threshold=0.02,
            message="x",
        )
    )
    provider = lambda s: ApprovalDecision(approved=approve, approver="tester", reason="t")
    return supervisor.run(state, provider), cluster


def test_golden_path_resolves():
    state, cluster = _run(approve=True)
    assert state.status == IncidentStatus.RESOLVED
    assert state.verification and state.verification.resolved
    assert cluster.services["payments-api"] == "healthy"
    events = [e.event for e in state.audit]
    for step in ("detection", "diagnosis", "plan", "executed", "verification"):
        assert step in events, f"missing lifecycle step: {step}"


def test_rejection_blocks_remediation():
    state, cluster = _run(approve=False)
    assert state.status == IncidentStatus.REJECTED
    assert not state.remediation_results
    assert cluster.services["payments-api"] == "unhealthy"  # left untouched


def test_executor_refuses_without_approval():
    cluster = MockCluster()
    cluster.register("payments-api")
    ex = RemediationExecutor(cluster)
    action = RemediationAction(
        action=RemediationActionType.RESTART_SERVICE,
        target="payments-api",
        rationale="x",
        risk="medium",
    )
    try:
        ex.execute(action, ApprovalDecision(approved=False, approver="x"))
        raise AssertionError("expected GateError")
    except GateError:
        pass
