from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.system_info import get_system_status, top_memory_processes


class SystemInfoModule(AssistantModule):
    feature_id = "system.info"
    display_name = "Состояние компьютера"
    plan = Plan.FREE
    default_trigger_groups = {
        "system.info.summary": {
            "display_name": "Состояние компьютера",
            "triggers": [
                "состояние компьютера",
                "как загружен компьютер",
                "нагрузка компьютера",
                "сколько занято оперативки",
                "сколько оперативной памяти занято",
                "сколько места на диске",
            ],
        },
        "system.info.top_memory": {
            "display_name": "Самые тяжёлые процессы",
            "triggers": [
                "что жрет память",
                "что жрёт память",
                "что занимает оперативку",
                "самые тяжелые процессы",
                "самые тяжёлые процессы",
            ],
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action = self._find_action(text)
        if action == "top_memory":
            rows = top_memory_processes(5)
            if not rows:
                return ModuleResponse(text="Не смогла получить список процессов.")
            formatted = ", ".join(f"{name}: {memory_gb:.2f} ГБ" for name, _pid, memory_gb in rows)
            return ModuleResponse(text=f"Больше всего памяти сейчас используют: {formatted}.")

        status = get_system_status()
        free_disk = round(status.disk_total_gb - status.disk_used_gb, 1)
        return ModuleResponse(
            text=(
                f"Процессор загружен на {status.cpu_percent:.0f} процентов. "
                f"Оперативная память: {status.memory_used_gb:.1f} из {status.memory_total_gb:.1f} гигабайт, "
                f"это {status.memory_percent:.0f} процентов. "
                f"На диске C свободно примерно {free_disk:.1f} гигабайт."
            )
        )

    def _find_action(self, text: str) -> str | None:
        normalized = " ".join(str(text or "").lower().replace("ё", "е").split())
        matches: list[tuple[int, str]] = []
        for action_id, group in self.get_trigger_groups().items():
            action = "top_memory" if action_id.endswith("top_memory") else "summary"
            for trigger in group.get("triggers", []):
                needle = str(trigger).lower().replace("ё", "е")
                if re.search(rf"\b{re.escape(needle)}\b", normalized):
                    matches.append((len(needle), action))
        if not matches:
            return None
        return max(matches, key=lambda item: item[0])[1]
