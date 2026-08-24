from typing import Any

from app.storage.local_store import APP_DIR, read_json, write_json


TRIGGER_FILE = APP_DIR / "feature_triggers.json"
LEGACY_ACTION_ID = "__legacy__"
MAX_TRIGGERS_PER_ACTION = 50
MAX_TRIGGER_LENGTH = 80


class TriggerStore:
    def load(self) -> dict[str, Any]:
        data = read_json(TRIGGER_FILE, default={})

        if not isinstance(data, dict):
            return {}

        return {
            feature_id: value
            for feature_id, value in data.items()
            if isinstance(feature_id, str)
        }

    def save(self, data: dict[str, Any]) -> None:
        normalized: dict[str, Any] = {}

        for feature_id, value in data.items():
            if not isinstance(feature_id, str):
                continue

            if isinstance(value, list):
                normalized[feature_id] = self._normalize_triggers(value)
                continue

            if isinstance(value, dict):
                normalized[feature_id] = self._normalize_store_groups(value)

        write_json(TRIGGER_FILE, normalized)

    def get(self, feature_id: str, default: list[str]) -> list[str]:
        data = self.load()
        stored = data.get(feature_id)

        if isinstance(stored, list):
            return self._normalize_triggers(stored)

        if isinstance(stored, dict):
            triggers: list[str] = []

            for value in stored.values():
                if isinstance(value, list):
                    triggers.extend(value)

            return self._normalize_triggers(triggers)

        return self._normalize_triggers(default)

    def set(self, feature_id: str, triggers: list[str]) -> list[str]:
        data = self.load()
        normalized = self._normalize_triggers(triggers)
        data[feature_id] = normalized
        self.save(data)
        return normalized

    def get_groups(
        self,
        feature_id: str,
        default_groups: dict[str, dict],
    ) -> dict[str, dict]:
        data = self.load()
        stored = data.get(feature_id)

        if isinstance(stored, list):
            groups = self._copy_default_groups(default_groups)
            legacy_triggers = self._normalize_triggers(stored)

            if legacy_triggers:
                groups[LEGACY_ACTION_ID] = {
                    "display_name": "Общие триггеры",
                    "triggers": legacy_triggers,
                    "melissa_semantic": False,
                    "snake_triggers": True,
                }

            return groups

        if not isinstance(stored, dict):
            return self._copy_default_groups(default_groups)

        normalized_store_groups = self._normalize_store_groups(stored)
        groups = self._copy_default_groups(default_groups)

        for action_id, triggers in normalized_store_groups.items():
            if action_id not in default_groups:
                continue

            current = groups[action_id]
            groups[action_id] = {
                **current,
                "display_name": str(
                    default_groups[action_id].get("display_name", action_id)
                ),
                "triggers": list(triggers),
            }

        return groups

    def set_groups(
        self,
        feature_id: str,
        groups: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        data = self.load()
        normalized = self._normalize_store_groups(groups)
        data[feature_id] = normalized
        self.save(data)
        return normalized

    def _copy_default_groups(self, default_groups: dict[str, dict]) -> dict[str, dict]:
        groups: dict[str, dict] = {}

        for action_id, group in default_groups.items():
            if not isinstance(action_id, str) or not isinstance(group, dict):
                continue

            groups[action_id] = {
                "display_name": str(group.get("display_name", action_id)),
                "triggers": self._normalize_triggers(group.get("triggers", [])),
                "melissa_semantic": group.get("melissa_semantic", True) is not False,
                "snake_triggers": group.get("snake_triggers", True) is not False,
            }

        return groups

    def _normalize_store_groups(self, groups: dict[Any, Any]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}

        for action_id, triggers in groups.items():
            if not isinstance(action_id, str) or not isinstance(triggers, list):
                continue

            normalized[action_id] = self._normalize_triggers(triggers)

        return normalized

    def _normalize_triggers(self, triggers: list[Any]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for trigger in triggers:
            if not isinstance(trigger, str):
                continue

            value = trigger.strip().lower()

            if not value:
                continue

            value = value[:MAX_TRIGGER_LENGTH]

            if value in seen:
                continue

            normalized.append(value)
            seen.add(value)

            if len(normalized) >= MAX_TRIGGERS_PER_ACTION:
                break

        return normalized
