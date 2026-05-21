import os
from pathlib import Path

from app.app_launcher.known_aliases import get_known_aliases_for_name
from app.app_launcher.matcher import is_dangerous_exe_name, normalize_text
from app.app_launcher.models import AppTarget

try:
    import winreg
except Exception:
    winreg = None


class WindowsIndexer:
    def index(self) -> list[AppTarget]:
        targets = []
        targets.extend(self._system_targets())
        targets.extend(self._shortcut_targets())
        targets.extend(self._registry_app_paths())
        return self._deduplicate(targets)

    def _system_targets(self) -> list[AppTarget]:
        return [
            AppTarget(
                target_id="system:explorer",
                name="Проводник",
                type="system",
                path="explorer.exe",
                aliases=["проводник", "файлы", "открой файлы", "explorer"],
                source="system",
            ),
            AppTarget(
                target_id="system:taskmgr",
                name="Диспетчер задач",
                type="system",
                path="taskmgr.exe",
                aliases=["диспетчер задач", "task manager", "taskmgr"],
                source="system",
            ),
            AppTarget(
                target_id="system:notepad",
                name="Блокнот",
                type="system",
                path="notepad.exe",
                aliases=["блокнот", "notepad"],
                source="system",
            ),
            AppTarget(
                target_id="system:calc",
                name="Калькулятор",
                type="system",
                path="calc.exe",
                aliases=["калькулятор", "calc"],
                source="system",
            ),
            AppTarget(
                target_id="system:browser",
                name="Браузер",
                type="system",
                launch_uri="https://www.google.com",
                aliases=["браузер", "интернет", "google", "гугл", "хром", "chrome"],
                source="system",
            ),
        ]

    def _shortcut_targets(self) -> list[AppTarget]:
        targets: list[AppTarget] = []

        for root, source in self._shortcut_roots():
            if not root.exists():
                continue

            try:
                shortcuts = root.rglob("*.lnk")
            except Exception:
                continue

            for shortcut_path in shortcuts:
                try:
                    if not shortcut_path.is_file():
                        continue
                except Exception:
                    continue

                name = shortcut_path.stem

                if is_dangerous_exe_name(name) or is_dangerous_exe_name(str(shortcut_path)):
                    continue

                aliases = [normalize_text(name), *get_known_aliases_for_name(name)]
                target_source = source
                confidence_bonus = 0.05

                if self._is_wargaming_shortcut(name):
                    aliases.extend(
                        [
                            "танки",
                            "танчики",
                            "wot",
                            "вот",
                            "world of tanks",
                            "мир танков",
                        ]
                    )
                    target_source = "wargaming_shortcut"
                    confidence_bonus = 0.12

                targets.append(
                    AppTarget(
                        target_id=f"shortcut:{shortcut_path}",
                        name=name,
                        type="shortcut",
                        path=str(shortcut_path),
                        aliases=[alias for alias in dict.fromkeys(aliases) if alias],
                        source=target_source,
                        confidence_bonus=confidence_bonus,
                    )
                )

        return targets

    def _registry_app_paths(self) -> list[AppTarget]:
        if winreg is None:
            return []

        targets: list[AppTarget] = []
        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        ]

        for hive, key_path in roots:
            try:
                with winreg.OpenKey(hive, key_path) as root_key:
                    key_count = winreg.QueryInfoKey(root_key)[0]

                    for index in range(key_count):
                        subkey_name = winreg.EnumKey(root_key, index)
                        target = self._read_app_path_target(root_key, subkey_name)

                        if target is not None:
                            targets.append(target)
            except Exception:
                continue

        return targets

    def _read_app_path_target(self, root_key, subkey_name: str) -> AppTarget | None:
        try:
            with winreg.OpenKey(root_key, subkey_name) as app_key:
                value, _ = winreg.QueryValueEx(app_key, "")
                exe_path = Path(str(value).strip('"'))
        except Exception:
            return None

        if not exe_path.exists() or is_dangerous_exe_name(str(exe_path)):
            return None

        name = exe_path.stem
        aliases = [normalize_text(name), *get_known_aliases_for_name(name)]

        return AppTarget(
            target_id=f"exe:{exe_path}",
            name=name,
            type="exe",
            path=str(exe_path),
            aliases=[alias for alias in dict.fromkeys(aliases) if alias],
            source="app_paths",
        )

    def _shortcut_roots(self) -> list[tuple[Path, str]]:
        appdata = Path(os.getenv("APPDATA", ""))
        userprofile = Path(os.getenv("USERPROFILE", ""))
        public = Path(os.getenv("PUBLIC", r"C:\Users\Public"))

        return [
            (Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"), "start_menu"),
            (appdata / r"Microsoft\Windows\Start Menu\Programs", "start_menu"),
            (userprofile / "Desktop", "desktop"),
            (public / "Desktop", "desktop"),
        ]

    def _is_wargaming_shortcut(self, name: str) -> bool:
        normalized = normalize_text(name)
        markers = ["wargaming", "world of tanks", "мир танков", "lesta", "tanks"]
        return any(marker in normalized for marker in markers)

    def _deduplicate(self, targets: list[AppTarget]) -> list[AppTarget]:
        deduped: list[AppTarget] = []
        seen: set[str] = set()

        for target in targets:
            if target.target_id in seen:
                continue

            deduped.append(target)
            seen.add(target.target_id)

        return deduped
