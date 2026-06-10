from __future__ import annotations

from app.telemetry.metrics import ServiceMetrics
from app.telemetry.source import TelemetrySource, get_telemetry_source


class TelemetryTool:
    """Agent-facing telemetry tool. Thin wrapper over a TelemetrySource (mock or
    redis, chosen by TELEMETRY_MODE) so agents are unaware of the backend -- the
    same seam pattern as LLMClient and the vector store."""

    def __init__(self, source: TelemetrySource | None = None) -> None:
        self._source = source or get_telemetry_source()

    def query_metrics(self, service: str) -> ServiceMetrics:
        return self._source.query_metrics(service)

    def mark_recovered(self, service: str) -> None:
        self._source.mark_recovered(service)
