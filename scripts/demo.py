"""Interactive golden-path demo: drive the full incident loop in the terminal,
pausing at the human-approval gate for a real keypress. No server, no GPU, no
external services required (mock mode).

    python scripts/demo.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.llm.factory import get_llm_client
from app.orchestration.state import IncidentState, IncidentStatus
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Signal
from app.telemetry.gpu import get_gpu_monitor
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m"


def hdr(s: str) -> None:
    print("\n" + c("1;36", "== " + s + " =="))


def main() -> None:
    cluster = MockCluster()
    cluster.register("payments-api")
    cluster.inject_fault("payments-api")
    supervisor = Supervisor(
        llm=get_llm_client(),
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
    print(c("1;37", "\nAGENTS_026 - Autonomous Incident Agent  (golden-path demo)"))
    print(c("90", "detect -> diagnose -> plan -> [human gate] -> remediate -> verify"))

    hdr("Incoming signal")
    print(f"  {signal.service}  {signal.metric}={signal.value} (threshold {signal.threshold})")
    print(f"  {signal.message}")

    # --- run up to the human gate ---
    state = supervisor.run_to_gate(IncidentState(signal=signal))

    hdr("Detector")
    print(f"  {state.detection.summary}  [{state.detection.severity.value}, "
          f"conf {state.detection.confidence:.0%}]")
    hdr("Diagnoser (RAG over runbooks)")
    print(f"  root cause: {state.diagnosis.root_cause}")
    for ev in state.diagnosis.evidence:
        print(c("90", f"    - {ev}"))
    hdr("Planner")
    print(f"  {state.plan.summary}")
    for a in state.plan.actions:
        print(f"    {a.action.value} -> {a.target}  (risk: {a.risk})")

    # --- the human-in-the-loop gate ---
    if state.status == IncidentStatus.AWAITING_APPROVAL:
        hdr("HUMAN APPROVAL GATE")
        ans = input(c("1;33", "  Approve remediation? [Y/n] ")).strip().lower()
        approved = ans in ("", "y", "yes")
        decision = ApprovalDecision(
            approved=approved, approver="demo-operator",
            reason="approved at demo" if approved else "rejected at demo",
        )
        state = supervisor.resume(state, decision)

    # --- outcome ---
    hdr("Outcome")
    if state.verification:
        print(f"  verifier: {state.verification.summary}")
    color = "1;32" if state.status == IncidentStatus.RESOLVED else "1;31"
    print(c(color, f"  STATUS: {state.status.value.upper()}"))
    print(c("90", f"  cluster: {cluster.services}"))

    hdr("Audit trail")
    for e in state.audit:
        print(f"  [{e.actor:>12}] {e.event:<18} {c('90', e.detail or '')}")

    hdr("MI300X self-monitor")
    for g in get_gpu_monitor().sample():
        print(f"  {g.device}: util {g.gpu_util_pct:.0f}%  "
              f"VRAM {g.vram_used_gb:.0f}/{g.vram_total_gb:.0f} GB  "
              f"{g.temp_c:.0f} C  {g.power_w:.0f} W")
    print()


if __name__ == "__main__":
    main()
