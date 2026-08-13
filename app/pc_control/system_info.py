from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class SystemStatus:
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_used_gb: float
    disk_total_gb: float
    disk_percent: float


def get_system_status() -> SystemStatus:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    gb = 1024 ** 3
    return SystemStatus(
        cpu_percent=round(float(psutil.cpu_percent(interval=0.2)), 1),
        memory_percent=round(float(memory.percent), 1),
        memory_used_gb=round(memory.used / gb, 1),
        memory_total_gb=round(memory.total / gb, 1),
        disk_used_gb=round(disk.used / gb, 1),
        disk_total_gb=round(disk.total / gb, 1),
        disk_percent=round(float(disk.percent), 1),
    )


def top_memory_processes(limit: int = 5) -> list[tuple[str, int, float]]:
    rows: list[tuple[str, int, float]] = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            memory_info = process.info.get("memory_info")
            rss = float(memory_info.rss) if memory_info else 0.0
            rows.append((str(process.info.get("name") or "process"), int(process.info["pid"]), rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda item: item[2], reverse=True)
    gb = 1024 ** 3
    return [(name, pid, round(rss / gb, 2)) for name, pid, rss in rows[:max(1, min(limit, 10))]]


def top_cpu_processes(limit: int = 5) -> list[tuple[str, int, float]]:
    processes = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            process.cpu_percent(None)
            processes.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    time.sleep(0.18)
    rows: list[tuple[str, int, float]] = []
    for process in processes:
        try:
            value = float(process.cpu_percent(None))
            rows.append((process.name() or "process", process.pid, round(value, 1)))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    rows.sort(key=lambda item: item[2], reverse=True)
    return rows[:max(1, min(limit, 10))]
