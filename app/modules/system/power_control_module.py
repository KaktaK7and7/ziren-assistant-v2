from __future__ import annotations

import re
import time
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.power import (
    PowerControlError,
    lock_workstation,
    restart_workstation,
    shutdown_workstation,
    sleep_workstation,
)


PENDING_SECONDS = 30.0


class SystemPowerControlModule(AssistantModule):
    feature_id = "system.power"
    display_name = "Питание и блокировка"
    plan = Plan.FREE
    default_trigger_groups = {
        "power.lock": {
            "display_name": "Заблокировать компьютер",
            "triggers": ["заблокируй компьютер", "заблокируй пк", "заблокируй windows"],
            "argument_hint": "Без аргументов. Блокирует текущий сеанс сразу.",
        },
        "power.sleep.request": {
            "display_name": "Запросить спящий режим",
            "triggers": ["переведи компьютер в спящий режим", "спящий режим", "усыпи компьютер"],
            "argument_hint": "Без аргументов. Только создаёт запрос; требуется отдельное подтверждение.",
        },
        "power.shutdown.request": {
            "display_name": "Запросить выключение компьютера",
            "triggers": ["выключи компьютер", "выключи пк", "выключи windows"],
            "argument_hint": "Без аргументов. Только создаёт запрос; требуется отдельное подтверждение.",
        },
        "power.restart.request": {
            "display_name": "Запросить перезагрузку компьютера",
            "triggers": ["перезагрузи компьютер", "перезагрузи пк", "перезапусти компьютер"],
            "argument_hint": "Без аргументов. Только создаёт запрос; требуется отдельное подтверждение.",
        },
        "power.confirm": {
            "display_name": "Подтвердить ожидающее действие питания",
            "triggers": [
                "подтверждаю",
                "да подтверждаю",
                "подтверждаю выключение",
                "подтверждаю перезагрузку",
                "подтверждаю спящий режим",
            ],
            "argument_hint": "Без аргументов. Выполняет только ранее запрошенное действие, если прошло не больше 30 секунд.",
        },
        "power.cancel": {
            "display_name": "Отменить ожидающее действие питания",
            "triggers": ["отмени выключение", "отмени перезагрузку", "отмени спящий режим", "отмена"],
            "argument_hint": "Без аргументов. Сбрасывает ожидающее действие питания.",
        },
    }

    def __init__(self) -> None:
        self._pending_action = ""
        self._pending_until = 0.0

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action_id = self._find_action(text)
        if action_id is None:
            return ModuleResponse(text="Не поняла команду питания.")
        return self._execute_action_id(action_id)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id not in self.default_trigger_groups:
            return None
        return self._execute_action_id(action_id)

    def _execute_action_id(self, action_id: str) -> ModuleResponse:
        if action_id == "power.lock":
            try:
                lock_workstation()
            except PowerControlError as error:
                return ModuleResponse(text=str(error))
            return ModuleResponse(text="Блокирую компьютер.")

        if action_id == "power.cancel":
            self._clear_pending()
            return ModuleResponse(text="Отменила действие питания.")

        if action_id == "power.confirm":
            return self._confirm()

        pending_by_action = {
            "power.sleep.request": ("sleep", "спящий режим"),
            "power.shutdown.request": ("shutdown", "выключение компьютера"),
            "power.restart.request": ("restart", "перезагрузку компьютера"),
        }
        pending = pending_by_action.get(action_id)
        if pending is None:
            return ModuleResponse(text="Неизвестная команда питания.")

        action, label = pending
        self._pending_action = action
        self._pending_until = time.monotonic() + PENDING_SECONDS
        return ModuleResponse(
            text=(
                f"Подтверди {label} в течение 30 секунд. "
                "Скажи: подтверждаю."
            )
        )

    def _confirm(self) -> ModuleResponse:
        if not self._pending_action or time.monotonic() > self._pending_until:
            self._clear_pending()
            return ModuleResponse(text="Нет активного действия питания для подтверждения.")

        action = self._pending_action
        self._clear_pending()
        try:
            if action == "sleep":
                sleep_workstation()
                return ModuleResponse(text="Перевожу компьютер в спящий режим.")
            if action == "shutdown":
                shutdown_workstation()
                return ModuleResponse(text="Выключаю компьютер.")
            if action == "restart":
                restart_workstation()
                return ModuleResponse(text="Перезагружаю компьютер.")
        except PowerControlError as error:
            return ModuleResponse(text=str(error))

        return ModuleResponse(text="Действие питания отменено.")

    def _clear_pending(self) -> None:
        self._pending_action = ""
        self._pending_until = 0.0

    def _find_action(self, text: str) -> str | None:
        normalized = self._normalize(text)
        matches: list[tuple[int, str]] = []
        for action_id in self.default_trigger_groups:
            for trigger in self.get_action_triggers(action_id):
                needle = self._normalize(trigger)
                if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                    matches.append((len(needle), action_id))
        return max(matches, key=lambda item: item[0])[1] if matches else None

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
