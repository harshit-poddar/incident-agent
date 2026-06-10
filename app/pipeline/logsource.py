from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class LogLine(BaseModel):
    """One line emitted by a CI/CD pipeline or service runtime.

    Typed I/O, same as everything else: agents and the monitor never parse raw
    strings -- they receive a structured LogLine."""

    ts: str
    stage: str            # build | test | deploy | runtime | monitor | agent
    level: str            # OK | INFO | WARN | ERROR
    msg: str
    service: str | None = None


@runtime_checkable
class LogSource(Protocol):
    """Yields pipeline/runtime log lines. Mock = a scripted scenario; a real
    implementation would tail a CI runner, Loki/Elasticsearch, or a Kubernetes
    pod log stream. Same seam pattern as LLMClient and TelemetrySource."""

    def lines(self) -> list[tuple[LogLine, float]]:
        """Each entry is (line, delay_seconds_to_wait_before_emitting_it)."""
        ...


class MockPipelineLogSource:
    """A scripted CI/CD deploy of payments-api that degrades into an OOM at
    runtime. The final ERROR line breaches the error-rate SLO -- that is the
    signature the LogMonitor catches to auto-open an incident.

    Delays pace the stream so the demo builds tension; the API can scale them
    (pace=0 in tests for an instant run)."""

    def lines(self) -> list[tuple[LogLine, float]]:
        svc = "payments-api"

        def L(ts, stage, level, msg, service=None):
            return LogLine(ts=ts, stage=stage, level=level, msg=msg, service=service)

        return [
            (L("12:34:01", "build", "OK", "pipeline #482 started · payments-api", svc), 0.2),
            (L("12:34:01", "build", "OK", "checkout main @ a3f9c2e"), 0.25),
            (L("12:34:02", "build", "OK", "docker build payments-api:482 ✓ (38s)"), 0.30),
            (L("12:34:03", "test", "OK", "unit tests · 214 passed"), 0.25),
            (L("12:34:04", "deploy", "OK", "rolling out payments-api:482 → sandbox cluster"), 0.35),
            (L("12:34:06", "runtime", "INFO", "serving traffic · 2.4k req/s", svc), 0.50),
            (L("12:34:09", "runtime", "INFO", "mem 71% · p95 180ms · err 0.3%", svc), 0.50),
            (L("12:34:13", "runtime", "WARN", "mem 88% climbing under sustained load", svc), 0.65),
            (L("12:34:16", "runtime", "ERROR", "java.lang.OutOfMemoryError: Java heap space", svc), 0.70),
            (L("12:34:16", "runtime", "ERROR", "pod payments-api-7c9 OOMKilled — restarting", svc), 0.50),
            (L("12:34:18", "runtime", "ERROR", "health check failed (3/3) · err_rate 0.38 > 0.02", svc), 0.70),
        ]
