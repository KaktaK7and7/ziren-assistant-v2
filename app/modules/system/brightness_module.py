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


_ORDINAL_MONITORS = {
    "первый": 1,
    "первого": 1,
    "первом": 1,
    "второй": 2,
    "второго": 2,
    "втором": 2,
    "третий": 3,
    "третьего": 3,
    "третьем": 3,
    "четвертый": 4,
    "четвертого": 4,
    "четвертом": 4,
}

_PERCENT_WORDS = {
    "ноль": 0,
    "один": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
    "сто": 100,
}


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
        return self.execute_action(action_id, arguments) or ModuleResponse(
            text="Не смогла изменить яркость."
        )

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
                        text=(
                            f"Установила яркость монитора {changed[0]} "
                            f"на {percent} процентов."
                        )
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
        monitor = self._monitor_from_text(normalized)

        if self._starts_with_action_trigger(normalized, "brightness.get"):
            return "brightness.get", {"monitor": monitor} if monitor else {}

        if not self._starts_with_action_trigger(normalized, "brightness.set"):
            return None

        percent = self._percent_from_text(normalized)
        arguments: dict[str, Any] = {}
        if percent is not None:
            arguments["percent"] = percent
        if monitor is not None:
            arguments["monitor"] = monitor
        return "brightness.set", arguments

    def _starts_with_action_trigger(self, text: str, action_id: str) -> bool:
        return any(
            text == needle or text.startswith(needle + " ")
            for trigger in self.get_action_triggers(action_id)
            if (needle := self._normalize(trigger))
        )

    @classmethod
    def _monitor_from_text(cls, text: str) -> int | None:
        numeric_patterns = (
            r"(?:монитор\w*|экран\w*)\s*(?:номер\s*)?(\d+)",
            r"(\d+)\s*(?:монитор\w*|экран\w*)",
        )
        for pattern in numeric_patterns:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                return value if value > 0 else None

        words = text.split()
        for index, word in enumerate(words):
            value = _ORDINAL_MONITORS.get(word)
            if value is None:
                continue
            nearby = words[max(0, index - 1) : index + 3]
            if any(token.startswith("монитор") or token.startswith("экран") for token in nearby):
                return value
        return None

    @classmethod
    def _percent_from_text(cls, text: str) -> int | None:
        explicit = re.findall(r"\b(100|\d{1,2})\s*(?:%|процент\w*)\b", text)
        if explicit:
            return int(explicit[-1])

        numeric_values = [int(value) for value in re.findall(r"\b(100|\d{1,2})\b", text)]
        if numeric_values:
            # When a monitor number and brightness are both present, brightness
            # is conventionally the last number: "монитор 2 яркость 40".
            return numeric_values[-1]

        words = [word.strip(" ,.!?:;") for word in text.split()]
        for index in range(len(words) - 1):
            left = _PERCENT_WORDS.get(words[index])
            right = _PERCENT_WORDS.get(words[index + 1])
            if left is not None and left >= 20 and left % 10 == 0 and right is not None and right < 10:
                value = left + right
                if 0 <= value <= 100:
                    return value

        for word in reversed(words):
            value = _PERCENT_WORDS.get(word)
            if value is not None and 0 <= value <= 100:
                return value
        return None

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
