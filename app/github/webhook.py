from __future__ import annotations

import hashlib
import hmac
import re

from app.github.schemas import WorkflowRun

# Workflow names whose FAILURE means "a security scan tripped", so the incident
# should be routed to the fine-tuned Java vuln-fixer rather than the generic CI
# fixer. Matched case-insensitively as substrings of the workflow name.
_SECURITY_WORKFLOW_HINTS = ("security", "sast", "codeql", "vuln", "scan")

_CWE_RE = re.compile(r"\bCWE-\d+\b", re.IGNORECASE)
_JAVA_FILE_RE = re.compile(r"[\w./\-]+\.java\b")


def is_security_failure(run: WorkflowRun, logs: str = "") -> bool:
    """True if a failed run looks like a SAST/security-scan finding -- by the
    workflow name (security-scan, codeql, ...) or by a CWE id appearing in its
    logs. This is the routing switch: security -> JavaVulnFixer, else -> Fixer."""
    name = (run.name or "").lower()
    if any(hint in name for hint in _SECURITY_WORKFLOW_HINTS):
        return True
    return bool(_CWE_RE.search(logs))


def parse_sast_finding(logs: str) -> tuple[str | None, str | None]:
    """Pull the (CWE id, Java file path) out of scan logs, if present. This is
    the auto-detection the JavaVulnFixer's TODO asked for: a real scanner names
    both in its output. Returns (None, None) for whichever it cannot find, so the
    caller can fall back to configured defaults."""
    cwe = _CWE_RE.search(logs)
    java = _JAVA_FILE_RE.search(logs)
    return (cwe.group(0).upper() if cwe else None, java.group(0) if java else None)


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
