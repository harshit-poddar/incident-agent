"""Minimal FastAPI surface for the agent. Runs the full graph per incident.

Run:  uvicorn app.main:app --reload
NOTE: real async human-approval (pause the graph at the gate, resume on the
/approve call) is a TODO for the next slice -- see CLAUDE.md. For now approval
is supplied inline via the auto_approve flag."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.llm.factory import get_llm_client
from app.orchestration.state import IncidentState
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Signal
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool

app = FastAPI(title="Autonomous incident agent (AGENTS_026)")

_STORE: dict[str, IncidentState] = {}
_CLUSTER = MockCluster()


@app.post("/incidents")
def trigger(signal: Signal, auto_approve: bool = True) -> IncidentState:
    _CLUSTER.register(signal.service)
    _CLUSTER.inject_fault(signal.service)
    state = IncidentState(signal=signal)
    supervisor = Supervisor(
        llm=get_llm_client(),
        knowledge=KnowledgeTool(),
        telemetry=TelemetryTool(),
        executor=RemediationExecutor(_CLUSTER),
    )

    def provider(_: IncidentState) -> ApprovalDecision:
        return ApprovalDecision(approved=auto_approve, approver="api", reason="via API")

    supervisor.run(state, provider)
    _STORE[state.id] = state
    return state


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> IncidentState:
    if incident_id not in _STORE:
        raise HTTPException(status_code=404, detail="unknown incident")
    return _STORE[incident_id]
