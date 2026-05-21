import re
from pathlib import Path

from app.app_launcher.known_aliases import get_known_aliases_for_name
from app.app_launcher.matcher import normalize_text
from app.app_launcher.models import AppTarget

try:
    import winreg
except Exception:
    winreg = None


class SteamIndexer:
    def index(self) -> list[AppTarget]:
        steam_path = self._find_steam_path()

        if steam_path is None:
            return []

        library_paths = self._find_library_paths(steam_path)
        targets: list[AppTarget] = []
        seen_appids: set[str] = set()

        for library_path in library_paths:
            steamapps_path = library_path / "steamapps"

            if not steamapps_path.exists():
                continue

            for manifest_path in steamapps_path.glob("appmanifest_*.acf"):
                manifest = self._read_text(manifest_path)

                if not manifest:
                    continue

                appid = self._extract_vdf_value(manifest, "appid")
                name = self._extract_vdf_value(manifest, "name")
                installdir = self._extract_vdf_value(manifest, "installdir")

                if not appid or not name or appid in seen_appids:
                    continue

                seen_appids.add(appid)
                aliases = self._build_aliases(name, installdir)

                targets.append(
                    AppTarget(
                        target_id=f"steam:{appid}",
                        name=name,
                        type="steam",
                        launch_uri=f"steam://run/{appid}",
                        appid=appid,
                        aliases=aliases,
                        source="steam",
                        confidence_bonus=0.08,
                    )
                )

        return targets

    def _find_steam_path(self) -> Path | None:
        registry_paths = [
            (getattr(winreg, "HKEY_CURRENT_USER", None), r"Software\Valve\Steam", "SteamPath"),
            (
                getattr(winreg, "HKEY_LOCAL_MACHINE", None),
                r"SOFTWARE\WOW6432Node\Valve\Steam",
                "InstallPath",
            ),
        ]

        if winreg is not None:
            for hive, key_path, value_name in registry_paths:
                if hive is None:
                    continue

                path = self._read_registry_value(hive, key_path, value_name)

                if path:
                    steam_path = Path(path)

                    if steam_path.exists():
                        return steam_path

        for fallback in [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
        ]:
            if fallback.exists():
                return fallback

        return None

    def _find_library_paths(self, steam_path: Path) -> list[Path]:
        paths = [steam_path]
        libraryfolders_path = steam_path / "steamapps" / "libraryfolders.vdf"
        content = self._read_text(libraryfolders_path)

        if content:
            for match in re.finditer(r'"path"\s*"([^"]+)"', content):
                library_path = Path(match.group(1).replace("\\\\", "\\"))

                if library_path.exists() and library_path not in paths:
                    paths.append(library_path)

        return paths

    def _build_aliases(self, name: str, installdir: str | None) -> list[str]:
        aliases = [normalize_text(name), *get_known_aliases_for_name(name)]

        if installdir:
            aliases.append(normalize_text(installdir))

        normalized_name = normalize_text(name)

        if "counter strike" in normalized_name:
            aliases.extend(get_known_aliases_for_name("Counter-Strike 2"))
        if "dota" in normalized_name:
            aliases.extend(get_known_aliases_for_name("Dota 2"))
        if "everlasting summer" in normalized_name:
            aliases.extend(get_known_aliases_for_name("Everlasting Summer"))
        if "world of tanks" in normalized_name or "мир танков" in normalized_name:
            aliases.extend(get_known_aliases_for_name("World of Tanks"))

        return [alias for alias in dict.fromkeys(aliases) if alias]

    def _read_registry_value(self, hive, key_path: str, value_name: str) -> str | None:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                return str(value)
        except Exception:
            return None

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def _extract_vdf_value(self, content: str, key: str) -> str | None:
        match = re.search(rf'"{re.escape(key)}"\s*"([^"]*)"', content)
        return match.group(1).strip() if match else None
