"""OpenTelemetry bridge -- the production half of Slice 6.

The dashboard runs entirely on the in-memory tracer; this exporter mirrors the
exact same spans into a real OpenTelemetry pipeline so they land in Jaeger /
Tempo / Logfire / any OTLP collector. It is only constructed when
`TRACE_MODE=otel`, and only then are the opentelemetry packages imported, so
the default (memory) install needs zero extra dependencies.

Install the optional deps to use it:
    pip install opentelemetry-sdk opentelemetry-exporter-otlp

Spans complete child-first (a child's `with` block exits before its parent's),
so we buffer a trace's spans and flush the whole tree once its root completes --
emitting parents before children with explicit start/end timestamps, which
reconstructs the correct OTel parent-child hierarchy."""
from __future__ import annotations

from app.obs.tracer import SpanRecord, perf_ms_to_epoch_ns


class OtelExporter:
    """Records SpanRecords and, when a trace's root span finishes, replays the
    whole trace into OpenTelemetry with proper parenting and timestamps."""

    def __init__(self) -> None:
        # All imports here so a memory-mode process never touches opentelemetry.
        from opentelemetry import trace as ot_trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        from app.config import settings

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        if settings.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        else:
            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        self._ot = ot_trace
        self._tracer = provider.get_tracer("agents-026")
        self._buffers: dict[str, list[SpanRecord]] = {}

    def record(self, span: SpanRecord) -> None:
        if span.trace_id is None:
            return
        self._buffers.setdefault(span.trace_id, []).append(span)
        # Root finished -> the whole trace is collected; flush it.
        if span.parent_id is None:
            self._flush(self._buffers.pop(span.trace_id, []))

    def _flush(self, spans: list[SpanRecord]) -> None:
        from opentelemetry.trace import Status, StatusCode

        # Emit parents before children so child contexts can reference them.
        by_id = {s.span_id: s for s in spans}

        def depth(s: SpanRecord) -> int:
            d, cur = 0, s
            while cur.parent_id and cur.parent_id in by_id:
                d += 1
                cur = by_id[cur.parent_id]
            return d

        ctx_by_span: dict[str, object] = {}
        for s in sorted(spans, key=depth):
            parent_ctx = ctx_by_span.get(s.parent_id) if s.parent_id else None
            ot_span = self._tracer.start_span(
                s.name,
                context=parent_ctx,
                start_time=perf_ms_to_epoch_ns(s.start_ms),
                attributes={"kind": s.kind, **{k: str(v) for k, v in s.attributes.items()}},
            )
            if s.status == "error":
                ot_span.set_status(Status(StatusCode.ERROR, s.error or "error"))
            ctx_by_span[s.span_id] = self._ot.set_span_in_context(ot_span)
            ot_span.end(end_time=perf_ms_to_epoch_ns(s.end_ms or s.start_ms))

    def spans(self, trace_id: str | None = None) -> list[SpanRecord]:  # pragma: no cover
        return []

    def traces(self) -> list[dict]:  # pragma: no cover
        return []

    def clear(self) -> None:  # pragma: no cover
        self._buffers.clear()
