from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.telemetry.metrics import ServiceMetrics, degraded, healthy


@runtime_checkable
class TelemetrySource(Protocol):
    """Where service metrics come from. The telemetry seam, like LLMClient and
    TelemetrySource's cousins: MockTelemetrySource (in-process, no deps) or
    RedisTelemetrySource (ingest from an event queue).

    `ingest` is the producer side: a collector (or, in the demo, the live log
    pipeline) publishes a metrics sample; `query_metrics` reads the latest."""

    def query_metrics(self, service: str) -> ServiceMetrics:
        ...

    def ingest(self, metrics: ServiceMetrics) -> None:
        ...

    def mark_recovered(self, service: str) -> None:
        ...

    def reset(self) -> None:
        ...


class MockTelemetrySource:
    """Offline source: holds the latest ingested sample per service in memory; a
    service with no sample yet reads as degraded (i.e. an active incident). The
    supervisor publishes a healthy sample after a successful remediation. Drives
    the golden-path verification with zero dependencies."""

    def __init__(self) -> None:
        self._latest: dict[str, ServiceMetrics] = {}

    def ingest(self, metrics: ServiceMetrics) -> None:
        self._latest[metrics.service] = metrics

    def mark_recovered(self, service: str) -> None:
        self.ingest(healthy(service))

    def query_metrics(self, service: str) -> ServiceMetrics:
        return self._latest.get(service) or degraded(service)

    def reset(self) -> None:
        self._latest.clear()


def get_telemetry_source() -> TelemetrySource:
    from app.config import settings

    if settings.telemetry_mode == "redis":
        from app.telemetry.source_redis import RedisTelemetrySource

        return RedisTelemetrySource()
    return MockTelemetrySource()
