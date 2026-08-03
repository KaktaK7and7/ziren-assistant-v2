from __future__ import annotations

import os
import time


def normalized_to_pixels(
    x: float,
    y: float,
    width: int,
    height: int,
) -> tuple[int, int]:
    if (
        not 0 <= x <= 1
        or not 0 <= y <= 1
        or width <= 0
        or height <= 0
    ):
        raise ValueError("Invalid click coordinates")

    return (
        min(width - 1, max(0, round(x * (width - 1)))),
        min(height - 1, max(0, round(y * (height - 1)))),
    )


def point_inside_rect(
    x: int,
    y: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> bool:
    return left <= x < right and top <= y < bottom


def click_primary_screen(
    x: float,
    y: float,
    expected_foreground_window: int | None = None,
) -> tuple[int, int]:
    if os.name != "nt":
        raise RuntimeError("Safe screen click is available only on Windows")

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    if expected_foreground_window:
        if not user32.IsWindow(expected_foreground_window):
            raise RuntimeError("The analyzed window is no longer available")

        active_window = int(user32.GetForegroundWindow())
        if active_window != expected_foreground_window:
            raise RuntimeError("The analyzed window is no longer active")

    screen_width = int(user32.GetSystemMetrics(0))
    screen_height = int(user32.GetSystemMetrics(1))

    window_rect: tuple[int, int, int, int] | None = None
    if expected_foreground_window:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(expected_foreground_window, ctypes.byref(rect)):
            raise RuntimeError("Cannot verify the analyzed window position")
        window_rect = (rect.left, rect.top, rect.right, rect.bottom)
        center_x = (rect.left + rect.right) // 2
        center_y = (rect.top + rect.bottom) // 2
        if not (
            0 <= center_x < screen_width
            and 0 <= center_y < screen_height
        ):
            raise RuntimeError("The analyzed window is not on the primary screen")

    pixel_x, pixel_y = normalized_to_pixels(
        x,
        y,
        screen_width,
        screen_height,
    )
    if window_rect and not point_inside_rect(
        pixel_x,
        pixel_y,
        *window_rect,
    ):
        raise RuntimeError("The proposed target is outside the analyzed window")

    if not user32.SetCursorPos(pixel_x, pixel_y):
        raise RuntimeError("Windows rejected cursor movement")

    time.sleep(0.08)
    if (
        expected_foreground_window
        and int(user32.GetForegroundWindow()) != expected_foreground_window
    ):
        raise RuntimeError("The analyzed window changed before the click")

    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    return pixel_x, pixel_y
