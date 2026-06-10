from __future__ import annotations

from app.telemetry.metrics import ServiceMetrics, degraded


class RedisTelemetrySource:
    """Telemetry ingested from a Redis Stream -- one stream per service. Recovery
    is published as an event (XADD); a query reads the latest event (XREVRANGE).
    This models the event-queue ingestion path: in production a collector would
    continuously XADD live metrics from the monitored cluster; here the recovery
    signal is the event, and a service with no events yet reads as degraded
    (i.e. the active incident). redis is imported lazily so mock mode is dep-free."""

    def __init__(self, url: str | None = None) -> None:
        import redis

        from app.config import settings

        self._redis = redis.Redis.from_url(url or settings.redis_url, decode_responses=True)

    def _stream(self, service: str) -> str:
        return f"telemetry:{service}"

    def mark_recovered(self, service: str) -> None:
        from app.telemetry.metrics import healthy

        self._redis.xadd(self._stream(service), {"data": healthy(service).model_dump_json()})

    def query_metrics(self, service: str) -> ServiceMetrics:
        entries = self._redis.xrevrange(self._stream(service), count=1)
        if not entries:
            return degraded(service)  # no event yet -> active incident
        _entry_id, fields = entries[0]
        return ServiceMetrics.model_validate_json(fields["data"])
