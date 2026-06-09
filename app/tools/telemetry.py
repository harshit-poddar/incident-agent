from __future__ import annotations

# Stubbed telemetry source. Swap for a Prometheus / event-queue query in prod.
_DEGRADED = {"error_rate": 0.38, "mem_usage": 0.98, "p95_latency_ms": 2400}
_HEALTHY = {"error_rate": 0.004, "mem_usage": 0.41, "p95_latency_ms": 180}


class TelemetryTool:
    def __init__(self) -> None:
        self._recovered: set[str] = set()

    def mark_recovered(self, service: str) -> None:
        self._recovered.add(service)

    def query_metrics(self, service: str) -> dict:
        return dict(_HEALTHY if service in self._recovered else _DEGRADED)
