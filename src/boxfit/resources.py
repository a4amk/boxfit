"""Resource telemetry: host snapshot + container sampling during rungs.

The verdict says PASS/FAIL; this says *why* and *where the ceiling is*.
All best-effort: missing docker/container info degrades to None, never fails.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any


def host_snapshot() -> dict[str, Any]:
    mem_gb, disk_free_gb = 0.0, 0.0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_gb = int(line.split()[1]) / 1024 / 1024
                    break
    except OSError:
        pass
    try:
        disk_free_gb = shutil.disk_usage("/").free / 1024**3
    except OSError:
        pass
    return {
        "nproc": os.cpu_count() or 0,
        "mem_gb": round(mem_gb, 1),
        "disk_free_gb": round(disk_free_gb, 1),
        "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0,
    }


def container_cpu_cap_pct(container: str) -> float | None:
    """Cgroup CPU cap as percent of one core (180.0 = 1.8 cores)."""
    try:
        out = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.HostConfig.NanoCpus}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        nano = int(out.stdout.strip() or 0)
        return nano / 10**7 if nano > 0 else None
    except Exception:
        return None


def sample_container(container: str) -> tuple[float | None, float | None]:
    """(cpu_pct, mem_mib) or (None, None) when docker is unavailable."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}} {{.MemUsage}}", container],
            capture_output=True,
            text=True,
            timeout=20,
        )
        parts = out.stdout.strip().split()
        cpu = float(parts[0].rstrip("%")) if parts else None
        mem = None
        if len(parts) >= 3 and "MiB" in parts[1]:
            mem = float(parts[1].replace("MiB", ""))
        elif len(parts) >= 3 and "GiB" in parts[1]:
            mem = float(parts[1].replace("GiB", "")) * 1024
        return cpu, mem
    except Exception:
        return None, None


class Sampler(threading.Thread):
    """Background sampler; stop() returns avg/max aggregates."""

    def __init__(self, container: str, interval: float = 5.0) -> None:
        super().__init__(daemon=True)
        self.container = container
        self.interval = interval
        self.cpus: list[float] = []
        self.mems: list[float] = []
        self.loads: list[float] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            cpu, mem = sample_container(self.container)
            if cpu is not None:
                self.cpus.append(cpu)
            if mem is not None:
                self.mems.append(mem)
            try:
                self.loads.append(os.getloadavg()[0])
            except OSError:
                pass

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        self.join(timeout=25)
        return {
            "qdrant_cpu_avg": round(sum(self.cpus) / len(self.cpus), 1) if self.cpus else None,
            "qdrant_cpu_max": round(max(self.cpus), 1) if self.cpus else None,
            "qdrant_mem_max_mib": round(max(self.mems), 1) if self.mems else None,
            "host_load_avg": round(sum(self.loads) / len(self.loads), 2) if self.loads else None,
        }


def fit_ceiling(
    points: list[tuple[float, float]], cap_pct: float
) -> tuple[float | None, str]:
    """Linear fit of achieved-RPS -> CPU%: RPS where CPU hits the cap.

    Returns (estimate, note). Needs >= 2 rungs with positive slope and real
    CPU burn; otherwise None with the reason — no number is better than a
    fabricated one.
    """
    if len(points) < 2:
        return None, "need >= 2 rungs"
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    denom = sum((p[0] - sx / n) ** 2 for p in points)
    if denom <= 0:
        return None, "no RPS spread across rungs"
    slope = sum((p[0] - sx / n) * (p[1] - sy / n) for p in points) / denom
    if slope <= 0:
        return None, "CPU does not rise with RPS (not CPU-bound here)"
    intercept = sy / n - slope * (sx / n)
    estimate = (cap_pct - intercept) / slope
    note = ""
    if max(p[1] for p in points) < 50:
        note = "low-confidence: peak CPU under 50%, projection is far-field"
    return max(estimate, 0.0), note
