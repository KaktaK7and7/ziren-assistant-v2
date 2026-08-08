from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.file_navigation import (
    FileNavigationError,
    latest_download,
    open_explorer,
    open_folder,
    open_safe_file,
    reveal_file,
)


FOLDER_ACTIONS = {
    "downloads": [
        "открой загрузки",
        "открой папку загрузки",
        "открой папку загрузок",
        "покажи загрузки",
    ],
    "documents": [
        "открой документы",
        "открой папку документы",
        "покажи документы",
    ],
    "pictures": [
        "открой изображения",
        "открой картинки",
        "открой папку изображения",
        "покажи изображения",
    ],
    "desktop": [
        "открой папку рабочий стол",
        "открой папку рабочего стола",
    ],
    "music": [
        "открой папку музыка",
        "открой папку музыки",
    ],
    "videos": [
        "открой видео",
        "открой папку видео",
    ],
}

EXPLORER_TRIGGERS = [
    "открой проводник",
    "запусти проводник",
]

REVEAL_LATEST_TRIGGERS = [
    "покажи последний скачанный файл",
    "найди последний скачанный файл",
    "покажи последний файл в загрузках",
]

OPEN_LATEST_TRIGGERS = [
    "открой последний скачанный файл",
    "открой последний файл в загрузках",
]


class SystemFileNavigationModule(AssistantModule):
    feature_id = "system.file_navigation"
    display_name = "Файлы и системные папки"
    plan = Plan.FREE
    default_trigger_groups = {
        "files.explorer": {
            "display_name": "Открыть Проводник",
            "triggers": EXPLORER_TRIGGERS,
        },
        "files.folder": {
            "display_name": "Открыть системную папку",
            "triggers": [
                trigger
                for triggers in FOLDER_ACTIONS.values()
                for trigger in triggers
            ],
        },
        "files.latest.reveal": {
            "display_name": "Показать последний скачанный файл",
            "triggers": REVEAL_LATEST_TRIGGERS,
        },
        "files.latest.open": {
            "display_name": "Открыть безопасный последний скачанный файл",
            "triggers": OPEN_LATEST_TRIGGERS,
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action = self._find_action(text)

        if action is None:
            return ModuleResponse(text="Не поняла команду файлов.")

        action_id, argument = action

        try:
            if action_id == "explorer":
                open_explorer()
                return ModuleResponse(text="Открываю Проводник.")

            if action_id == "folder" and argument:
                path = open_folder(argument)
                return ModuleResponse(text=f"Открываю папку {path.name}.")

            if action_id == "latest_reveal":
                path = latest_download()
                reveal_file(path)
                return ModuleResponse(
                    text=f"Показываю последний скачанный файл: {path.name}."
                )

            if action_id == "latest_open":
                path = latest_download()
                open_safe_file(path)
                return ModuleResponse(
                    text=f"Открываю последний скачанный файл: {path.name}."
                )
        except FileNavigationError as error:
            return ModuleResponse(text=str(error))
        except OSError as error:
            return ModuleResponse(text=f"Не смогла открыть файл или папку: {error}")

        return ModuleResponse(text="Не смогла выполнить команду файлов.")

    def _find_action(self, text: str) -> tuple[str, str | None] | None:
        normalized = self._normalize(text)
        matches: list[tuple[int, str, str | None]] = []

        for trigger in EXPLORER_TRIGGERS:
            if self._contains(normalized, trigger):
                matches.append((len(trigger), "explorer", None))

        for folder_id, triggers in FOLDER_ACTIONS.items():
            for trigger in triggers:
                if self._contains(normalized, trigger):
                    matches.append((len(trigger), "folder", folder_id))

        for trigger in REVEAL_LATEST_TRIGGERS:
            if self._contains(normalized, trigger):
                matches.append((len(trigger), "latest_reveal", None))

        for trigger in OPEN_LATEST_TRIGGERS:
            if self._contains(normalized, trigger):
                matches.append((len(trigger), "latest_open", None))

        if not matches:
            return None

        _, action_id, argument = max(matches, key=lambda item: item[0])
        return action_id, argument

    def _normalize(self, value: str) -> str:
        return " ".join(str(value or "").lower().replace("ё", "е").split())

    def _contains(self, normalized: str, trigger: str) -> bool:
        normalized_trigger = self._normalize(trigger)
        return re.search(
            rf"\b{re.escape(normalized_trigger)}\b",
            normalized,
        ) is not None
