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
    detect -> diagnose -> plan -> [human gate] -> remediate -> verify.

    The graph is split at the gate so it can PAUSE for real async approval:
      run_to_gate()  runs detect/diagnose/plan and stops at AWAITING_APPROVAL
      resume()       applies a decision, then remediates + verifies
    run() chains both for the synchronous (test/demo) path."""

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

    def run_to_gate(self, state: IncidentState) -> IncidentState:
        """Run up to (and stopping at) the human-approval gate.

        Terminal outcomes returned directly: RESOLVED (benign signal).
        Paused outcome: AWAITING_APPROVAL (caller must later call resume()).
        Low-risk plans that need no approval are auto-approved and run through
        to completion here."""
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

        # 4. Pause at the human-in-the-loop gate.
        if state.plan.requires_approval:
            state.status = IncidentStatus.AWAITING_APPROVAL
            state.log("supervisor", "awaiting_approval", "Remediation needs human approval.")
            return state

        # Low-risk: no human needed -- auto-approve and run to completion.
        return self.resume(
            state,
            ApprovalDecision(approved=True, approver="auto", reason="low-risk auto-approved"),
        )

    def resume(self, state: IncidentState, decision: ApprovalDecision) -> IncidentState:
        """Apply an approval decision and finish the graph: remediate + verify.
        A rejection stops here. The gated executor independently re-checks the
        decision -- defense in depth, never weakened."""
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

    def run(self, state: IncidentState, approval_provider: ApprovalProvider) -> IncidentState:
        """Synchronous end-to-end run (tests/skeleton). Pauses at the gate, then
        immediately resolves the decision via the supplied provider."""
        state = self.run_to_gate(state)
        if state.status == IncidentStatus.AWAITING_APPROVAL:
            state = self.resume(state, approval_provider(state))
        return state
