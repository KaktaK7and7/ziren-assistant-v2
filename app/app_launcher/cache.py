import re
from dataclasses import asdict
from typing import Any

from app.app_launcher.models import AppTarget
from app.storage.local_store import APP_DIR, read_json, write_json


CACHE_FILE = APP_DIR / "app_launcher_cache.json"


class AppLauncherCache:
    def load(self) -> dict:
        data = read_json(CACHE_FILE, default={})

        if not isinstance(data, dict):
            return self._empty_cache()

        aliases = data.get("aliases", {})
        targets = data.get("targets", {})

        if not isinstance(aliases, dict) or not isinstance(targets, dict):
            return self._empty_cache()

        return {"aliases": aliases, "targets": targets}

    def save(self, data: dict) -> None:
        write_json(CACHE_FILE, data)

    def normalize_alias(self, value: str) -> str:
        value = value.lower().replace("ё", "е").strip()
        return re.sub(r"\s+", " ", value)

    def get_alias(self, query: str) -> AppTarget | None:
        data = self.load()
        alias = self.normalize_alias(query)
        target_id = data.get("aliases", {}).get(alias)

        if not isinstance(target_id, str):
            return None

        target_data = data.get("targets", {}).get(target_id)

        if not isinstance(target_data, dict):
            return None

        return self._target_from_dict(target_data)

    def remember_target(self, target: AppTarget) -> None:
        data = self.load()
        targets = data.setdefault("targets", {})
        targets[target.target_id] = asdict(target)
        self.save(data)

    def remember_alias(self, query: str, target: AppTarget) -> None:
        data = self.load()
        data.setdefault("targets", {})[target.target_id] = asdict(target)
        data.setdefault("aliases", {})[self.normalize_alias(query)] = target.target_id
        self.save(data)

    def _target_from_dict(self, data: dict[str, Any]) -> AppTarget | None:
        try:
            aliases = data.get("aliases", [])

            if not isinstance(aliases, list):
                aliases = []

            return AppTarget(
                target_id=str(data["target_id"]),
                name=str(data["name"]),
                type=str(data["type"]),
                launch_uri=data.get("launch_uri"),
                path=data.get("path"),
                appid=data.get("appid"),
                aliases=[str(alias) for alias in aliases],
                source=str(data.get("source", "")),
                confidence_bonus=float(data.get("confidence_bonus", 0.0)),
            )
        except Exception:
            return None

    def _empty_cache(self) -> dict:
        return {"aliases": {}, "targets": {}}
