from __future__ import annotations

from app.llm.base import LLMClient
from app.orchestration.state import IncidentState
from app.tools.schemas import RemediationPlan

SYSTEM = (
    "You are the Remediation Planner. Propose the minimal safe set of actions "
    "to resolve the incident. Any medium/high-risk action MUST require approval."
)


def plan(state: IncidentState, llm: LLMClient) -> RemediationPlan:
    user = f"Diagnosis: {state.diagnosis.model_dump() if state.diagnosis else {}}"
    return llm.generate(system=SYSTEM, user=user, output_model=RemediationPlan)
