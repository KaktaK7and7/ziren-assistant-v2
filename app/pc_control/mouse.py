from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes


INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


class MouseControlError(RuntimeError):
    pass


def _require_windows():
    if os.name != "nt":
        raise MouseControlError("Управление мышью доступно только в Windows")

    ULONG_PTR = wintypes.WPARAM

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    return MOUSEINPUT, INPUT


def _send(flags: int, data: int = 0) -> None:
    MOUSEINPUT, INPUT = _require_windows()
    packet = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(
            dx=0,
            dy=0,
            mouseData=data,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
    if sent != 1:
        raise MouseControlError("Windows не приняла действие мыши")


def left_click() -> None:
    _send(MOUSEEVENTF_LEFTDOWN)
    _send(MOUSEEVENTF_LEFTUP)


def double_click() -> None:
    left_click()
    time.sleep(0.08)
    left_click()


def right_click() -> None:
    _send(MOUSEEVENTF_RIGHTDOWN)
    _send(MOUSEEVENTF_RIGHTUP)


def scroll(steps: int) -> None:
    amount = max(-12, min(12, int(steps)))
    if amount == 0:
        return
    _send(MOUSEEVENTF_WHEEL, amount * WHEEL_DELTA)
