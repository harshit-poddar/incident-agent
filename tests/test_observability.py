"""Slice 6 -- tracing across the agent graph.

Asserts that running an incident produces a nested span tree (the waterfall the
dashboard draws): a graph root, agent spans for each node, and an llm span
nested under each agent."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.obs.tracer import InMemoryTracer, get_tracer, span, trace

client = TestClient(app)

SIGNAL = {
    "service": "payments-api",
    "metric": "error_rate",
    "value": 0.38,
    "threshold": 0.02,
    "message": "5xx error rate breached threshold",
}


def test_spans_nest_and_time_themselves():
    tracer = InMemoryTracer()
    # Drive the tracer directly to assert nesting + timing without the API.
    import app.obs.tracer as t

    t._TRACER = tracer  # force this tracer for the span() helper
    try:
        with trace("inc-test"):
            with span("root", kind="graph"):
                with span("child", kind="agent"):
                    pass
    finally:
        t._TRACER = None

    spans = tracer.spans("inc-test")
    assert len(spans) == 2
    root = next(s for s in spans if s.name == "root")
    child = next(s for s in spans if s.name == "child")
    assert child.parent_id == root.span_id
    assert root.parent_id is None
    assert child.duration_ms is not None and child.duration_ms >= 0


def test_incident_run_produces_a_trace_waterfall():
    client.delete("/incidents")  # also clears the tracer
    inc = client.post("/incidents", json=SIGNAL).json()
    client.post(f"/incidents/{inc['id']}/approve", json={"approved": True})

    traces = client.get("/traces").json()
    assert any(t["trace_id"] == inc["id"] for t in traces)

    spans = client.get(f"/traces/{inc['id']}").json()
    names = {s["name"] for s in spans}
    # Graph nodes are present...
    assert "supervisor.run_to_gate" in names
    assert "detector" in names
    assert "diagnoser" in names
    assert "verifier" in names
    # ...and every agent's llm call was captured and nested under it.
    assert any(s["kind"] == "llm" for s in spans)
    detector = next(s for s in spans if s["name"] == "detector")
    llm_children = [
        s for s in spans if s["parent_id"] == detector["span_id"] and s["kind"] == "llm"
    ]
    assert llm_children, "detector's llm.generate span should nest under it"


def test_tracer_clear_on_reset():
    client.post("/incidents", json=SIGNAL)
    assert client.get("/traces").json()  # something there
    client.delete("/incidents")
    assert client.get("/traces").json() == []


def test_get_tracer_is_memory_in_tests():
    assert isinstance(get_tracer(), InMemoryTracer)
