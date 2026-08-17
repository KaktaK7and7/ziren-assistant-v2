from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.screenshot import (
    ScreenshotError,
    capture_and_save,
    open_screenshot_directory,
)


SCREENSHOT_TRIGGERS = [
    "скриншот",
    "скрин",
    "сделать скриншот",
    "сделай скриншот",
    "сделай скрин",
    "сохрани скриншот",
    "сохрани снимок экрана",
]

SCREENSHOT_FOLDER_TRIGGERS = [
    "открой папку скриншотов",
    "открой папку со скриншотами",
    "открой папку куда сохраняются скриншоты",
    "открой папку куда мы сохраняем скриншоты",
    "покажи папку скриншотов",
    "покажи где сохраняются скриншоты",
    "где лежат скриншоты",
]


class SystemScreenshotModule(AssistantModule):
    feature_id = "system.screenshot"
    display_name = "Снимок экрана"
    plan = Plan.FREE
    default_trigger_groups = {
        "screenshot.save": {
            "display_name": "Сохранить снимок экрана",
            "triggers": SCREENSHOT_TRIGGERS,
            "argument_hint": "Без аргументов. Делает снимок основного экрана и сохраняет его локально.",
        },
        "screenshot.open_folder": {
            "display_name": "Открыть папку скриншотов",
            "triggers": SCREENSHOT_FOLDER_TRIGGERS,
            "argument_hint": "Без аргументов. Открывает только фиксированную локальную папку Pictures/Ziren/Screenshots.",
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action = self._find_action(text)
        if action == "screenshot.open_folder":
            return self._open_folder()
        return self._save()

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id == "screenshot.save":
            return self._save()
        if action_id == "screenshot.open_folder":
            return self._open_folder()
        return None

    def _save(self) -> ModuleResponse:
        try:
            path = capture_and_save()
        except (ScreenshotError, OSError, RuntimeError) as error:
            return ModuleResponse(text=f"Не получилось сделать скриншот: {error}")

        return ModuleResponse(
            text=(
                "Скриншот сохранён в папку Изображения, Ziren, Screenshots. "
                f"Файл {path.name}."
            )
        )

    def _open_folder(self) -> ModuleResponse:
        try:
            open_screenshot_directory()
        except (ScreenshotError, OSError, RuntimeError) as error:
            return ModuleResponse(text=f"Не получилось открыть папку скриншотов: {error}")
        return ModuleResponse(text="Открываю папку скриншотов.")

    def _find_action(self, text: str) -> str | None:
        normalized = self._normalize(text)
        if "отправ" in normalized:
            return None

        matches: list[tuple[int, str]] = []
        for action_id in ("screenshot.open_folder", "screenshot.save"):
            for trigger in self.get_action_triggers(action_id):
                needle = self._normalize(trigger)
                if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                    matches.append((len(needle), action_id))

        return max(matches, key=lambda item: item[0])[1] if matches else None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value or "").lower().replace("ё", "е").split())
