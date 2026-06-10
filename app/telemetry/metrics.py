from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ServiceMetrics(BaseModel):
    """Typed service telemetry -- replaces the old raw dict so metrics flow
    through the graph with validation like every other domain model."""

    service: str
    error_rate: float
    mem_usage: float
    p95_latency_ms: float
    healthy: bool
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GpuMetrics(BaseModel):
    """A snapshot of one accelerator -- the MI300X the agent runs on. Sourced
    from rocm-smi in production, mocked on CPU/non-AMD dev boxes."""

    device: str
    gpu_util_pct: float
    vram_used_gb: float
    vram_total_gb: float
    temp_c: float
    power_w: float
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Canonical presets: one place defines what "degraded" vs "healthy" looks like,
# matching the golden-path scenario (payments-api OOM -> restart -> recovered).
def degraded(service: str) -> ServiceMetrics:
    return ServiceMetrics(
        service=service, error_rate=0.38, mem_usage=0.98, p95_latency_ms=2400.0, healthy=False
    )


def healthy(service: str) -> ServiceMetrics:
    return ServiceMetrics(
        service=service, error_rate=0.004, mem_usage=0.41, p95_latency_ms=180.0, healthy=True
    )
