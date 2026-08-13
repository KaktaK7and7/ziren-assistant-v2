from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.system_status import read_system_status


TRIGGERS = [
    "состояние компьютера",
    "нагрузка компьютера",
    "как загружен компьютер",
    "сколько занято оперативки",
    "сколько оперативной памяти занято",
    "сколько места на диске",
    "сколько свободно на диске",
]


class SystemStatusModule(AssistantModule):
    feature_id = "system.status"
    display_name = "Состояние компьютера"
    plan = Plan.FREE
    default_trigger_groups = {
        "system.status.summary": {
            "display_name": "Показать нагрузку и память",
            "triggers": TRIGGERS,
        }
    }

    def can_handle(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(re.search(rf"\b{re.escape(trigger)}\b", normalized) for trigger in TRIGGERS)

    def handle(self, text: str) -> ModuleResponse:
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

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
