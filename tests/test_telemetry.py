from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.telemetry.gpu import MockGpuMonitor
from app.telemetry.metrics import ServiceMetrics, degraded, healthy
from app.telemetry.source import MockTelemetrySource
from app.tools.telemetry import TelemetryTool

client = TestClient(app)


def test_presets_are_typed_and_consistent():
    d = degraded("payments-api")
    h = healthy("payments-api")
    assert isinstance(d, ServiceMetrics) and isinstance(h, ServiceMetrics)
    assert d.healthy is False and h.healthy is True
    assert d.error_rate > h.error_rate  # degraded is worse


def test_mock_source_degraded_until_recovered():
    src = MockTelemetrySource()
    assert src.query_metrics("payments-api").healthy is False
    src.mark_recovered("payments-api")
    assert src.query_metrics("payments-api").healthy is True


def test_telemetry_tool_wraps_source():
    tool = TelemetryTool(source=MockTelemetrySource())
    m = tool.query_metrics("payments-api")
    assert isinstance(m, ServiceMetrics) and m.service == "payments-api"
    tool.mark_recovered("payments-api")
    assert tool.query_metrics("payments-api").healthy is True


def test_mock_gpu_monitor_reports_mi300x():
    gpus = MockGpuMonitor().sample()
    assert len(gpus) == 1
    g = gpus[0]
    assert "MI300X" in g.device
    assert g.vram_total_gb == 192.0
    assert 0 <= g.gpu_util_pct <= 100


def test_gpu_endpoint():
    r = client.get("/telemetry/gpu")
    assert r.status_code == 200
    body = r.json()
    assert body and "MI300X" in body[0]["device"]
    assert body[0]["vram_total_gb"] == 192.0


def test_service_telemetry_endpoint():
    r = client.get("/telemetry/service/payments-api")
    assert r.status_code == 200
    assert r.json()["service"] == "payments-api"
