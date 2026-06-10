"""FastAPI surface for the agent with a REAL async human-approval gate.

Run:  uvicorn app.main:app --reload

Flow:
  POST /incidents              -> runs detect/diagnose/plan, then PAUSES at the
                                  gate (status AWAITING_APPROVAL) and persists.
  POST /incidents/{id}/approve -> a human approves/rejects; the graph RESUMES
                                  (remediate + verify) and persists the result.
  GET  /incidents/{id}         -> fetch current state + full audit trail.

State lives in an IncidentStore (in-memory by default, Postgres via
STORE_MODE=postgres) so it survives between the pause and the resume."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.llm.factory import get_llm_client
from app.orchestration.state import IncidentState, IncidentStatus
from app.orchestration.store import get_incident_store
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Signal
from app.telemetry.gpu import get_gpu_monitor
from app.telemetry.metrics import GpuMetrics, ServiceMetrics
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool

app = FastAPI(title="Autonomous incident agent (AGENTS_026)")

# Shared singletons: the sandbox cluster must persist between the POST that
# injects the fault and the /approve that remediates it; the store keeps the
# paused incident alive across those two requests.
_STORE = get_incident_store()
_CLUSTER = MockCluster()


class ApproveRequest(BaseModel):
    approved: bool = True
    approver: str = "human"
    reason: str | None = None


def _build_supervisor() -> Supervisor:
    return Supervisor(
        llm=get_llm_client(),
        knowledge=KnowledgeTool(),
        telemetry=TelemetryTool(),
        executor=RemediationExecutor(_CLUSTER),
    )


@app.post("/incidents")
def trigger(signal: Signal) -> IncidentState:
    """Open an incident and run the graph up to the approval gate."""
    _CLUSTER.register(signal.service)
    _CLUSTER.inject_fault(signal.service)
    state = IncidentState(signal=signal)
    state = _build_supervisor().run_to_gate(state)
    _STORE.save(state)
    return state


@app.post("/incidents/{incident_id}/approve")
def approve(incident_id: str, decision: ApproveRequest) -> IncidentState:
    """Resolve the human-approval gate and resume the graph."""
    state = _STORE.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    if state.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"incident is {state.status.value}, not awaiting approval",
        )
    resolved = _build_supervisor().resume(
        state,
        ApprovalDecision(
            approved=decision.approved,
            approver=decision.approver,
            reason=decision.reason,
        ),
    )
    _STORE.save(resolved)
    return resolved


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> IncidentState:
    state = _STORE.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    return state


@app.get("/incidents")
def list_incidents() -> list[str]:
    return _STORE.list_ids()


@app.get("/telemetry/gpu")
def gpu_telemetry() -> list[GpuMetrics]:
    """The MI300X self-monitor: the agent reporting on the hardware it runs on."""
    return get_gpu_monitor().sample()


@app.get("/telemetry/service/{service}")
def service_telemetry(service: str) -> ServiceMetrics:
    return TelemetryTool().query_metrics(service)
