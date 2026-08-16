from __future__ import annotations

import ctypes
import os
import subprocess


class PowerControlError(RuntimeError):
    pass


def _require_windows() -> None:
    if os.name != "nt":
        raise PowerControlError("Управление питанием доступно только в Windows")


def lock_workstation() -> None:
    _require_windows()
    if not ctypes.windll.user32.LockWorkStation():
        raise PowerControlError("Windows не смогла заблокировать сеанс")


def sleep_workstation() -> None:
    _require_windows()
    result = ctypes.windll.powrprof.SetSuspendState(False, False, False)
    if not result:
        raise PowerControlError("Windows не смогла перейти в спящий режим")


def shutdown_workstation() -> None:
    _run_shutdown(["/s", "/t", "0"])


def restart_workstation() -> None:
    _run_shutdown(["/r", "/t", "0"])


def _run_shutdown(arguments: list[str]) -> None:
    _require_windows()
    executable = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "shutdown.exe")
    if not os.path.isfile(executable):
        executable = "shutdown.exe"
    try:
        subprocess.Popen(
            [executable, *arguments],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise PowerControlError("Windows не приняла команду питания") from error
