from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.monitors import MonitorControlError, move_active_window


ACTIONS = {
    "monitor.window_left": {
        "direction": "left",
        "display_name": "Перенести активное окно на монитор слева",
        "triggers": [
            "перенеси окно на левый монитор",
            "перемести окно на монитор слева",
            "окно на левый монитор",
        ],
        "response": "Перенесла активное окно на монитор слева.",
    },
    "monitor.window_right": {
        "direction": "right",
        "display_name": "Перенести активное окно на монитор справа",
        "triggers": [
            "перенеси окно на правый монитор",
            "перемести окно на монитор справа",
            "окно на правый монитор",
        ],
        "response": "Перенесла активное окно на монитор справа.",
    },
}


class SystemMonitorControlModule(AssistantModule):
    feature_id = "system.monitors"
    display_name = "Несколько мониторов"
    plan = Plan.FREE
    default_trigger_groups = {
        action_id: {
            "display_name": action["display_name"],
            "triggers": action["triggers"],
            "argument_hint": (
                "Без аргументов. Действие применяется к активному окну Windows "
                "и считается успешным только после подтверждения смены монитора."
            ),
        }
        for action_id, action in ACTIONS.items()
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action_id = self._find_action(text)
        if action_id is None:
            return ModuleResponse(text="Не поняла команду для мониторов.")
        return self._execute(action_id)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id not in ACTIONS:
            return None
        return self._execute(action_id)

    def _execute(self, action_id: str) -> ModuleResponse:
        action = ACTIONS[action_id]
        try:
            move_active_window(action["direction"])
        except MonitorControlError as error:
            return ModuleResponse(text=f"Не смогла перенести окно: {error}")
        return ModuleResponse(text=action["response"])

    def _find_action(self, text: str) -> str | None:
        normalized = " ".join(str(text or "").lower().replace("ё", "е").split())
        matches: list[tuple[int, str]] = []
        for action_id in ACTIONS:
            for trigger in self.get_action_triggers(action_id):
                needle = " ".join(trigger.lower().replace("ё", "е").split())
                if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                    matches.append((len(needle), action_id))
        return max(matches, key=lambda item: item[0])[1] if matches else None
