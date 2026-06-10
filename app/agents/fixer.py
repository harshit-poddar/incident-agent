from __future__ import annotations

from app.github.client import GitHubClient
from app.llm.base import LLMClient
from app.orchestration.state import IncidentState
from app.schemas.incident import ProposedFix
from app.tools.schemas import RemediationAction, RemediationActionType, RemediationPlan

SYSTEM = (
    "You are the Fixer agent. Given a diagnosis and the offending source file, "
    "propose the MINIMAL code change that fixes the root cause. Return the full "
    "new file content, a concise PR title, and a PR body explaining the fix. "
    "Do not change unrelated lines."
)


class Fixer:
    """A specialised planner for CI-failure incidents. Instead of restarting a
    service, it fetches the offending file, asks the LLM for a code fix, and
    wraps it as an OPEN_PR action -- a *gated* side effect, so the human reviews
    the diff before it is ever pushed.

    Its `plan` method matches the planner seam signature (state, llm) ->
    RemediationPlan, so it drops straight into the Supervisor in place of the
    default runtime planner."""

    def __init__(self, github: GitHubClient, repo: str, ref: str, file_path: str) -> None:
        self._github = github
        self._repo = repo
        self._ref = ref
        self._file_path = file_path

    def plan(self, state: IncidentState, llm: LLMClient) -> RemediationPlan:
        source = self._github.get_file(self._repo, self._file_path, self._ref)
        diagnosis = state.diagnosis.model_dump() if state.diagnosis else {}
        user = (
            f"Repo: {self._repo} (branch {self._ref})\n"
            f"Diagnosis: {diagnosis}\n"
            f"Offending file `{self._file_path}`:\n```\n{source}\n```"
        )
        fix = llm.generate(system=SYSTEM, user=user, output_model=ProposedFix)
        # Trust the diagnosis for the path if the model left it blank.
        if not fix.file_path:
            fix = fix.model_copy(update={"file_path": self._file_path})

        return RemediationPlan(
            summary=f"Open PR: {fix.pr_title}",
            requires_approval=True,
            actions=[
                RemediationAction(
                    action=RemediationActionType.OPEN_PR,
                    target=self._repo,
                    rationale=fix.rationale,
                    risk="medium",
                    fix=fix,
                )
            ],
        )
