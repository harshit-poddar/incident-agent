from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.github.client import MockGitHubClient
from app.github.webhook import parse_workflow_run, verify_signature
from app.main import app
from app.schemas.incident import ProposedFix

client = TestClient(app)


def test_open_pr_is_gated_and_runs_after_approval():
    client.delete("/incidents")

    # Simulate a failed CI run -> agent diagnoses and proposes a PR, paused.
    state = client.post("/github/simulate").json()
    assert state["status"] == "awaiting_approval"
    action = state["plan"]["actions"][0]
    assert action["action"] == "open_pr"
    assert action["fix"]["file_path"] == "payments/handler.py"
    assert "lru_cache" in action["fix"]["new_content"]  # the proposed fix is real

    # Approve -> the PR is opened (gated side effect) and the incident resolves.
    done = client.post(f"/incidents/{state['id']}/approve", json={"approved": True}).json()
    assert done["status"] == "resolved"
    out = done["remediation_results"][0]["output"]
    assert "opened PR #" in out
    assert "github.com" in out


def test_rejected_fix_opens_no_pr():
    client.delete("/incidents")
    state = client.post("/github/simulate").json()
    done = client.post(
        f"/incidents/{state['id']}/approve", json={"approved": False}
    ).json()
    assert done["status"] == "rejected"
    assert done["remediation_results"] == []  # nothing executed -> no PR


def test_mock_github_client_records_pr():
    gh = MockGitHubClient()
    fix = ProposedFix(
        file_path="a.py", new_content="x=1\n", pr_title="t", pr_body="b", rationale="r"
    )
    pr = gh.open_pr("owner/repo", "main", fix)
    assert pr.url.startswith("https://github.com/owner/repo/pull/")
    assert gh.opened == [pr]


def test_webhook_parses_only_failed_runs():
    ok = {"action": "completed", "workflow_run": {"conclusion": "success", "id": 1}}
    assert parse_workflow_run(ok) is None

    fail = {
        "action": "completed",
        "repository": {"full_name": "owner/repo"},
        "workflow_run": {
            "id": 7,
            "name": "deploy",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "abc",
        },
    }
    run = parse_workflow_run(fail)
    assert run is not None and run.run_id == 7 and run.repo == "owner/repo"


def test_webhook_signature_verification():
    secret = "s3cr3t"
    body = b'{"hello":"world"}'
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, good, secret) is True
    assert verify_signature(body, "sha256=deadbeef", secret) is False
    # No secret configured -> skip verification (dev/demo).
    assert verify_signature(body, None, "") is True


def test_webhook_endpoint_opens_incident():
    client.delete("/incidents")
    payload = {
        "action": "completed",
        "repository": {"full_name": "owner/repo"},
        "workflow_run": {
            "id": 99,
            "name": "deploy",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "abc",
        },
    }
    r = client.post("/github/webhook", content=json.dumps(payload))
    assert r.status_code == 200
    body = r.json()
    assert "incident_id" in body
    # And it shows up as the latest incident for the dashboard to pick up.
    latest = client.get("/incidents/latest").json()
    assert latest["id"] == body["incident_id"]
    assert latest["status"] == "awaiting_approval"
