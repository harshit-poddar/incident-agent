from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.telemetry.metrics import ServiceMetrics, degraded, healthy


@runtime_checkable
class TelemetrySource(Protocol):
    """Where service metrics come from. The telemetry seam, like LLMClient and
    TelemetrySource's cousins: MockTelemetrySource (in-process, no deps) or
    RedisTelemetrySource (ingest from an event queue)."""

    def query_metrics(self, service: str) -> ServiceMetrics:
        ...

    def mark_recovered(self, service: str) -> None:
        ...


class MockTelemetrySource:
    """Offline source: a service reads as degraded until it is marked recovered
    (which the supervisor does after a successful remediation). Drives the
    golden-path verification with zero dependencies."""

    def __init__(self) -> None:
        self._recovered: set[str] = set()

    def mark_recovered(self, service: str) -> None:
        self._recovered.add(service)

    def query_metrics(self, service: str) -> ServiceMetrics:
        return healthy(service) if service in self._recovered else degraded(service)


def get_telemetry_source() -> TelemetrySource:
    from app.config import settings

    if settings.telemetry_mode == "redis":
        from app.telemetry.source_redis import RedisTelemetrySource

        return RedisTelemetrySource()
    return MockTelemetrySource()
