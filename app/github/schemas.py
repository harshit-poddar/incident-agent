from __future__ import annotations

from pydantic import BaseModel


class WorkflowRun(BaseModel):
    """The slice of a GitHub `workflow_run` webhook payload we act on."""

    run_id: int
    repo: str            # "owner/name"
    name: str            # workflow name, e.g. "deploy"
    head_branch: str
    head_sha: str
    conclusion: str | None = None   # success | failure | cancelled | ...
    html_url: str | None = None


class PullRequestRef(BaseModel):
    """A pointer to a PR the agent opened, surfaced to the dashboard/audit."""

    number: int
    url: str
    branch: str
