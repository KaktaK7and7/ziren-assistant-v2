from __future__ import annotations

import os
import re
from typing import Any

from app.config.settings import DESKTOP_TOKEN_ENV
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.scheduler.reminders import (
    ReminderStore,
    ReminderWorker,
    due_after,
    human_due_time,
    next_clock_time,
)


class SystemSchedulerModule(AssistantModule):
    feature_id = "system.scheduler"
    display_name = "Напоминания и будильники"
    plan = Plan.FREE
    default_trigger_groups = {
        "scheduler.reminder.relative": {
            "display_name": "Создать напоминание через интервал",
            "triggers": ["напомни через", "создай напоминание через"],
            "argument_hint": "arguments.minutes или arguments.hours — число; arguments.label — что напомнить.",
        },
        "scheduler.alarm.clock": {
            "display_name": "Поставить будильник на время",
            "triggers": ["поставь будильник на", "будильник на"],
            "argument_hint": "arguments.time — локальное время HH:MM; arguments.label — необязательная подпись.",
        },
        "scheduler.list": {
            "display_name": "Показать активные напоминания",
            "triggers": ["какие у меня напоминания", "покажи напоминания", "покажи будильники"],
            "argument_hint": "Без аргументов.",
        },
        "scheduler.clear": {
            "display_name": "Удалить все напоминания и будильники",
            "triggers": ["удали все напоминания", "отмени все напоминания", "отмени все будильники"],
            "argument_hint": "Без аргументов. Удаляет все локальные задачи расписания.",
        },
    }

    def __init__(self, store: ReminderStore | None = None, *, start_worker: bool = True) -> None:
        self.store = store or ReminderStore()
        self.worker = ReminderWorker(self.store)
        if start_worker and os.environ.get(DESKTOP_TOKEN_ENV):
            self.worker.start()

    def can_handle(self, text: str) -> bool:
        return self._parse_local(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        parsed = self._parse_local(text)
        if parsed is None:
            return ModuleResponse(text="Не поняла напоминание или будильник.")
        action_id, arguments = parsed
        response = self.execute_action(action_id, arguments)
        return response or ModuleResponse(text="Не смогла создать напоминание.")

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        args = arguments or {}
        try:
            if action_id == "scheduler.reminder.relative":
                minutes = self._number(args.get("minutes"))
                hours = self._number(args.get("hours"))
                label = str(args.get("label") or "").strip()
                if minutes <= 0 and hours <= 0:
                    return ModuleResponse(text="Уточни, через сколько напомнить.")
                if not label:
                    return ModuleResponse(text="Уточни, о чём напомнить.")
                job = self.store.add(
                    "reminder",
                    label,
                    due_after(minutes=minutes, hours=hours),
                )
                return ModuleResponse(
                    text=f"Хорошо. Напомню в {human_due_time(job.due_at)}: {job.label}."
                )

            if action_id == "scheduler.alarm.clock":
                raw_time = str(args.get("time") or "").strip()
                match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", raw_time)
                if not match:
                    return ModuleResponse(text="Скажи время будильника, например семь тридцать или 07:30.")
                due_at = next_clock_time(int(match.group(1)), int(match.group(2)))
                label = str(args.get("label") or "Будильник").strip() or "Будильник"
                job = self.store.add("alarm", label, due_at)
                return ModuleResponse(text=f"Будильник установлен на {human_due_time(job.due_at)}.")

            if action_id == "scheduler.list":
                jobs = self.store.list_jobs()
                if not jobs:
                    return ModuleResponse(text="Активных напоминаний и будильников нет.")
                summary = ", ".join(
                    f"{human_due_time(job.due_at)} — {job.label}"
                    for job in jobs[:6]
                )
                return ModuleResponse(text=f"Активные задачи: {summary}.")

            if action_id == "scheduler.clear":
                count = self.store.clear()
                return ModuleResponse(text=f"Удалила задач расписания: {count}.")
        except ValueError as error:
            return ModuleResponse(text=str(error))

        return None

    def _parse_local(self, text: str) -> tuple[str, dict[str, Any]] | None:
        source = " ".join(str(text or "").split()).strip()
        normalized = source.lower().replace("ё", "е")

        relative = re.match(
            r"^(?:напомни|создай напоминание)\s+через\s+(\d+(?:[.,]\d+)?)\s*"
            r"(минут\w*|час\w*)\s+(.+)$",
            normalized,
        )
        if relative:
            value = float(relative.group(1).replace(",", "."))
            unit = relative.group(2)
            label_words = source.split()[4:]
            label = " ".join(label_words).strip()
            return (
                "scheduler.reminder.relative",
                {
                    "hours": value if unit.startswith("час") else 0,
                    "minutes": value if unit.startswith("минут") else 0,
                    "label": label,
                },
            )

        alarm = re.match(
            r"^(?:поставь\s+)?будильник\s+на\s+(\d{1,2})(?::|\s)(\d{2})(?:\s+(.+))?$",
            normalized,
        )
        if alarm:
            label = (alarm.group(3) or "Будильник").strip()
            return (
                "scheduler.alarm.clock",
                {"time": f"{int(alarm.group(1)):02d}:{int(alarm.group(2)):02d}", "label": label},
            )

        for action_id in ("scheduler.list", "scheduler.clear"):
            for trigger in self.get_action_triggers(action_id):
                if normalized == trigger.lower().replace("ё", "е"):
                    return action_id, {}

        return None

    @staticmethod
    def _number(value: object) -> float:
        if isinstance(value, bool) or value is None:
            return 0.0
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0
