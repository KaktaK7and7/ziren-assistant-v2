import hashlib
import re
from dataclasses import asdict
from pathlib import Path
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
        target.target_id = self.stable_target_id(target)
        targets[target.target_id] = asdict(target)
        self.save(data)

    def remember_alias(self, query: str, target: AppTarget) -> None:
        data = self.load()
        target.target_id = self.stable_target_id(target)
        data.setdefault("targets", {})[target.target_id] = asdict(target)
        data.setdefault("aliases", {})[self.normalize_alias(query)] = target.target_id
        self.save(data)

    def list_apps(self) -> list[dict]:
        data = self.load()
        targets = data.get("targets", {})
        aliases = data.get("aliases", {})
        apps: list[dict] = []

        for target_id, target_data in targets.items():
            if not isinstance(target_data, dict):
                continue

            target = self._target_from_dict(target_data)

            if target is None:
                continue

            mapped_aliases = [
                alias
                for alias, alias_target_id in aliases.items()
                if alias_target_id == target_id
            ]
            target.aliases = list(dict.fromkeys([*target.aliases, *mapped_aliases]))
            apps.append(asdict(target))

        return sorted(apps, key=lambda item: str(item.get("name", "")).lower())

    def stable_target_id(self, target: AppTarget) -> str:
        target_type = target.type.lower().strip()

        if target_type in {"exe", "shortcut"} and target.path:
            identity = str(Path(target.path).expanduser().resolve(strict=False)).lower()
        elif target_type == "steam" and target.appid:
            identity = str(target.appid).strip()
        else:
            identity = (target.path or target.launch_uri or target.name).strip().lower()

        digest = hashlib.sha1(f"{target_type}:{identity}".encode("utf-8")).hexdigest()[:12]
        return f"{target_type}:{digest}"

    def validate_manual_target(self, target: AppTarget) -> AppTarget:
        target.type = target.type.lower().strip()
        target.name = target.name.strip()
        target.source = target.source.strip() or "manual"

        if target.type not in {"exe", "shortcut", "steam", "system"}:
            raise ValueError("Выберите тип запуска приложения.")

        if target.type in {"exe", "shortcut"}:
            raw_path = str(target.path or "").strip()
            expected_extension = ".exe" if target.type == "exe" else ".lnk"
            error_message = (
                "Выберите настоящий .exe файл приложения."
                if target.type == "exe"
                else "Выберите ярлык .lnk."
            )

            if not raw_path or not raw_path.lower().endswith(expected_extension):
                raise ValueError(error_message)

            path = Path(raw_path).expanduser()

            if not path.exists() or not path.is_file():
                raise ValueError(error_message)

            target.path = str(path.resolve())
            target.appid = None
            target.launch_uri = None

            if not target.name:
                target.name = path.stem

        elif target.type == "steam":
            appid = str(target.appid or "").strip()

            if not appid or not appid.isdigit():
                raise ValueError("Укажите Steam AppID.")

            target.appid = appid
            target.path = None
            target.launch_uri = f"steam://run/{appid}"

            if not target.name:
                target.name = f"Steam {appid}"

        elif target.type == "system":
            command = str(target.path or target.launch_uri or "").strip()

            if not command:
                raise ValueError("Укажите системную команду Windows.")

            target.path = command
            target.appid = None
            target.launch_uri = None

            if not target.name:
                target.name = command

        target.target_id = self.stable_target_id(target)
        return target

    def cleanup_duplicates(self) -> None:
        data = self.load()
        self._dedupe_data(data)
        self.save(data)

    def upsert_target_with_aliases(
        self,
        target: AppTarget,
        aliases: list[str],
        original_target_id: str | None = None,
    ) -> None:
        target = self.validate_manual_target(target)
        normalized_aliases = [
            self.normalize_alias(alias)
            for alias in aliases
            if isinstance(alias, str) and self.normalize_alias(alias)
        ]
        data = self.load()
        targets = data.setdefault("targets", {})
        alias_map = data.setdefault("aliases", {})
        existing_id = self._find_duplicate_target_id(
            data,
            target,
            original_target_id=original_target_id,
        )

        if existing_id and existing_id != target.target_id:
            existing_data = targets.pop(existing_id, None)

            if isinstance(existing_data, dict):
                existing_target = self._target_from_dict(existing_data)

                if existing_target is not None:
                    target.aliases = [
                        *existing_target.aliases,
                        *target.aliases,
                    ]

                for alias, alias_target_id in list(alias_map.items()):
                    if alias_target_id == existing_id:
                        alias_map[alias] = target.target_id

        existing_data = targets.get(target.target_id)

        if isinstance(existing_data, dict):
            existing_target = self._target_from_dict(existing_data)

            if existing_target is not None:
                target.aliases = [
                    *existing_target.aliases,
                    *target.aliases,
                ]

        target.aliases = list(dict.fromkeys([*target.aliases, *normalized_aliases]))
        targets[target.target_id] = asdict(target)

        for alias, target_id in list(alias_map.items()):
            if target_id == target.target_id and alias not in target.aliases:
                del alias_map[alias]

        for alias in target.aliases:
            alias_map[alias] = target.target_id

        self._dedupe_data(data)
        self.save(data)

    def delete_target(self, target_id: str) -> None:
        data = self.load()
        data.setdefault("targets", {}).pop(target_id, None)
        aliases = data.setdefault("aliases", {})

        for alias, alias_target_id in list(aliases.items()):
            if alias_target_id == target_id:
                del aliases[alias]

        self.save(data)

    def delete_alias(self, alias: str) -> None:
        normalized_alias = self.normalize_alias(alias)
        data = self.load()
        target_id = data.setdefault("aliases", {}).pop(normalized_alias, None)

        if target_id:
            target_data = data.setdefault("targets", {}).get(target_id)

            if isinstance(target_data, dict):
                aliases = target_data.get("aliases", [])

                if isinstance(aliases, list):
                    target_data["aliases"] = [
                        item
                        for item in aliases
                        if self.normalize_alias(str(item)) != normalized_alias
                    ]

        self.save(data)

    def add_alias(self, alias: str, target_id: str) -> None:
        normalized_alias = self.normalize_alias(alias)

        if not normalized_alias:
            raise ValueError("alias must be a non-empty string")

        data = self.load()
        target_data = data.setdefault("targets", {}).get(target_id)

        if not isinstance(target_data, dict):
            raise ValueError("unknown target_id")

        data.setdefault("aliases", {})[normalized_alias] = target_id
        target_aliases = target_data.setdefault("aliases", [])

        if not isinstance(target_aliases, list):
            target_aliases = []
            target_data["aliases"] = target_aliases

        normalized_existing = {
            self.normalize_alias(str(item)) for item in target_aliases
        }

        if normalized_alias not in normalized_existing:
            target_aliases.append(normalized_alias)

        self.save(data)

    def _find_duplicate_target_id(
        self,
        data: dict,
        target: AppTarget,
        original_target_id: str | None = None,
    ) -> str | None:
        targets = data.get("targets", {})

        if not isinstance(targets, dict):
            return None

        lookup_ids = [target.target_id]

        if original_target_id and original_target_id not in lookup_ids:
            lookup_ids.append(original_target_id)

        for target_id in lookup_ids:
            if target_id in targets:
                return target_id

        target_keys = self._dedupe_keys(target)

        for target_id, target_data in targets.items():
            if not isinstance(target_data, dict):
                continue

            existing = self._target_from_dict(target_data)

            if existing is None:
                continue

            if any(key in target_keys for key in self._dedupe_keys(existing)):
                return target_id

        return None

    def _dedupe_data(self, data: dict) -> None:
        targets = data.setdefault("targets", {})
        aliases = data.setdefault("aliases", {})

        if not isinstance(targets, dict) or not isinstance(aliases, dict):
            return

        canonical_by_key: dict[tuple[str, str], str] = {}

        for target_id, target_data in list(targets.items()):
            if not isinstance(target_data, dict):
                del targets[target_id]
                continue

            target = self._target_from_dict(target_data)

            if target is None:
                del targets[target_id]
                continue

            stable_id = self.stable_target_id(target)
            keys = self._dedupe_keys(target)
            canonical_id = canonical_by_key.get(("id", stable_id))

            if canonical_id is None:
                for key in keys:
                    canonical_id = canonical_by_key.get(key)

                    if canonical_id is not None:
                        break

            if canonical_id is None:
                canonical_id = stable_id
                for key in keys:
                    canonical_by_key[key] = canonical_id

                canonical_by_key[("id", stable_id)] = canonical_id

                if target_id != canonical_id:
                    del targets[target_id]
                    for alias, alias_target_id in list(aliases.items()):
                        if alias_target_id == target_id:
                            aliases[alias] = canonical_id

                target.target_id = canonical_id
                targets[canonical_id] = asdict(target)
                continue

            canonical_data = targets.get(canonical_id)
            canonical_target = (
                self._target_from_dict(canonical_data)
                if isinstance(canonical_data, dict)
                else None
            )

            if canonical_target is None:
                target.target_id = canonical_id
                targets[canonical_id] = asdict(target)
            else:
                canonical_target.aliases = list(
                    dict.fromkeys([*canonical_target.aliases, *target.aliases])
                )
                targets[canonical_id] = asdict(canonical_target)

            if target_id != canonical_id:
                del targets[target_id]

            for alias, alias_target_id in list(aliases.items()):
                if alias_target_id == target_id:
                    aliases[alias] = canonical_id

        for alias, target_id in list(aliases.items()):
            if not isinstance(alias, str) or not isinstance(target_id, str):
                del aliases[alias]
                continue

            normalized_alias = self.normalize_alias(alias)

            if not normalized_alias or target_id not in targets:
                del aliases[alias]
                continue

            if normalized_alias != alias:
                del aliases[alias]
                aliases[normalized_alias] = target_id

            target_data = targets.get(target_id)

            if isinstance(target_data, dict):
                target_aliases = target_data.setdefault("aliases", [])

                if not isinstance(target_aliases, list):
                    target_aliases = []
                    target_data["aliases"] = target_aliases

                existing = {
                    self.normalize_alias(str(item)) for item in target_aliases
                }

                if normalized_alias not in existing:
                    target_aliases.append(normalized_alias)

    def _dedupe_keys(self, target: AppTarget) -> list[tuple[str, str]]:
        target_type = target.type.lower().strip()
        keys = [(f"{target_type}:name", self.normalize_alias(target.name))]

        if target_type in {"exe", "shortcut"} and target.path:
            keys.append(
                (
                    f"{target_type}:path",
                    str(Path(target.path).expanduser().resolve(strict=False)).lower(),
                )
            )

        elif target_type == "steam" and target.appid:
            keys.append((f"{target_type}:appid", str(target.appid).strip()))

        return [key for key in keys if key[1]]

    def _target_from_dict(self, data: dict[str, Any]) -> AppTarget | None:
        try:
            aliases = data.get("aliases", [])

            if not isinstance(aliases, list):
                aliases = []

            spoken_name = data.get("spoken_name")

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
                spoken_name=str(spoken_name) if spoken_name is not None else None,
            )
        except Exception:
            return None

    def _empty_cache(self) -> dict:
        return {"aliases": {}, "targets": {}}
