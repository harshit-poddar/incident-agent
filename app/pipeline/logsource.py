from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class LogLine(BaseModel):
    """One line emitted by a CI/CD pipeline or service runtime.

    Typed I/O, same as everything else: agents and the monitor never parse raw
    strings -- they receive a structured LogLine.

    `metrics` carries an optional telemetry snapshot (error_rate, mem_usage,
    p95_latency_ms, healthy) for runtime lines. The stream endpoint publishes it
    to the telemetry source (Redis), so the dashboard reads the live degradation
    straight out of the event queue as the job runs."""

    ts: str
    stage: str            # build | test | deploy | runtime | monitor | agent
    level: str            # OK | INFO | WARN | ERROR
    msg: str
    service: str | None = None
    metrics: dict | None = None


@runtime_checkable
class LogSource(Protocol):
    """Yields pipeline/runtime log lines. Mock = a scripted scenario; a real
    implementation would tail a CI runner, Loki/Elasticsearch, or a Kubernetes
    pod log stream. Same seam pattern as LLMClient and TelemetrySource."""

    def lines(self) -> list[tuple[LogLine, float]]:
        """Each entry is (line, delay_seconds_to_wait_before_emitting_it)."""
        ...


def _metrics(error_rate: float, mem_usage: float, p95: float, healthy: bool) -> dict:
    return {
        "error_rate": error_rate,
        "mem_usage": mem_usage,
        "p95_latency_ms": p95,
        "healthy": healthy,
    }


class MockPipelineLogSource:
    """A scripted CI/CD deploy of payments-api that degrades into an OOM at
    runtime -- grounded in the REAL bug the agent fixes: the unbounded receipt
    cache in payments/handler.py (runbook RB-114). The build/test/deploy stages
    run clean; under sustained traffic the cache never evicts, memory climbs,
    GC thrashes, the pod is OOM-killed, and the error-rate SLO is breached.

    That final ERROR line is the signature the LogMonitor catches to auto-open
    an incident. Runtime lines carry a `metrics` snapshot that the stream
    endpoint publishes to Redis, so the dashboard reads the live climb out of
    the event queue. Delays pace the ~13s stream so the room sees work
    happening; the API scales them (pace=0 in tests for an instant run)."""

    def lines(self) -> list[tuple[LogLine, float]]:
        svc = "payments-api"

        def L(ts, stage, level, msg, service=None, metrics=None):
            return LogLine(ts=ts, stage=stage, level=level, msg=msg, service=service, metrics=metrics)

        return [
            # --- build ---------------------------------------------------------
            (L("12:34:01", "build", "INFO", "pipeline #4821 triggered · payments-api · commit a3f9c2e"), 0.40),
            (L("12:34:01", "build", "OK", "checkout main @ a3f9c2e"), 0.30),
            (L("12:34:02", "build", "INFO", "resolving dependencies · 142 packages"), 0.40),
            (L("12:34:03", "build", "INFO", "compiling payments-api · 86 sources"), 0.55),
            (L("12:34:04", "build", "INFO", "docker build · layer 3/7 (app sources)"), 0.35),
            (L("12:34:05", "build", "OK", "docker build · payments-api:4821 ✓ (41s)"), 0.45),
            # --- test ----------------------------------------------------------
            (L("12:34:06", "test", "OK", "unit tests · 214 passed"), 0.50),
            (L("12:34:07", "test", "OK", "integration tests · 38 passed"), 0.50),
            (L("12:34:07", "test", "WARN", "load/soak test skipped (fast pipeline) — memory profile not exercised"), 0.45),
            (L("12:34:08", "test", "OK", "trivy image scan · 0 critical, 2 low"), 0.40),
            # --- deploy --------------------------------------------------------
            (L("12:34:09", "deploy", "INFO", "pushing image → ghcr.io/payments-api:4821"), 0.45),
            (L("12:34:10", "deploy", "OK", "rolling update · pod 1/3 ready", svc), 0.50),
            (L("12:34:11", "deploy", "OK", "rolling update · pod 2/3 ready", svc), 0.50),
            (L("12:34:12", "deploy", "OK", "rolling update · pod 3/3 ready", svc), 0.50),
            (L("12:34:12", "deploy", "OK", "smoke test · GET /healthz → 200", svc), 0.40),
            (L("12:34:13", "deploy", "OK", "deploy #4821 live → sandbox cluster", svc), 0.45),
            # --- runtime (metrics climb -> published to Redis) -----------------
            (L("12:34:14", "runtime", "INFO", "serving traffic · 2.4k req/s", svc,
               _metrics(0.004, 0.42, 180, True)), 0.60),
            (L("12:34:15", "runtime", "INFO", "receipt cache warming · 48k entries", svc,
               _metrics(0.004, 0.55, 190, True)), 0.60),
            (L("12:34:16", "runtime", "INFO", "mem 68% · p95 210ms · err 0.4%", svc,
               _metrics(0.004, 0.68, 210, True)), 0.65),
            (L("12:34:18", "runtime", "WARN", "receipt cache 612k entries · evictions=0 (unbounded)", svc,
               _metrics(0.01, 0.82, 360, True)), 0.70),
            (L("12:34:19", "runtime", "WARN", "GC pause 1.2s · heap pressure rising", svc,
               _metrics(0.05, 0.91, 900, False)), 0.70),
            (L("12:34:21", "runtime", "ERROR", "java.lang.OutOfMemoryError: Java heap space", svc,
               _metrics(0.21, 0.98, 2400, False)), 0.70),
            (L("12:34:21", "runtime", "ERROR", "pod payments-api-7c9 OOMKilled — restarting", svc,
               _metrics(0.33, 0.99, 2400, False)), 0.55),
            (L("12:34:23", "runtime", "ERROR", "health check failed (3/3) · err_rate 0.38 > 0.02 SLO breach", svc,
               _metrics(0.38, 0.98, 2400, False)), 0.70),
        ]
