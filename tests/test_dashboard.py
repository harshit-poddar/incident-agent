from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dashboard_served_at_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Branding is present whether we serve the React build or the legacy page.
    assert "AGENTS_026" in r.text
    # It is a real HTML document mounting an app (React #root) or the legacy UI.
    assert "<div id=\"root\">" in r.text or "Trigger incident" in r.text


def test_dashboard_drives_real_api():
    # The buttons in the page call these endpoints -- smoke-test the wiring.
    inc = client.post(
        "/incidents",
        json={
            "service": "payments-api",
            "metric": "error_rate",
            "value": 0.38,
            "threshold": 0.02,
            "message": "x",
        },
    ).json()
    assert inc["status"] == "awaiting_approval"
    done = client.post(f"/incidents/{inc['id']}/approve", json={"approved": True}).json()
    assert done["status"] == "resolved"
    assert client.get("/telemetry/gpu").json()[0]["vram_total_gb"] == 192.0


def test_reset_clears_incidents():
    client.post(
        "/incidents",
        json={
            "service": "payments-api",
            "metric": "error_rate",
            "value": 0.38,
            "threshold": 0.02,
            "message": "x",
        },
    )
    assert len(client.get("/incidents").json()) > 0
    r = client.delete("/incidents")
    assert r.status_code == 200
    assert r.json()["cleared"] >= 1
    assert client.get("/incidents").json() == []
