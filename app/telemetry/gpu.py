from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.telemetry.metrics import GpuMetrics


@runtime_checkable
class GpuMonitor(Protocol):
    """Reads the accelerator(s) the agent runs on. MockGpuMonitor for CPU/dev
    boxes; RocmSmiGpuMonitor shells out to rocm-smi on the MI300X pod. This is
    what lets the agent monitor the very hardware serving its model."""

    def sample(self) -> list[GpuMetrics]:
        ...


class MockGpuMonitor:
    """Plausible MI300X readings for dev/demo on non-AMD hardware. 192 GB VRAM,
    a busy-but-healthy load -- enough to drive the GPU panel without a GPU."""

    def sample(self) -> list[GpuMetrics]:
        return [
            GpuMetrics(
                device="MI300X[0]",
                gpu_util_pct=64.0,
                vram_used_gb=142.0,
                vram_total_gb=192.0,
                temp_c=58.0,
                power_w=410.0,
            )
        ]


class RocmSmiGpuMonitor:
    """Real readings via `rocm-smi --showuse --showmemuse --showtemp --showpower
    --json`. rocm-smi's JSON keys vary across ROCm versions, so every field is
    looked up defensively with fallbacks. Untestable off AMD hardware -- the
    verified path on this repo's machines is MockGpuMonitor."""

    def sample(self) -> list[GpuMetrics]:
        import json
        import subprocess

        proc = subprocess.run(
            [
                "rocm-smi",
                "--showuse",
                "--showmemuse",
                "--showmeminfo",
                "vram",
                "--showtemp",
                "--showpower",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(proc.stdout or "{}")
        out: list[GpuMetrics] = []
        for card, fields in data.items():
            if not card.lower().startswith("card"):
                continue
            used_b = _num(fields, "VRAM Total Used Memory (B)", "VRAM Total Used Memory (b)")
            total_b = _num(fields, "VRAM Total Memory (B)", "VRAM Total Memory (b)")
            out.append(
                GpuMetrics(
                    device=f"MI300X[{card.replace('card', '')}]",
                    gpu_util_pct=_num(fields, "GPU use (%)"),
                    vram_used_gb=used_b / 1e9,
                    vram_total_gb=(total_b / 1e9) or 192.0,
                    temp_c=_num(fields, "Temperature (Sensor edge) (C)", "Temperature (Sensor junction) (C)"),
                    power_w=_num(fields, "Average Graphics Package Power (W)", "Current Socket Graphics Package Power (W)"),
                )
            )
        return out


def _num(fields: dict, *keys: str) -> float:
    """First present key parsed to float, else 0.0 -- tolerant of rocm-smi key
    drift across versions."""
    for k in keys:
        if k in fields:
            try:
                return float(str(fields[k]).strip())
            except (TypeError, ValueError):
                continue
    return 0.0


def get_gpu_monitor() -> GpuMonitor:
    from app.config import settings

    if settings.gpu_monitor_mode == "rocm":
        return RocmSmiGpuMonitor()
    return MockGpuMonitor()
