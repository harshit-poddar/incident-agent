from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def test_pipeline_stream_auto_opens_incident():
    # Clean slate so the monitor auto-opens rather than de-duplicating.
    client.delete("/incidents")

    # pace=0 -> no inter-line sleeps, so the finite stream returns immediately.
    r = client.get("/pipeline/stream?pace=0")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    events = _events(r.text)
    types = [e["type"] for e in events]

    # The CI logs streamed, an incident was auto-opened, and the stream closed.
    assert "log" in types
    assert "incident" in types
    assert types[-1] == "done"

    # The OOM lead-up is in the log stream.
    assert any("OutOfMemoryError" in e.get("msg", "") for e in events if e["type"] == "log")

    # The auto-opened incident paused at the human-approval gate.
    inc = next(e["incident"] for e in events if e["type"] == "incident")
    assert inc["status"] == "awaiting_approval"
    assert inc["signal"]["service"] == "payments-api"

    # And it can be approved through to resolution like any other incident.
    done = client.post(f"/incidents/{inc['id']}/approve", json={"approved": True}).json()
    assert done["status"] == "resolved"


def test_pipeline_stream_dedupes_open_incident():
    client.delete("/incidents")
    # First run opens an incident and leaves it awaiting approval.
    first = _events(client.get("/pipeline/stream?pace=0").text)
    inc_id = next(e["incident"]["id"] for e in first if e["type"] == "incident")

    # Second run, with that incident still open, must NOT open a duplicate --
    # it points back at the existing one.
    second = _events(client.get("/pipeline/stream?pace=0").text)
    inc2 = next(e["incident"] for e in second if e["type"] == "incident")
    assert inc2["id"] == inc_id
    assert any("not duplicating" in e.get("msg", "") for e in second if e["type"] == "log")

    # Only one incident exists.
    assert client.get("/incidents").json() == [inc_id]
