from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass


class BrightnessControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class MonitorBrightness:
    index: int
    description: str
    percent: int


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", wintypes.WCHAR * 128),
    ]


def _require_windows() -> None:
    if os.name != "nt":
        raise BrightnessControlError("Управление яркостью доступно только в Windows")


def _physical_monitors() -> list[PHYSICAL_MONITOR]:
    _require_windows()
    user32 = ctypes.windll.user32
    dxva2 = ctypes.windll.dxva2
    monitor_handles: list[int] = []

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def callback(hmonitor, _hdc, _rect, _data):
        monitor_handles.append(int(hmonitor))
        return True

    if not user32.EnumDisplayMonitors(0, 0, callback_type(callback), 0):
        raise BrightnessControlError("Windows не смогла перечислить мониторы")

    result: list[PHYSICAL_MONITOR] = []
    for hmonitor in monitor_handles:
        count = wintypes.DWORD(0)
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
            wintypes.HMONITOR(hmonitor),
            ctypes.byref(count),
        ) or count.value <= 0:
            continue

        array_type = PHYSICAL_MONITOR * int(count.value)
        monitors = array_type()
        if dxva2.GetPhysicalMonitorsFromHMONITOR(
            wintypes.HMONITOR(hmonitor),
            count,
            monitors,
        ):
            result.extend(monitors[index] for index in range(int(count.value)))

    if not result:
        raise BrightnessControlError("Не найдены мониторы с доступом DDC/CI")
    return result


def _destroy(monitors: list[PHYSICAL_MONITOR]) -> None:
    if not monitors:
        return
    try:
        dxva2 = ctypes.windll.dxva2
        array_type = PHYSICAL_MONITOR * len(monitors)
        array = array_type(*monitors)
        dxva2.DestroyPhysicalMonitors(len(monitors), array)
    except Exception:
        pass


def get_brightness(monitor_index: int | None = None) -> list[MonitorBrightness]:
    monitors = _physical_monitors()
    try:
        selected = _select(monitors, monitor_index)
        values: list[MonitorBrightness] = []
        dxva2 = ctypes.windll.dxva2
        for original_index, monitor in selected:
            minimum = wintypes.DWORD()
            current = wintypes.DWORD()
            maximum = wintypes.DWORD()
            ok = dxva2.GetMonitorBrightness(
                monitor.hPhysicalMonitor,
                ctypes.byref(minimum),
                ctypes.byref(current),
                ctypes.byref(maximum),
            )
            if not ok or maximum.value <= minimum.value:
                continue
            percent = round(
                (current.value - minimum.value)
                * 100
                / (maximum.value - minimum.value)
            )
            values.append(
                MonitorBrightness(
                    index=original_index + 1,
                    description=str(monitor.szPhysicalMonitorDescription).strip() or f"Монитор {original_index + 1}",
                    percent=max(0, min(100, int(percent))),
                )
            )

        if not values:
            raise BrightnessControlError(
                "Монитор не поддерживает управление яркостью через DDC/CI"
            )
        return values
    finally:
        _destroy(monitors)


def set_brightness(percent: int, monitor_index: int | None = None) -> list[int]:
    normalized = max(0, min(100, int(percent)))
    monitors = _physical_monitors()
    changed: list[int] = []
    try:
        selected = _select(monitors, monitor_index)
        dxva2 = ctypes.windll.dxva2
        for original_index, monitor in selected:
            minimum = wintypes.DWORD()
            current = wintypes.DWORD()
            maximum = wintypes.DWORD()
            if not dxva2.GetMonitorBrightness(
                monitor.hPhysicalMonitor,
                ctypes.byref(minimum),
                ctypes.byref(current),
                ctypes.byref(maximum),
            ):
                continue
            target = round(
                minimum.value
                + (maximum.value - minimum.value) * normalized / 100
            )
            if dxva2.SetMonitorBrightness(monitor.hPhysicalMonitor, int(target)):
                changed.append(original_index + 1)

        if not changed:
            raise BrightnessControlError(
                "Монитор не поддерживает изменение яркости через DDC/CI"
            )
        return changed
    finally:
        _destroy(monitors)


def _select(
    monitors: list[PHYSICAL_MONITOR],
    monitor_index: int | None,
) -> list[tuple[int, PHYSICAL_MONITOR]]:
    indexed = list(enumerate(monitors))
    if monitor_index is None:
        return indexed
    requested = int(monitor_index) - 1
    if requested < 0 or requested >= len(monitors):
        raise BrightnessControlError("Монитор с таким номером не найден")
    return [(requested, monitors[requested])]
