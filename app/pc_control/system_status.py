from __future__ import annotations

import shutil
import subprocess
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


class GpuTemperatureError(RuntimeError):
    pass


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


def read_nvidia_temperatures() -> list[tuple[str, int]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        raise GpuTemperatureError("nvidia-smi не найден. Температура NVIDIA недоступна.")

    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=name,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GpuTemperatureError("Не удалось опросить видеокарту.") from error

    if completed.returncode != 0:
        raise GpuTemperatureError("Драйвер NVIDIA не вернул температуру видеокарты.")

    rows: list[tuple[str, int]] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line or "," not in line:
            continue
        name, raw_temperature = line.rsplit(",", 1)
        try:
            temperature = int(float(raw_temperature.strip()))
        except ValueError:
            continue
        rows.append((name.strip()[:120] or "NVIDIA GPU", temperature))

    if not rows:
        raise GpuTemperatureError("Температура видеокарты недоступна.")

    return rows
