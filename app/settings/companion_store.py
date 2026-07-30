from copy import deepcopy
from typing import Any

from app.storage.local_store import APP_DIR, read_json, write_json


COMPANION_SETTINGS_FILE = APP_DIR / "companion_settings.json"
DEFAULT_COMPANION_SETTINGS = {
    "command_reactions_enabled": True,
    "command_reaction_chance": 0.3,
    "command_reaction_cooldown_minutes": 10,
    "proactive_dialogue_enabled": False,
    "proactive_idle_min_minutes": 20,
    "proactive_idle_max_minutes": 45,
    "quiet_hours_enabled": True,
    "quiet_hours_start": 23,
    "quiet_hours_end": 9,
}


class CompanionSettingsStore:
    def get(self) -> dict:
        raw = read_json(COMPANION_SETTINGS_FILE, default={})
        return self._normalize(raw)

    def update(self, values: dict[str, Any]) -> dict:
        current = self.get()
        allowed = set(DEFAULT_COMPANION_SETTINGS)
        merged = {
            **current,
            **{
                key: value
                for key, value in values.items()
                if key in allowed
            },
        }
        normalized = self._normalize(merged)
        write_json(COMPANION_SETTINGS_FILE, normalized)
        return normalized

    def _normalize(self, raw: Any) -> dict:
        source = raw if isinstance(raw, dict) else {}
        result = deepcopy(DEFAULT_COMPANION_SETTINGS)

        for key in (
            "command_reactions_enabled",
            "proactive_dialogue_enabled",
            "quiet_hours_enabled",
        ):
            if isinstance(source.get(key), bool):
                result[key] = source[key]

        result["command_reaction_chance"] = self._float_between(
            source.get("command_reaction_chance"),
            DEFAULT_COMPANION_SETTINGS["command_reaction_chance"],
            0.0,
            1.0,
        )
        result["command_reaction_cooldown_minutes"] = self._int_between(
            source.get("command_reaction_cooldown_minutes"),
            DEFAULT_COMPANION_SETTINGS["command_reaction_cooldown_minutes"],
            1,
            120,
        )
        result["proactive_idle_min_minutes"] = self._int_between(
            source.get("proactive_idle_min_minutes"),
            DEFAULT_COMPANION_SETTINGS["proactive_idle_min_minutes"],
            5,
            240,
        )
        result["proactive_idle_max_minutes"] = self._int_between(
            source.get("proactive_idle_max_minutes"),
            DEFAULT_COMPANION_SETTINGS["proactive_idle_max_minutes"],
            result["proactive_idle_min_minutes"],
            360,
        )
        result["quiet_hours_start"] = self._int_between(
            source.get("quiet_hours_start"),
            DEFAULT_COMPANION_SETTINGS["quiet_hours_start"],
            0,
            23,
        )
        result["quiet_hours_end"] = self._int_between(
            source.get("quiet_hours_end"),
            DEFAULT_COMPANION_SETTINGS["quiet_hours_end"],
            0,
            23,
        )
        return result

    @staticmethod
    def _int_between(value: Any, fallback: int, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            return fallback

        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return fallback

        return min(maximum, max(minimum, normalized))

    @staticmethod
    def _float_between(
        value: Any,
        fallback: float,
        minimum: float,
        maximum: float,
    ) -> float:
        if isinstance(value, bool):
            return fallback

        try:
            normalized = float(value)
        except (TypeError, ValueError):
            return fallback

        return min(maximum, max(minimum, normalized))
