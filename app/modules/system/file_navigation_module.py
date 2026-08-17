from __future__ import annotations

import re
from typing import Any

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
    "downloads": {
        "display_name": "Открыть Загрузки",
        "triggers": [
            "открой загрузки",
            "открой папку загрузки",
            "открой папку загрузок",
            "покажи загрузки",
        ],
    },
    "documents": {
        "display_name": "Открыть Документы",
        "triggers": [
            "открой документы",
            "открой папку документы",
            "покажи документы",
        ],
    },
    "pictures": {
        "display_name": "Открыть Изображения",
        "triggers": [
            "открой изображения",
            "открой картинки",
            "открой папку изображения",
            "покажи изображения",
        ],
    },
    "desktop": {
        "display_name": "Открыть Рабочий стол",
        "triggers": [
            "открой папку рабочий стол",
            "открой папку рабочего стола",
        ],
    },
    "music": {
        "display_name": "Открыть Музыку",
        "triggers": [
            "открой папку музыка",
            "открой папку музыки",
        ],
    },
    "videos": {
        "display_name": "Открыть Видео",
        "triggers": [
            "открой видео",
            "открой папку видео",
        ],
    },
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
            "argument_hint": "Без аргументов. Открывает новое окно Проводника.",
        },
        **{
            f"files.folder.{folder_id}": {
                "display_name": folder["display_name"],
                "triggers": folder["triggers"],
                "argument_hint": "Без аргументов. Открывает фиксированную пользовательскую системную папку.",
            }
            for folder_id, folder in FOLDER_ACTIONS.items()
        },
        "files.latest.reveal": {
            "display_name": "Показать последний скачанный файл",
            "triggers": REVEAL_LATEST_TRIGGERS,
            "argument_hint": "Без аргументов. Выделяет самый новый файл в папке Загрузки.",
        },
        "files.latest.open": {
            "display_name": "Открыть безопасный последний скачанный файл",
            "triggers": OPEN_LATEST_TRIGGERS,
            "argument_hint": "Без аргументов. Открывает только файл с разрешённым безопасным расширением.",
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action_id = self._find_action(text)
        if action_id is None:
            return ModuleResponse(text="Не поняла команду файлов.")
        return self.execute_action(action_id, {}) or ModuleResponse(
            text="Не смогла выполнить команду файлов."
        )

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        try:
            if action_id == "files.explorer":
                open_explorer()
                return ModuleResponse(text="Открываю Проводник.")

            if action_id.startswith("files.folder."):
                folder_id = action_id.removeprefix("files.folder.")
                if folder_id not in FOLDER_ACTIONS:
                    return None
                path = open_folder(folder_id)
                return ModuleResponse(text=f"Открываю папку {path.name}.")

            if action_id == "files.latest.reveal":
                path = latest_download()
                reveal_file(path)
                return ModuleResponse(
                    text=f"Показываю последний скачанный файл: {path.name}."
                )

            if action_id == "files.latest.open":
                path = latest_download()
                open_safe_file(path)
                return ModuleResponse(
                    text=f"Открываю последний скачанный файл: {path.name}."
                )
        except FileNavigationError as error:
            return ModuleResponse(text=str(error))
        except OSError as error:
            return ModuleResponse(text=f"Не смогла открыть файл или папку: {error}")

        return None

    def _find_action(self, text: str) -> str | None:
        normalized = self._normalize(text)
        matches: list[tuple[int, str]] = []

        for action_id in self.default_trigger_groups:
            for trigger in self.get_action_triggers(action_id):
                needle = self._normalize(trigger)
                if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                    matches.append((len(needle), action_id))

        if not matches:
            return None

        return max(matches, key=lambda item: item[0])[1]

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value or "").lower().replace("ё", "е").split())
