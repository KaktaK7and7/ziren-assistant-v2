import ctypes
import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path

from app.app_launcher.debug import app_debug_step
from app.app_launcher.models import AppTarget


def is_access_denied_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "access is denied" in text
        or "winerror 5" in text
        or "permission denied" in text
        or "отказано в доступе" in text
    )


def _run_as_admin(
    path: str,
    parameters: str | None = None,
    cwd: str | None = None,
) -> None:
    if platform.system().lower() != "windows":
        raise RuntimeError("Запуск от имени администратора поддерживается только на Windows.")

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        path,
        parameters or None,
        cwd or None,
        1,
    )

    if result <= 32:
        if result == 31:
            raise RuntimeError("Не удалось открыть приложение. Проверь путь в настройках приложений.")

        raise RuntimeError(f"Не удалось открыть запрос администратора. Код ShellExecute: {result}")


class AppLauncher:
    def __init__(self) -> None:
        self.last_launch_was_elevated = False

    def launch(self, target: AppTarget) -> None:
        self.last_launch_was_elevated = False

        if target.type == "steam":
            self._launch_steam(target)
            return

        if target.type == "shortcut":
            self._launch_shortcut(target)
            return

        if target.type == "system":
            self._launch_system(target)
            return

        if target.type == "exe":
            self._launch_exe(target)
            return

        raise RuntimeError(f"Неизвестный тип приложения: {target.type}")

    def _launch_steam(self, target: AppTarget) -> None:
        if not target.launch_uri:
            raise RuntimeError("У Steam-игры нет launch uri.")

        self._log_normal_attempt(target, target.launch_uri)
        os.startfile(target.launch_uri)

    def _launch_shortcut(self, target: AppTarget) -> None:
        if not target.path:
            raise RuntimeError("У ярлыка нет пути.")

        shortcut_path = Path(target.path)

        if shortcut_path.suffix.lower() != ".lnk" or not shortcut_path.exists():
            raise RuntimeError("Выберите ярлык .lnk.")

        self._log_normal_attempt(target, str(shortcut_path))

        try:
            os.startfile(str(shortcut_path))
        except Exception as error:
            if not is_access_denied_error(error):
                raise

            self._try_runas(target, str(shortcut_path))

    def _launch_system(self, target: AppTarget) -> None:
        if target.launch_uri and target.launch_uri.startswith(("http://", "https://")):
            self._log_normal_attempt(target, target.launch_uri)
            webbrowser.open(target.launch_uri)
            return

        if not target.path:
            raise RuntimeError("У системного приложения нет команды запуска.")

        self._log_normal_attempt(target, target.path)

        try:
            subprocess.Popen([target.path], shell=False)
        except Exception as error:
            if not is_access_denied_error(error):
                raise

            self._try_runas(target, target.path)

    def _launch_exe(self, target: AppTarget) -> None:
        if not target.path:
            raise RuntimeError("У приложения нет пути к exe.")

        exe_path = Path(target.path)

        if exe_path.suffix.lower() != ".exe" or not exe_path.exists():
            raise RuntimeError("Выберите настоящий .exe файл приложения.")

        parent_dir = exe_path.parent
        self._log_normal_attempt(target, str(exe_path))

        try:
            subprocess.Popen([str(exe_path)], cwd=str(parent_dir), shell=False)
        except Exception as error:
            if not is_access_denied_error(error):
                raise

            self._try_runas(target, str(exe_path), cwd=str(parent_dir))

    def _try_runas(
        self,
        target: AppTarget,
        path: str,
        parameters: str | None = None,
        cwd: str | None = None,
    ) -> None:
        app_debug_step(
            "launch access denied, trying runas",
            {
                "target": target.name,
                "type": target.type,
                "basename": os.path.basename(path),
            },
        )

        try:
            _run_as_admin(path, parameters=parameters, cwd=cwd)
        except Exception:
            app_debug_step(
                "launch runas failed",
                {
                    "target": target.name,
                    "type": target.type,
                    "basename": os.path.basename(path),
                },
            )
            raise

        self.last_launch_was_elevated = True
        app_debug_step(
            "launch runas requested",
            {
                "target": target.name,
                "type": target.type,
                "basename": os.path.basename(path),
            },
        )

    def _log_normal_attempt(self, target: AppTarget, path_or_uri: str) -> None:
        app_debug_step(
            "launch normal attempt",
            {
                "target": target.name,
                "type": target.type,
                "basename": os.path.basename(path_or_uri),
            },
        )
