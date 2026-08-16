from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.screenshot import ScreenshotError, capture_and_save


SCREENSHOT_TRIGGERS = [
    "скриншот",
    "скрин",
    "сделать скриншот",
    "сделай скриншот",
    "сделай скрин",
    "сохрани скриншот",
    "сохрани снимок экрана",
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
        }
    }

    def can_handle(self, text: str) -> bool:
        normalized = " ".join(str(text or "").lower().replace("ё", "е").split())
        if "отправ" in normalized:
            return False

        return any(
            re.search(
                rf"\b{re.escape(trigger.lower().replace('ё', 'е'))}\b",
                normalized,
            )
            for trigger in self.get_action_triggers("screenshot.save")
            if trigger.strip()
        )

    def handle(self, text: str) -> ModuleResponse:
        return self._save()

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id != "screenshot.save":
            return None
        return self._save()

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
