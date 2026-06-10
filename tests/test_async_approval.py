from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.state import IncidentState, IncidentStatus
from app.orchestration.store import InMemoryIncidentStore
from app.schemas.incident import Signal

client = TestClient(app)

SIGNAL = {
    "service": "payments-api",
    "metric": "error_rate",
    "value": 0.38,
    "threshold": 0.02,
    "message": "5xx error rate breached threshold",
}


def test_post_incident_pauses_at_gate():
    r = client.post("/incidents", json=SIGNAL)
    assert r.status_code == 200
    body = r.json()
    # The graph stopped at the gate -- it did NOT auto-remediate.
    assert body["status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert body["plan"] is not None
    assert body["remediation_results"] == []
    assert body["verification"] is None


def test_approve_resumes_to_resolved():
    inc_id = client.post("/incidents", json=SIGNAL).json()["id"]
    r = client.post(f"/incidents/{inc_id}/approve", json={"approved": True, "approver": "alice"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == IncidentStatus.RESOLVED.value
    assert body["verification"]["resolved"] is True
    assert body["remediation_results"]  # remediation actually ran
    # The human approval is recorded in the audit trail.
    actors = [e["actor"] for e in body["audit"]]
    assert "human" in actors


def test_reject_blocks_remediation():
    inc_id = client.post("/incidents", json=SIGNAL).json()["id"]
    r = client.post(f"/incidents/{inc_id}/approve", json={"approved": False, "approver": "bob"})
    body = r.json()
    assert body["status"] == IncidentStatus.REJECTED.value
    assert body["remediation_results"] == []
    assert body["verification"] is None


def test_double_approve_is_conflict():
    inc_id = client.post("/incidents", json=SIGNAL).json()["id"]
    client.post(f"/incidents/{inc_id}/approve", json={"approved": True})
    # Second approval -- incident is no longer awaiting approval.
    r = client.post(f"/incidents/{inc_id}/approve", json={"approved": True})
    assert r.status_code == 409


def test_approve_unknown_incident_404():
    r = client.post("/incidents/does-not-exist/approve", json={"approved": True})
    assert r.status_code == 404


def test_get_and_list_incidents():
    inc_id = client.post("/incidents", json=SIGNAL).json()["id"]
    assert client.get(f"/incidents/{inc_id}").status_code == 200
    assert inc_id in client.get("/incidents").json()
    assert client.get("/incidents/nope").status_code == 404


def test_in_memory_store_isolates_copies():
    store = InMemoryIncidentStore()
    state = IncidentState(signal=Signal(**SIGNAL))
    store.save(state)
    # Mutating the original after save must not affect the stored copy.
    state.status = IncidentStatus.FAILED
    assert store.get(state.id).status == IncidentStatus.DETECTED
