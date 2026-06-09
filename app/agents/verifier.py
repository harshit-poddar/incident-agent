from __future__ import annotations

from app.llm.base import LLMClient
from app.orchestration.state import IncidentState
from app.schemas.incident import Verification
from app.tools.telemetry import TelemetryTool

SYSTEM = (
    "You are the Verifier agent. Confirm whether the incident is resolved based "
    "on post-remediation telemetry. Be conservative: only report resolved if "
    "metrics are clearly back to normal."
)


def verify(state: IncidentState, llm: LLMClient, telemetry: TelemetryTool) -> Verification:
    svc = state.detection.affected_service if state.detection else state.signal.service
    metrics = telemetry.query_metrics(svc)
    user = f"Post-remediation metrics for {svc}: {metrics}"
    return llm.generate(system=SYSTEM, user=user, output_model=Verification)
