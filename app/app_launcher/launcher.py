import os
import subprocess
import webbrowser
from pathlib import Path

from app.app_launcher.models import AppTarget


class AppLauncher:
    def launch(self, target: AppTarget) -> None:
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

        os.startfile(target.launch_uri)

    def _launch_shortcut(self, target: AppTarget) -> None:
        if not target.path:
            raise RuntimeError("У ярлыка нет пути.")

        shortcut_path = Path(target.path)

        if not shortcut_path.exists():
            raise RuntimeError(f"Ярлык не найден: {target.path}")

        os.startfile(str(shortcut_path))

    def _launch_system(self, target: AppTarget) -> None:
        if target.launch_uri:
            if target.launch_uri.startswith(("http://", "https://")):
                webbrowser.open(target.launch_uri)
                return

            os.startfile(target.launch_uri)
            return

        if not target.path:
            raise RuntimeError("У системного приложения нет команды запуска.")

        subprocess.Popen([target.path], shell=False)

    def _launch_exe(self, target: AppTarget) -> None:
        if not target.path:
            raise RuntimeError("У приложения нет пути к exe.")

        exe_path = Path(target.path)

        if not exe_path.exists():
            raise RuntimeError(f"Файл запуска не найден: {target.path}")

        subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), shell=False)
