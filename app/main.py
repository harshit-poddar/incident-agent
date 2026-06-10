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

import asyncio
import json
import pathlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.fixer import Fixer
from app.config import settings
from app.github.client import get_github_client
from app.github.schemas import WorkflowRun
from app.github.webhook import parse_workflow_run, verify_signature
from app.llm.factory import get_llm_client
from app.obs.tracer import SpanRecord, get_tracer
from app.orchestration.state import IncidentState, IncidentStatus
from app.orchestration.store import get_incident_store
from app.orchestration.supervisor import Supervisor
from app.pipeline.logsource import MockPipelineLogSource
from app.pipeline.monitor import LogMonitor
from app.schemas.incident import Signal
from app.telemetry.gpu import get_gpu_monitor
from app.telemetry.metrics import GpuMetrics, ServiceMetrics
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool

# Statuses past the point of no return -- a service whose only incidents are all
# in one of these is "closed", so a fresh signal should open a NEW incident.
_TERMINAL = {IncidentStatus.RESOLVED, IncidentStatus.REJECTED, IncidentStatus.FAILED}

app = FastAPI(title="Autonomous incident agent (AGENTS_026)")

# Shared singletons: the sandbox cluster must persist between the POST that
# injects the fault and the /approve that remediates it; the store keeps the
# paused incident alive across those two requests.
_STORE = get_incident_store()
_CLUSTER = MockCluster()
_WEB_DIR = pathlib.Path(__file__).parent / "web"
# The React dashboard (Slice 7), built to static assets. If it exists we serve
# it; otherwise we fall back to the self-contained vanilla dashboard, so the API
# and tests work with no frontend build present.
_FRONTEND_DIST = pathlib.Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    # Vite emits assets under /static/* (base in vite.config.js); mount them.
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIST)), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    """The ops dashboard. Serves the built React app when present, else the
    legacy single-file dashboard."""
    react_index = _FRONTEND_DIST / "index.html"
    if react_index.is_file():
        return react_index.read_text(encoding="utf-8")
    return (_WEB_DIR / "index.html").read_text(encoding="utf-8")


class ApproveRequest(BaseModel):
    approved: bool = True
    approver: str = "human"
    reason: str | None = None


def _build_supervisor() -> Supervisor:
    # The executor always carries a GitHub client (mock by default, no network)
    # so a resumed OPEN_PR incident can open its PR through this same path.
    return Supervisor(
        llm=get_llm_client(),
        knowledge=KnowledgeTool(),
        telemetry=TelemetryTool(),
        executor=RemediationExecutor(_CLUSTER, get_github_client()),
    )


def _open_ci_incident(run: WorkflowRun) -> IncidentState:
    """Run the agent graph for a failed CI run: pull the run logs, detect,
    diagnose, and have the Fixer propose a PR -- pausing at the approval gate.
    The PR is opened (gated) only after a human approves in /approve."""
    github = get_github_client()
    logs = github.fetch_run_logs(run.repo, run.run_id)
    signal = Signal(
        service="payments-api",
        metric="ci_failure",
        value=1.0,
        threshold=0.0,
        message=f"workflow '{run.name}' failed on {run.head_branch}\n{logs[:500]}",
    )
    fixer = Fixer(github, run.repo, run.head_branch, settings.github_target_file)
    supervisor = Supervisor(
        llm=get_llm_client(),
        knowledge=KnowledgeTool(),
        telemetry=TelemetryTool(),
        executor=RemediationExecutor(_CLUSTER, github),
        planner_fn=fixer.plan,
    )
    _CLUSTER.register(signal.service)
    _CLUSTER.inject_fault(signal.service)
    state = IncidentState(signal=signal)
    state = supervisor.run_to_gate(state)
    _STORE.save(state)
    return state


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


@app.get("/incidents/latest")
def latest_incident() -> IncidentState | None:
    """The most recently updated incident, or null. The dashboard polls this to
    pick up incidents opened out-of-band by the GitHub webhook."""
    ids = _STORE.list_ids()
    return _STORE.get(ids[0]) if ids else None


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> IncidentState:
    state = _STORE.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    return state


@app.get("/incidents")
def list_incidents() -> list[str]:
    return _STORE.list_ids()


@app.delete("/incidents")
def reset_incidents() -> dict:
    """Clear all incidents -- lets the demo be re-run from a clean slate."""
    cleared = _STORE.clear()
    get_tracer().clear()
    return {"cleared": cleared}


@app.get("/traces")
def list_traces() -> list[dict]:
    """Slice 6 -- one summary row per incident trace (newest first). The
    dashboard lists these and lets you open a trace's span waterfall."""
    return get_tracer().traces()


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> list[SpanRecord]:
    """All spans for one incident, time-ordered -- the data behind the
    waterfall: detector -> llm, diagnoser -> rag + llm, planner -> llm, etc."""
    return get_tracer().spans(trace_id)


