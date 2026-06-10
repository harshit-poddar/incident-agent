from __future__ import annotations

from app.config import settings
from app.github.client import GitHubClient
from app.tools.schemas import (
    ApprovalDecision,
    RemediationAction,
    RemediationActionType,
    RemediationResult,
)


class MockCluster:
    """In-memory stand-in for the sandboxed Docker/K8s environment."""

    def __init__(self) -> None:
        self.services: dict[str, str] = {}

    def register(self, service: str) -> None:
        self.services[service] = "healthy"

    def inject_fault(self, service: str) -> None:
        self.services[service] = "unhealthy"

    def restart(self, service: str) -> str:
        self.services[service] = "healthy"
        return f"{service} restarted; status=healthy"


class GateError(PermissionError):
    pass


class RemediationExecutor:
    """Side-effectful tool. Refuses to act without an approved decision -- the
    human-in-the-loop gate is enforced HERE as defense in depth, not only in
    the orchestration layer. Opening a PR is just another gated action, so the
    same single check protects code changes and infra changes alike."""

    def __init__(self, cluster: MockCluster, github: GitHubClient | None = None) -> None:
        self._cluster = cluster
        self._github = github

    def execute(
        self, action: RemediationAction, approval: ApprovalDecision
    ) -> RemediationResult:
        if not approval.approved:
            raise GateError("Remediation attempted without approval.")
        if action.action == RemediationActionType.RESTART_SERVICE:
            out = self._cluster.restart(action.target)
            return RemediationResult(action=action, success=True, output=out)
        if action.action == RemediationActionType.OPEN_PR:
            if self._github is None or action.fix is None:
                return RemediationResult(
                    action=action,
                    success=False,
                    output="OPEN_PR requires a GitHub client and a proposed fix.",
                )
            pr = self._github.open_pr(action.target, settings.github_base_branch, action.fix)
            return RemediationResult(
                action=action,
                success=True,
                output=f"opened PR #{pr.number} ({pr.branch}): {pr.url}",
            )
        return RemediationResult(
            action=action,
            success=False,
            output=f"Unsupported action {action.action} in skeleton",
        )
