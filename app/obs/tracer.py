"""Tracing across the agent graph -- Slice 6 (observability).

Same seam philosophy as the rest of the system: agents/supervisor depend only
on the `span()` / `trace()` helpers; the concrete sink behind them is a single
env switch (`TRACE_MODE` = memory | otel).

  memory -> InMemoryTracer: a ring buffer the dashboard reads to draw a live
            span waterfall. Zero dependencies -- the default, always on.
  otel   -> the same in-memory tracer PLUS an OpenTelemetry exporter (console
            or OTLP), so the identical spans flow to a real collector in prod.

Spans nest via contextvars (exactly how OpenTelemetry propagates context), so
an `llm.generate` raised inside `diagnoser` is recorded as its child with no
plumbing through function signatures. `trace_id` is the incident id, which
groups every span raised while handling one incident into that incident's
trace."""
from __future__ import annotations

import contextvars
import time
from collections import deque
from contextlib import contextmanager
from typing import Iterator, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field

# High-resolution monotonic clock for span timing. time.time() has ~15 ms
# granularity on Windows, which ties sub-millisecond spans and breaks ordering
# in the waterfall; perf_counter is sub-microsecond. We keep an epoch anchor so
# the OpenTelemetry exporter can still emit correct Unix timestamps.
_PERF0 = time.perf_counter()
_EPOCH0 = time.time()


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def perf_ms_to_epoch_ns(perf_ms: float) -> int:
    """Map a perf_counter-based millisecond reading to Unix epoch nanoseconds."""
    offset_s = perf_ms / 1000.0 - _PERF0
    return int((_EPOCH0 + offset_s) * 1e9)


class SpanRecord(BaseModel):
    """One unit of work in the agent graph -- an OpenTelemetry-style span.

    `parent_id` nests spans into a tree (agent -> its llm call -> its tool
    call); the dashboard renders that tree as a waterfall. `trace_id` is the
    incident id."""

    span_id: str
    parent_id: str | None = None
    trace_id: str | None = None
    name: str
    kind: str = "graph"  # graph | agent | llm | tool
    start_ms: float
    end_ms: float | None = None
    duration_ms: float | None = None
    status: str = "ok"  # ok | error
    error: str | None = None
    attributes: dict = Field(default_factory=dict)


@runtime_checkable
class Tracer(Protocol):
    """The sink spans are recorded into. Implementations: InMemoryTracer (the
    dashboard substrate) and CompositeTracer (memory + OpenTelemetry export)."""

    def record(self, span: SpanRecord) -> None: ...
    def spans(self, trace_id: str | None = None) -> list[SpanRecord]: ...
    def traces(self) -> list[dict]: ...
    def clear(self) -> None: ...


class InMemoryTracer:
    """Always-on tracer: keeps the last N spans in a ring buffer and serves them
    to the dashboard. No dependencies -- the substrate every mode builds on."""

    def __init__(self, capacity: int = 2000) -> None:
        self._spans: deque[SpanRecord] = deque(maxlen=capacity)

    def record(self, span: SpanRecord) -> None:
        self._spans.append(span)

    def spans(self, trace_id: str | None = None) -> list[SpanRecord]:
        items = list(self._spans)
        if trace_id is not None:
            items = [s for s in items if s.trace_id == trace_id]
        return sorted(items, key=lambda s: s.start_ms)

    def traces(self) -> list[dict]:
        """One summary row per trace (incident), newest first: id, root name,
        wall-clock duration, span count, status."""
        by_trace: dict[str, list[SpanRecord]] = {}
        for s in self._spans:
            if s.trace_id is None:
                continue
            by_trace.setdefault(s.trace_id, []).append(s)
        out: list[dict] = []
        for tid, spans in by_trace.items():
            start = min(s.start_ms for s in spans)
            end = max((s.end_ms or s.start_ms) for s in spans)
            root = min(spans, key=lambda s: s.start_ms)
            out.append(
                {
                    "trace_id": tid,
                    "root": root.name,
                    "spans": len(spans),
                    "duration_ms": round(end - start, 2),
                    "status": "error" if any(s.status == "error" for s in spans) else "ok",
                    "start_ms": start,
                }
            )
        return sorted(out, key=lambda r: r["start_ms"], reverse=True)

    def clear(self) -> None:
        self._spans.clear()


class CompositeTracer:
    """Fans each span out to several sinks -- keep it in memory for the dashboard
    AND export it to OpenTelemetry for a real collector. An exporter failure is
    swallowed: telemetry must never break the request path it observes."""

    def __init__(self, primary: InMemoryTracer, *extra: Tracer) -> None:
        self._primary = primary
        self._extra = extra

    def record(self, span: SpanRecord) -> None:
        self._primary.record(span)
        for t in self._extra:
            try:
                t.record(span)
            except Exception:
                pass

    def spans(self, trace_id: str | None = None) -> list[SpanRecord]:
        return self._primary.spans(trace_id)

    def traces(self) -> list[dict]:
        return self._primary.traces()

    def clear(self) -> None:
        self._primary.clear()


# --- context propagation: how a span learns its parent and trace ------------
_current_span: contextvars.ContextVar[SpanRecord | None] = contextvars.ContextVar(
    "current_span", default=None
)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)

_TRACER: Tracer | None = None


def get_tracer() -> Tracer:
    """The process-wide tracer, built once from settings (single env switch)."""
    global _TRACER
    if _TRACER is None:
        _TRACER = _build_tracer()
    return _TRACER


def _build_tracer() -> Tracer:
    from app.config import settings

    mem = InMemoryTracer()
    if settings.trace_mode == "otel":
        try:
            from app.obs.otel import OtelExporter

            return CompositeTracer(mem, OtelExporter())
        except Exception:
            # OpenTelemetry libs not installed -> degrade to memory, demo lives.
            return mem
    return mem


@contextmanager
def trace(incident_id: str) -> Iterator[None]:
    """Bind the current trace (incident id) for every span raised inside."""
    token = _trace_id.set(incident_id)
    try:
        yield
    finally:
        _trace_id.reset(token)


@contextmanager
def span(name: str, kind: str = "graph", **attributes: object) -> Iterator[SpanRecord]:
    """Open a span around a unit of work. Nests under whatever span is current,
    times itself, captures attributes, and records on exit -- on success or on
    exception (status=error, then re-raised)."""
    parent = _current_span.get()
    sp = SpanRecord(
        span_id=uuid4().hex[:12],
        parent_id=parent.span_id if parent else None,
        trace_id=_trace_id.get(),
        name=name,
        kind=kind,
        start_ms=_now_ms(),
        attributes=dict(attributes),
    )
    token = _current_span.set(sp)
    try:
        yield sp
    except Exception as exc:
        sp.status = "error"
        sp.error = repr(exc)
        raise
    finally:
        sp.end_ms = _now_ms()
        sp.duration_ms = round(sp.end_ms - sp.start_ms, 2)
        _current_span.reset(token)
        get_tracer().record(sp)
