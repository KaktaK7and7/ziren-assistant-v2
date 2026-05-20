from app.storage.local_store import APP_DIR, read_json, write_json


TRIGGER_FILE = APP_DIR / "feature_triggers.json"
MAX_TRIGGERS_PER_FEATURE = 50
MAX_TRIGGER_LENGTH = 80


class TriggerStore:
    def load(self) -> dict[str, list[str]]:
        data = read_json(TRIGGER_FILE, default={})

        if not isinstance(data, dict):
            return {}

        normalized: dict[str, list[str]] = {}

        for feature_id, triggers in data.items():
            if not isinstance(feature_id, str) or not isinstance(triggers, list):
                continue

            normalized[feature_id] = self._normalize_triggers(triggers)

        return normalized

    def save(self, data: dict[str, list[str]]) -> None:
        normalized: dict[str, list[str]] = {}

        for feature_id, triggers in data.items():
            if not isinstance(feature_id, str):
                continue

            normalized[feature_id] = self._normalize_triggers(triggers)

        write_json(TRIGGER_FILE, normalized)

    def get(self, feature_id: str, default: list[str]) -> list[str]:
        data = self.load()

        if feature_id in data:
            return list(data[feature_id])

        return self._normalize_triggers(default)

    def set(self, feature_id: str, triggers: list[str]) -> list[str]:
        data = self.load()
        normalized = self._normalize_triggers(triggers)
        data[feature_id] = normalized
        self.save(data)
        return normalized

    def _normalize_triggers(self, triggers: list[str]) -> list[str]:
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

            if len(normalized) >= MAX_TRIGGERS_PER_FEATURE:
                break

        return normalized
