from __future__ import annotations

import hashlib
import hmac

from app.github.schemas import WorkflowRun


def verify_signature(body: bytes, header: str | None, secret: str) -> bool:
    """Verify GitHub's `X-Hub-Signature-256` HMAC. If no secret is configured
    we skip verification (dev/demo); in production set github_webhook_secret so
    only GitHub can open incidents."""
    if not secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, header)


def parse_workflow_run(payload: dict) -> WorkflowRun | None:
    """Extract the bits we act on from a `workflow_run` webhook payload.
    Returns None if the payload is not a completed, failed run."""
    if payload.get("action") != "completed":
        return None
    run = payload.get("workflow_run") or {}
    if run.get("conclusion") != "failure":
        return None
    repo = (payload.get("repository") or {}).get("full_name", "")
    return WorkflowRun(
        run_id=run.get("id", 0),
        repo=repo,
        name=run.get("name", ""),
        head_branch=run.get("head_branch", ""),
        head_sha=run.get("head_sha", ""),
        conclusion=run.get("conclusion"),
        html_url=run.get("html_url"),
    )
