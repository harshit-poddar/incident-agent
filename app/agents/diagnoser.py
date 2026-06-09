from __future__ import annotations

from app.llm.base import LLMClient
from app.orchestration.state import IncidentState
from app.schemas.incident import Diagnosis
from app.tools.knowledge import KnowledgeTool

SYSTEM = (
    "You are the Diagnoser agent. Determine the root cause using the detection "
    "and retrieved runbooks. Always cite concrete evidence."
)


def diagnose(state: IncidentState, llm: LLMClient, knowledge: KnowledgeTool) -> Diagnosis:
    summary = state.detection.summary if state.detection else ""
    runbooks = knowledge.search_runbooks("oom " + summary)
    user = (
        f"Detection: {state.detection.model_dump() if state.detection else {}}\n"
        f"Runbooks: {runbooks}"
    )
    return llm.generate(system=SYSTEM, user=user, output_model=Diagnosis)
