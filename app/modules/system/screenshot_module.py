from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.screenshot import ScreenshotError, capture_and_save


SCREENSHOT_TRIGGERS = [
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
            for trigger in SCREENSHOT_TRIGGERS
        )

    def handle(self, text: str) -> ModuleResponse:
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
