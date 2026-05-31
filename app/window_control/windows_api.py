import ctypes
import platform
import subprocess
from ctypes import wintypes

import psutil

from app.window_control.models import WindowTarget


SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010

EXCLUDED_TITLES = {
    "program manager",
    "windows input experience",
    "microsoft text input application",
    "default ime",
}

PROCESS_CLOSE_DENYLIST = {
    "explorer.exe",
    "system",
    "system idle process",
    "wininit.exe",
    "winlogon.exe",
    "csrss.exe",
    "smss.exe",
    "services.exe",
    "lsass.exe",
    "dwm.exe",
    "taskhostw.exe",
    "sihost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
}


def _ensure_windows() -> None:
    if platform.system().lower() != "windows":
        raise RuntimeError("Управление окнами поддерживается только на Windows.")


def list_windows() -> list[WindowTarget]:
    _ensure_windows()

    user32 = ctypes.windll.user32
    windows: list[WindowTarget] = []

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        title_length = user32.GetWindowTextLengthW(hwnd)

        if title_length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, buffer, title_length + 1)
        title = buffer.value.strip()

        if not title or title.lower() in EXCLUDED_TITLES:
            return True

        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        pid = int(process_id.value)
        process_name = ""

        try:
            process_name = psutil.Process(pid).name()
        except Exception:
            process_name = ""

        windows.append(
            WindowTarget(
                hwnd=int(hwnd),
                title=title,
                process_id=pid,
                process_name=process_name,
                visible=True,
                minimized=bool(user32.IsIconic(hwnd)),
            )
        )
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return windows


def minimize_window(hwnd: int) -> None:
    _ensure_windows()
    ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)


def maximize_window(hwnd: int) -> None:
    _ensure_windows()
    ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)


def restore_window(hwnd: int) -> None:
    _ensure_windows()
    ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)


def focus_window(hwnd: int) -> None:
    restore_window(hwnd)


def close_window(hwnd: int) -> None:
    _ensure_windows()
    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def force_close_process(process_id: int) -> None:
    _ensure_windows()

    try:
        process = psutil.Process(process_id)
        process_name = process.name().lower()

        if process_name in PROCESS_CLOSE_DENYLIST:
            raise RuntimeError("Нельзя закрыть системный процесс.")

        process.terminate()

        try:
            process.wait(timeout=1.5)
            return
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.5)
    except psutil.AccessDenied as error:
        raise RuntimeError("Нет прав для закрытия процесса.") from error
    except psutil.NoSuchProcess:
        return


def show_desktop() -> None:
    _ensure_windows()
    subprocess.Popen(
        [
            "powershell",
            "-Command",
            "(New-Object -ComObject Shell.Application).ToggleDesktop()",
        ]
    )
