from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.system_status import (
    GpuTemperatureError,
    read_nvidia_temperatures,
    read_system_status,
)


SUMMARY_TRIGGERS = [
    "состояние компьютера",
    "нагрузка компьютера",
    "как загружен компьютер",
    "сколько занято оперативки",
    "сколько оперативной памяти занято",
    "сколько места на диске",
    "сколько свободно на диске",
]
GPU_TEMP_TRIGGERS = [
    "температура видеокарты",
    "какая температура видеокарты",
    "температура gpu",
    "температура гпу",
    "насколько горячая видеокарта",
]


class SystemStatusModule(AssistantModule):
    feature_id = "system.status"
    display_name = "Состояние компьютера"
    plan = Plan.FREE
    default_trigger_groups = {
        "system.status.summary": {
            "display_name": "Показать нагрузку и память",
            "triggers": SUMMARY_TRIGGERS,
            "argument_hint": "Без аргументов. Читает CPU, RAM и свободное место диска C.",
        },
        "system.status.gpu_temperature": {
            "display_name": "Температура NVIDIA GPU",
            "triggers": GPU_TEMP_TRIGGERS,
            "argument_hint": "Без аргументов. Читает температуру через установленный NVIDIA nvidia-smi.",
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action = self._find_action(text)
        if action == "gpu_temperature":
            return self._gpu_temperature()
        return self._summary()

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id == "system.status.summary":
            return self._summary()
        if action_id == "system.status.gpu_temperature":
            return self._gpu_temperature()
        return None

    def _summary(self) -> ModuleResponse:
        try:
            status = read_system_status()
        except Exception as error:
            return ModuleResponse(text=f"Не смогла получить состояние компьютера: {error}")

        return ModuleResponse(
            text=(
                f"Процессор загружен на {status.cpu_percent:.0f} процентов. "
                f"Оперативная память: {status.memory_used_gb:.1f} из "
                f"{status.memory_total_gb:.1f} гигабайт, это {status.memory_percent:.0f} процентов. "
                f"На диске C свободно {status.disk_free_gb:.1f} из "
                f"{status.disk_total_gb:.1f} гигабайт."
            )
        )

    def _gpu_temperature(self) -> ModuleResponse:
        try:
            rows = read_nvidia_temperatures()
        except GpuTemperatureError as error:
            return ModuleResponse(text=str(error))

        if len(rows) == 1:
            name, temperature = rows[0]
            return ModuleResponse(text=f"Температура {name}: {temperature} градусов.")

        summary = ", ".join(
            f"{name}: {temperature} градусов"
            for name, temperature in rows[:4]
        )
        return ModuleResponse(text=f"Температура видеокарт: {summary}.")

    def _find_action(self, text: str) -> str | None:
        normalized = self._normalize(text)
        matches: list[tuple[int, str]] = []
        for trigger in self.get_action_triggers("system.status.gpu_temperature"):
            needle = self._normalize(trigger)
            if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                matches.append((len(needle), "gpu_temperature"))
        for trigger in self.get_action_triggers("system.status.summary"):
            needle = self._normalize(trigger)
            if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                matches.append((len(needle), "summary"))
        return max(matches, key=lambda item: item[0])[1] if matches else None

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
