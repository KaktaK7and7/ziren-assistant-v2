from __future__ import annotations

import ctypes
import os
import time

from app.pc_control.windows_input import WindowsInputError, send_hotkey


SM_CMONITORS = 80
MONITOR_DEFAULTTONEAREST = 2
MOVE_VERIFY_ATTEMPTS = 8
MOVE_VERIFY_DELAY_SECONDS = 0.05


class MonitorControlError(RuntimeError):
    pass


def _user32():
    if os.name != "nt":
        raise MonitorControlError("Управление мониторами доступно только в Windows")
    return ctypes.windll.user32


def _monitor_count(user32) -> int:
    return max(0, int(user32.GetSystemMetrics(SM_CMONITORS)))


def _foreground_window(user32) -> int:
    hwnd = int(user32.GetForegroundWindow() or 0)
    if not hwnd or not user32.IsWindow(hwnd):
        raise MonitorControlError("Не найдено активное окно для переноса")
    return hwnd


def _monitor_for_window(user32, hwnd: int) -> int:
    handle = int(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) or 0)
    if not handle:
        raise MonitorControlError("Windows не смогла определить монитор активного окна")
    return handle


def move_active_window(direction: str) -> None:
    normalized = str(direction or "").strip().lower()
    if normalized not in {"left", "right"}:
        raise MonitorControlError("Неизвестное направление переноса окна")

    user32 = _user32()
    if _monitor_count(user32) < 2:
        raise MonitorControlError("Для переноса окна нужен второй активный монитор")

    hwnd = _foreground_window(user32)
    before_monitor = _monitor_for_window(user32, hwnd)
    key = "left" if normalized == "left" else "right"

    try:
        send_hotkey(["win", "shift", key])
    except WindowsInputError as error:
        raise MonitorControlError(str(error)) from error

    for _ in range(MOVE_VERIFY_ATTEMPTS):
        time.sleep(MOVE_VERIFY_DELAY_SECONDS)
        if not user32.IsWindow(hwnd):
            raise MonitorControlError("Активное окно исчезло во время переноса")
        after_monitor = _monitor_for_window(user32, hwnd)
        if after_monitor != before_monitor:
            return

    raise MonitorControlError(
        "Windows получила команду, но перенос окна на другой монитор не подтвердился"
    )
