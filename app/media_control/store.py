import hashlib
import re
from dataclasses import asdict

from app.media_control.models import MusicPreset
from app.storage.local_store import APP_DIR, read_json, write_json


MUSIC_PRESETS_FILE = APP_DIR / "music_presets.json"


def normalize_alias(text: str) -> str:
    normalized = text.strip().lower().replace("ё", "е")
    normalized = re.sub(r"[^\w\s:/?&=.#%+-]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


class MusicPresetStore:
    def __init__(self, path=MUSIC_PRESETS_FILE) -> None:
        self.path = path

    def list_presets(self) -> list[MusicPreset]:
        data = read_json(self.path, {"presets": []})
        raw_presets = data.get("presets", []) if isinstance(data, dict) else []

        if not isinstance(raw_presets, list):
            return []

        presets: list[MusicPreset] = []

        for item in raw_presets:
            if not isinstance(item, dict):
                continue

            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []

            presets.append(
                MusicPreset(
                    preset_id=str(item.get("preset_id", "")).strip(),
                    name=str(item.get("name", "")).strip(),
                    url=str(item.get("url", "")).strip(),
                    aliases=self._normalize_aliases(aliases),
                    enabled=bool(item.get("enabled", True)),
                )
            )

        return [
            preset
            for preset in presets
            if preset.preset_id and preset.name and preset.url
        ]

    def save_preset(self, preset: MusicPreset) -> MusicPreset:
        saved_preset = MusicPreset(
            preset_id=preset.preset_id.strip() or self._stable_id(preset.name, preset.url),
            name=preset.name.strip(),
            url=preset.url.strip(),
            aliases=self._normalize_aliases(preset.aliases),
            enabled=bool(preset.enabled),
        )

        if not saved_preset.name:
            raise ValueError("Название сценария обязательно.")

        if not saved_preset.url:
            raise ValueError("Ссылка обязательна.")

        presets = self.list_presets()
        updated = False

        for index, existing in enumerate(presets):
            if existing.preset_id == saved_preset.preset_id:
                presets[index] = saved_preset
                updated = True
                break

        if not updated:
            presets.append(saved_preset)

        self._write_presets(presets)
        return saved_preset

    def delete_preset(self, preset_id: str) -> None:
        self._write_presets(
            [preset for preset in self.list_presets() if preset.preset_id != preset_id]
        )

    def find_by_query(self, query: str) -> MusicPreset | None:
        normalized_query = normalize_alias(query)

        if not normalized_query:
            return None

        for preset in self.list_presets():
            if not preset.enabled:
                continue

            candidates = [preset.name, *preset.aliases]
            normalized_candidates = {normalize_alias(candidate) for candidate in candidates}

            if normalized_query in normalized_candidates:
                return preset

        return None

    def _write_presets(self, presets: list[MusicPreset]) -> None:
        write_json(self.path, {"presets": [asdict(preset) for preset in presets]})

    def _stable_id(self, name: str, url: str) -> str:
        source = f"{normalize_alias(name)}|{url.strip().lower()}"
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:14]
        return f"music:{digest}"

    def _normalize_aliases(self, aliases: list[str]) -> list[str]:
        normalized_aliases: list[str] = []
        seen: set[str] = set()

        for alias in aliases:
            if not isinstance(alias, str):
                continue

            normalized = normalize_alias(alias)

            if not normalized or normalized in seen:
                continue

            normalized_aliases.append(normalized)
            seen.add(normalized)

        return normalized_aliases
