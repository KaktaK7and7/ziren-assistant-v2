from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import WindowsInputError, send_hotkey


BROWSER_ACTIONS = {
    "new_tab": {
        "keys": ["ctrl", "t"],
        "triggers": ["новая вкладка", "открой новую вкладку", "создай новую вкладку"],
        "response": "Открыла новую вкладку.",
    },
    "close_tab": {
        "keys": ["ctrl", "w"],
        "triggers": ["закрой вкладку", "закрой текущую вкладку"],
        "response": "Закрыла вкладку.",
    },
    "restore_tab": {
        "keys": ["ctrl", "shift", "t"],
        "triggers": ["верни вкладку", "восстанови вкладку", "верни закрытую вкладку"],
        "response": "Вернула закрытую вкладку.",
    },
    "back": {
        "keys": ["alt", "left"],
        "triggers": ["назад в браузере", "вернись назад", "предыдущая страница"],
        "response": "Перехожу назад.",
    },
    "forward": {
        "keys": ["alt", "right"],
        "triggers": ["вперед в браузере", "вперёд в браузере", "следующая страница"],
        "response": "Перехожу вперёд.",
    },
    "reload": {
        "keys": ["ctrl", "r"],
        "triggers": ["обнови страницу", "перезагрузи страницу"],
        "response": "Обновила страницу.",
    },
    "address": {
        "keys": ["ctrl", "l"],
        "triggers": ["адресная строка", "перейди в адресную строку", "выдели адрес сайта"],
        "response": "Выделила адресную строку.",
    },
    "next_tab": {
        "keys": ["ctrl", "tab"],
        "triggers": ["следующая вкладка", "переключи на следующую вкладку"],
        "response": "Переключила вкладку.",
    },
    "previous_tab": {
        "keys": ["ctrl", "shift", "tab"],
        "triggers": ["предыдущая вкладка", "переключи на предыдущую вкладку"],
        "response": "Переключила вкладку назад.",
    },
}


class SystemBrowserControlModule(AssistantModule):
    feature_id = "system.browser_control"
    display_name = "Управление браузером"
    plan = Plan.FREE
    default_trigger_groups = {
        f"browser.{action_id}": {
            "display_name": action_id.replace("_", " ").title(),
            "triggers": action["triggers"],
            "argument_hint": "Без аргументов. Действие применяется к активному браузеру.",
        }
        for action_id, action in BROWSER_ACTIONS.items()
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action_id = self._find_action(text)

        if action_id is None:
            return ModuleResponse(text="Не поняла команду браузера.")

        return self._execute(action_id)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if not action_id.startswith("browser."):
            return None
        local_id = action_id.removeprefix("browser.")
        if local_id not in BROWSER_ACTIONS:
            return None
        return self._execute(local_id)

    def _execute(self, action_id: str) -> ModuleResponse:
        action = BROWSER_ACTIONS[action_id]

        try:
            send_hotkey(action["keys"])
        except WindowsInputError as error:
            return ModuleResponse(text=f"Не смогла выполнить команду браузера: {error}")

        return ModuleResponse(text=action["response"])

    def _find_action(self, text: str) -> str | None:
        normalized = " ".join(str(text or "").lower().replace("ё", "е").split())
        matches: list[tuple[int, str]] = []

        for action_id in BROWSER_ACTIONS:
            for trigger in self.get_action_triggers(f"browser.{action_id}"):
                normalized_trigger = " ".join(trigger.lower().replace("ё", "е").split())
                if normalized_trigger and re.search(rf"\b{re.escape(normalized_trigger)}\b", normalized):
                    matches.append((len(normalized_trigger), action_id))

        if not matches:
            return None

        return max(matches, key=lambda item: item[0])[1]
