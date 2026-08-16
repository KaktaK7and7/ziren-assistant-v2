from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.brightness import (
    BrightnessControlError,
    get_brightness,
    set_brightness,
)


class SystemBrightnessModule(AssistantModule):
    feature_id = "system.brightness"
    display_name = "Яркость мониторов"
    plan = Plan.FREE
    default_trigger_groups = {
        "brightness.get": {
            "display_name": "Узнать яркость монитора",
            "triggers": [
                "какая яркость",
                "какая яркость монитора",
                "покажи яркость",
                "узнай яркость монитора",
            ],
            "argument_hint": "arguments.monitor — необязательный номер монитора, начиная с 1.",
        },
        "brightness.set": {
            "display_name": "Установить яркость монитора",
            "triggers": [
                "яркость",
                "установи яркость",
                "поставь яркость",
                "измени яркость",
            ],
            "argument_hint": "arguments.percent — яркость 0–100; arguments.monitor — необязательный номер монитора.",
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._parse_local(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        parsed = self._parse_local(text)
        if parsed is None:
            return ModuleResponse(text="Не поняла команду яркости.")
        action_id, arguments = parsed
        return self.execute_action(action_id, arguments) or ModuleResponse(text="Не смогла изменить яркость.")

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        args = arguments or {}
        monitor = self._optional_int(args.get("monitor"))

        try:
            if action_id == "brightness.get":
                values = get_brightness(monitor)
                summary = ", ".join(
                    f"монитор {item.index}: {item.percent} процентов"
                    for item in values
                )
                return ModuleResponse(text=f"Яркость: {summary}.")

            if action_id == "brightness.set":
                percent = self._optional_int(args.get("percent"))
                if percent is None or not 0 <= percent <= 100:
                    return ModuleResponse(text="Укажи яркость от 0 до 100 процентов.")
                changed = set_brightness(percent, monitor)
                if len(changed) == 1:
                    return ModuleResponse(
                        text=f"Установила яркость монитора {changed[0]} на {percent} процентов."
                    )
                return ModuleResponse(
                    text=f"Установила яркость {percent} процентов на мониторах: "
                    + ", ".join(str(index) for index in changed)
                    + "."
                )
        except BrightnessControlError as error:
            return ModuleResponse(text=str(error))

        return None

    def _parse_local(self, text: str) -> tuple[str, dict[str, Any]] | None:
        normalized = self._normalize(text)
        if any(
            normalized == self._normalize(trigger)
            or normalized.startswith(self._normalize(trigger) + " ")
            for trigger in self.get_action_triggers("brightness.get")
        ) and not re.search(r"\b\d{1,3}\b", normalized):
            monitor = self._monitor_from_text(normalized)
            return "brightness.get", {"monitor": monitor} if monitor else {}

        if not any(
            normalized == self._normalize(trigger)
            or normalized.startswith(self._normalize(trigger) + " ")
            for trigger in self.get_action_triggers("brightness.set")
        ):
            return None

        percent_match = re.search(r"\b(100|\d{1,2})\s*(?:%|процент\w*)?\b", normalized)
        if not percent_match:
            return "brightness.set", {}
        monitor = self._monitor_from_text(normalized)
        return "brightness.set", {
            "percent": int(percent_match.group(1)),
            **({"monitor": monitor} if monitor else {}),
        }

    @staticmethod
    def _monitor_from_text(text: str) -> int | None:
        match = re.search(r"(?:монитор\w*|экран\w*)\s+(\d+)", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
