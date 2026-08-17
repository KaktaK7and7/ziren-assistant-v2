from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import WindowsInputError, send_hotkey


class SystemScreenRecordingModule(AssistantModule):
    feature_id = "system.screen_recording"
    display_name = "Запись экрана"
    plan = Plan.FREE
    default_trigger_groups = {
        "screen_recording.toggle": {
            "display_name": "Начать или остановить запись экрана",
            "triggers": [
                "начни запись экрана",
                "запусти запись экрана",
                "останови запись экрана",
                "закончи запись экрана",
                "переключи запись экрана",
            ],
            "argument_hint": "Без аргументов. Использует системное сочетание Windows Game Bar Win+Alt+R.",
        }
    }

    def can_handle(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(
            re.search(rf"\b{re.escape(self._normalize(trigger))}\b", normalized)
            for trigger in self.get_action_triggers("screen_recording.toggle")
            if trigger.strip()
        )

    def handle(self, text: str) -> ModuleResponse:
        return self._toggle(text)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id != "screen_recording.toggle":
            return None
        return self._toggle("")

    def _toggle(self, text: str) -> ModuleResponse:
        try:
            send_hotkey(["win", "alt", "r"])
        except WindowsInputError as error:
            return ModuleResponse(text=f"Не смогла передать команду записи экрана: {error}")

        normalized = self._normalize(text)
        if "останов" in normalized or "закончи" in normalized:
            return ModuleResponse(text="Передала Windows команду остановить запись экрана.")
        if "начни" in normalized or "запусти" in normalized:
            return ModuleResponse(text="Передала Windows команду начать запись экрана.")
        return ModuleResponse(text="Переключила запись экрана через Windows Game Bar.")

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