def _open_incident_for(service: str) -> str | None:
    """Return the id of a still-open incident for this service, if any -- so the
    log monitor de-duplicates instead of opening a second incident for a fault
    that is already being handled."""
    for iid in _STORE.list_ids():
        st = _STORE.get(iid)
        if st and st.signal.service == service and st.status not in _TERMINAL:
            return st.id
    return None


def _sse(payload: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/pipeline/stream")
async def pipeline_stream(pace: float = 1.0) -> StreamingResponse:
    """Stream live CI/runtime logs as Server-Sent Events. A LogMonitor watches
    the stream; when it spots an SLO-breach signature it AUTO-OPENS an incident
    (runs detect -> diagnose -> plan to the approval gate) and pushes the paused
    IncidentState down the same stream -- which the dashboard renders in the
    lifecycle panel. `pace` scales the inter-line delay (0 = instant, for tests).

    Event types: {"type":"log", ...LogLine}, {"type":"incident","incident":...},
    {"type":"done"}."""
    source = MockPipelineLogSource()
    monitor = LogMonitor()

    async def gen():
        triggered = False
        for line, delay in source.lines():
            await asyncio.sleep(delay * pace)
            yield _sse({"type": "log", **line.model_dump()})
            if triggered:
                continue
            signal = monitor.inspect(line)
            if signal is None:
                continue
            triggered = True

            existing = _open_incident_for(signal.service)
            if existing is not None:
                yield _sse({
                    "type": "log", "ts": line.ts, "stage": "monitor", "level": "INFO",
                    "service": signal.service,
                    "msg": f"incident {existing} already open for {signal.service} — not duplicating",
                })
                yield _sse({"type": "incident", "incident": _STORE.get(existing).model_dump(mode="json")})
                continue

            yield _sse({
                "type": "log", "ts": line.ts, "stage": "monitor", "level": "WARN",
                "service": signal.service,
                "msg": f"anomaly confirmed — no open incident for {signal.service}, auto-opening",
            })
            # Open the incident and run the agent graph to the approval gate.
            # run_to_gate is sync (and blocking in live mode), so offload it to a
            # thread to keep the event loop -- and the log stream -- responsive.
            _CLUSTER.register(signal.service)
            _CLUSTER.inject_fault(signal.service)
            state = IncidentState(signal=signal)
            state = await asyncio.to_thread(_build_supervisor().run_to_gate, state)
            _STORE.save(state)
            yield _sse({
                "type": "log", "ts": line.ts, "stage": "agent", "level": "OK",
                "service": signal.service,
                "msg": f"incident {state.id} opened — agents engaged, awaiting human approval",
            })
            yield _sse({"type": "incident", "incident": state.model_dump(mode="json")})
        yield _sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/github/webhook")
async def github_webhook(request: Request) -> dict:
    """Receive a GitHub `workflow_run` event. On a failed run, auto-open an
    incident: pull the logs, diagnose, and have the Fixer propose a PR -- paused
    at the approval gate. The PR is opened only after a human approves."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(body, sig, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="bad signature")

    payload = json.loads(body or b"{}")
    run = parse_workflow_run(payload)
    if run is None:
        return {"ignored": "not a failed workflow_run"}

    existing = _open_incident_for("payments-api")
    if existing is not None:
        return {"incident_id": existing, "deduped": True}

    state = await asyncio.to_thread(_open_ci_incident, run)
    return {"incident_id": state.id, "status": state.status.value}


@app.post("/github/simulate")
async def github_simulate() -> IncidentState:
    """Offline stand-in for the webhook: synthesise a failed CI run and drive
    the same path. Lets the GitHub demo run with no tunnel, no PAT, no network
    -- the bulletproof fallback if wifi or the runner is flaky on stage."""
    run = WorkflowRun(
        run_id=482,
        repo=settings.github_repo,
        name="deploy",
        head_branch=settings.github_base_branch,
        head_sha="a3f9c2e",
        conclusion="failure",
        html_url=f"https://github.com/{settings.github_repo}/actions/runs/482",
    )
    return await asyncio.to_thread(_open_ci_incident, run)


@app.get("/telemetry/gpu")
def gpu_telemetry() -> list[GpuMetrics]:
    """The MI300X self-monitor: the agent reporting on the hardware it runs on."""
    return get_gpu_monitor().sample()


@app.get("/telemetry/service/{service}")
def service_telemetry(service: str) -> ServiceMetrics:
    return TelemetryTool().query_metrics(service)
