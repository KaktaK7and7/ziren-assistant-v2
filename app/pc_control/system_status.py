from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class SystemStatus:
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_free_gb: float
    disk_total_gb: float


def read_system_status() -> SystemStatus:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    gb = 1024 ** 3
    return SystemStatus(
        cpu_percent=round(float(psutil.cpu_percent(interval=0.2)), 1),
        memory_percent=round(float(memory.percent), 1),
        memory_used_gb=round(memory.used / gb, 1),
        memory_total_gb=round(memory.total / gb, 1),
        disk_free_gb=round(disk.free / gb, 1),
        disk_total_gb=round(disk.total / gb, 1),
    )
