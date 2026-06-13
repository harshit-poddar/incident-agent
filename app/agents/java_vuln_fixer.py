from __future__ import annotations

from app.github.client import GitHubClient
from app.llm.base import LLMClient
from app.obs.tracer import span
from app.orchestration.state import IncidentState
from app.schemas.incident import ProposedFix
from app.tools.schemas import RemediationAction, RemediationActionType, RemediationPlan
from app.tools.vuln_fixer import CWE_DESCRIPTIONS, VulnFixerClient


class JavaVulnFixer:
    """Security analogue of the CI-failure `Fixer`. When a SAST scanner flags a
    Java file with one of the trained CWEs (89/78/22), this planner fetches the
    file, asks the fine-tuned 'vuln-fixer' model for a patched version, and wraps
    it as a gated OPEN_PR action -- the SAME human-approval gate and executor
    path that infra restarts and CI fixes go through. It drops into the
    Supervisor's `planner_fn` seam exactly like `Fixer`.

    The patch comes from the dedicated vuln-fixer model, not the general
    LLMClient, so `plan` ignores the injected `llm` -- it keeps the seam
    signature (state, llm) -> RemediationPlan so the swap is transparent.

    TODO: auto-detect the CWE from the scanner finding; for now the orchestrator
    passes it explicitly via the constructor."""

    def __init__(
        self,
        github: GitHubClient,
        vuln_fixer: VulnFixerClient,
        repo: str,
        ref: str,
        file_path: str,
        cwe: str,
    ) -> None:
        self._github = github
        self._vuln_fixer = vuln_fixer
        self._repo = repo
        self._ref = ref
        self._file_path = file_path
        self._cwe = cwe.strip().upper()

    def plan(self, state: IncidentState, llm: LLMClient) -> RemediationPlan:
        source = self._github.get_file(self._repo, self._file_path, self._ref)
        with span("tool.vuln_fixer", kind="tool", cwe=self._cwe, file=self._file_path):
            patched = self._vuln_fixer.fix(code=source, cwe=self._cwe)

        desc = CWE_DESCRIPTIONS.get(self._cwe, self._cwe)
        filename = self._file_path.rsplit("/", 1)[-1]
        fix = ProposedFix(
            file_path=self._file_path,
            new_content=patched,
            pr_title=f"fix(security): remediate {self._cwe} in {filename}",
            pr_body=(
                f"A security scan flagged **{self._cwe}** ({desc}) in "
                f"`{self._file_path}`.\n\n"
                "The fine-tuned `vuln-fixer` model produced a patched version that "
                "removes the vulnerability while preserving the class and method "
                "signatures. Review the diff before merging."
            ),
            rationale=f"Automated {self._cwe} remediation via the fine-tuned vuln-fixer model.",
        )
        return RemediationPlan(
            summary=f"Open PR: fix {self._cwe} in {self._file_path}",
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
