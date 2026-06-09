from __future__ import annotations

from typing import Callable

from app.agents import detector, diagnoser, planner, verifier
from app.llm.base import LLMClient
from app.orchestration.state import IncidentState, IncidentStatus
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import GateError, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool

# Returns an approval decision for the current state. In tests/demo this is an
# auto-approver; behind the API it is the human-in-the-loop gate.
ApprovalProvider = Callable[[IncidentState], ApprovalDecision]


class Supervisor:
    """Coordinates the agent graph:
    detect -> diagnose -> plan -> [human gate] -> remediate -> verify."""

    def __init__(
        self,
        llm: LLMClient,
        knowledge: KnowledgeTool,
        telemetry: TelemetryTool,
        executor: RemediationExecutor,
    ) -> None:
        self.llm = llm
        self.knowledge = knowledge
        self.telemetry = telemetry
        self.executor = executor

    def run(self, state: IncidentState, approval_provider: ApprovalProvider) -> IncidentState:
        # 1. Detect
        state.detection = detector.detect(state.signal, self.llm)
        state.log("detector", "detection", state.detection.summary)
        if not state.detection.is_anomaly:
            state.status = IncidentStatus.RESOLVED
            state.log("supervisor", "no_anomaly", "Signal judged benign; closing.")
            return state

        # 2. Diagnose
        state.status = IncidentStatus.DIAGNOSING
        state.diagnosis = diagnoser.diagnose(state, self.llm, self.knowledge)
        state.log("diagnoser", "diagnosis", state.diagnosis.root_cause)

        # 3. Plan
        state.plan = planner.plan(state, self.llm)
        state.status = IncidentStatus.PLANNED
        state.log("planner", "plan", state.plan.summary)

        # 4. Human-in-the-loop gate
        if state.plan.requires_approval:
            state.status = IncidentStatus.AWAITING_APPROVAL
            state.log("supervisor", "awaiting_approval", "Remediation needs human approval.")
            decision = approval_provider(state)
            state.approval = decision
            actor = "auto" if decision.approver == "auto" else "human"
            state.log(
                actor,
                "approval" if decision.approved else "rejection",
                decision.reason,
            )
            if not decision.approved:
                state.status = IncidentStatus.REJECTED
                return state
        else:
            state.approval = ApprovalDecision(
                approved=True, approver="auto", reason="low-risk auto-approved"
            )

        # 5. Remediate (gated executor double-checks approval)
        state.status = IncidentStatus.REMEDIATING
        try:
            for action in state.plan.actions:
                result = self.executor.execute(action, state.approval)
                state.remediation_results.append(result)
                state.log("remediation", "executed", result.output)
                if result.success and action.target:
                    self.telemetry.mark_recovered(action.target)
        except GateError as e:
            state.status = IncidentStatus.FAILED
            state.log("remediation", "blocked", str(e))
            return state

        # 6. Verify
        state.status = IncidentStatus.VERIFYING
        state.verification = verifier.verify(state, self.llm, self.telemetry)
        state.log("verifier", "verification", state.verification.summary)
        state.status = (
            IncidentStatus.RESOLVED
            if state.verification.resolved
            else IncidentStatus.FAILED
        )
        return state
