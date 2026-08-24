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


_NUMBER_WORDS = {
    "ноль": 0,
    "один": 1,
    "одна": 1,
    "одно": 1,
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
        "scheduler.alarm.relative": {
            "display_name": "Поставить будильник через интервал",
            "triggers": ["поставь будильник через", "будильник через"],
            "argument_hint": "arguments.minutes или arguments.hours — число; arguments.label — необязательная подпись.",
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
            if action_id in {
                "scheduler.reminder.relative",
                "scheduler.alarm.relative",
            }:
                minutes = self._number(args.get("minutes"))
                hours = self._number(args.get("hours"))
                is_alarm = action_id == "scheduler.alarm.relative"
                label = str(args.get("label") or "").strip()
                if minutes <= 0 and hours <= 0:
                    return ModuleResponse(text="Уточни, через сколько поставить задачу.")
                if not label:
                    if is_alarm:
                        label = "Будильник"
                    else:
                        return ModuleResponse(text="Уточни, о чём напомнить.")
                job = self.store.add(
                    "alarm" if is_alarm else "reminder",
                    label,
                    due_after(minutes=minutes, hours=hours),
                )
                if is_alarm:
                    return ModuleResponse(
                        text=f"Будильник установлен на {human_due_time(job.due_at)}."
                    )
                return ModuleResponse(
                    text=f"Хорошо. Напомню в {human_due_time(job.due_at)}: {job.label}."
                )

            if action_id == "scheduler.alarm.clock":
                raw_time = str(args.get("time") or "").strip()
                match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", raw_time)
                if not match:
                    return ModuleResponse(
                        text="Скажи время будильника, например семь тридцать или 07:30."
                    )
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
        if not source:
            return None
        source_words = source.split()
        normalized_words = [
            word.lower().replace("ё", "е").strip(" ,.!?:;")
            for word in source_words
        ]
        normalized = " ".join(word for word in normalized_words if word)

        for action_id in (
            "scheduler.reminder.relative",
            "scheduler.alarm.relative",
        ):
            prefix_length = self._trigger_prefix_length(normalized_words, action_id)
            if prefix_length is None:
                continue
            parsed = self._parse_relative_tail(
                normalized_words,
                source_words,
                prefix_length,
            )
            # Once a configured trigger matched, keep the command in the local
            # Snake route even when the user omitted arguments; execute_action
            # will ask for the missing interval instead of falling through.
            return action_id, parsed or {}

        clock_prefix_length = self._trigger_prefix_length(
            normalized_words,
            "scheduler.alarm.clock",
        )
        if clock_prefix_length is not None:
            clock_start = clock_prefix_length
            if (
                clock_start < len(normalized_words)
                and normalized_words[clock_start] == "на"
            ):
                clock_start += 1
            parsed_clock = self._parse_clock_words(normalized_words[clock_start:])
            if parsed_clock is None:
                return "scheduler.alarm.clock", {}
            hour, minute, consumed = parsed_clock
            label = " ".join(source_words[clock_start + consumed :]).strip()
            return (
                "scheduler.alarm.clock",
                {
                    "time": f"{hour:02d}:{minute:02d}",
                    "label": label or "Будильник",
                },
            )

        for action_id in ("scheduler.list", "scheduler.clear"):
            if self._matches_exact_trigger(normalized, action_id):
                return action_id, {}

        return None

    def _trigger_prefix_length(
        self,
        normalized_words: list[str],
        action_id: str,
    ) -> int | None:
        candidates: list[tuple[int, tuple[str, ...]]] = []
        for trigger in self.get_action_triggers(action_id):
            words = tuple(
                word.lower().replace("ё", "е").strip(" ,.!?:;")
                for word in str(trigger or "").split()
                if word.strip(" ,.!?:;")
            )
            if words:
                candidates.append((len(words), words))

        for length, words in sorted(candidates, key=lambda item: item[0], reverse=True):
            if tuple(normalized_words[:length]) == words:
                return length
        return None

    def _matches_exact_trigger(self, normalized: str, action_id: str) -> bool:
        return any(
            normalized
            == " ".join(
                str(trigger or "").lower().replace("ё", "е").split()
            ).strip(" ,.!?:;")
            for trigger in self.get_action_triggers(action_id)
            if str(trigger or "").strip()
        )

    def _parse_relative_tail(
        self,
        normalized_words: list[str],
        source_words: list[str],
        start: int,
    ) -> dict[str, Any] | None:
        if start < len(normalized_words) and normalized_words[start] == "через":
            start += 1

        unit_index = -1
        for index in range(start, min(len(normalized_words), start + 5)):
            word = normalized_words[index].strip(".,!?:;")
            if word.startswith("минут") or word.startswith("час"):
                unit_index = index
                break

        if unit_index < 0 or unit_index == start:
            return None

        amount = self._parse_number_phrase(normalized_words[start:unit_index])
        if amount is None or amount <= 0:
            return None

        unit = normalized_words[unit_index]
        label = " ".join(source_words[unit_index + 1 :]).strip(" ,.!?:;-")
        return {
            "hours": amount if unit.startswith("час") else 0,
            "minutes": amount if unit.startswith("минут") else 0,
            "label": label,
        }

    @classmethod
    def _parse_clock_words(
        cls,
        words: list[str],
    ) -> tuple[int, int, int] | None:
        if not words:
            return None

        first = words[0].strip(" ,.!?:;")
        direct = re.fullmatch(r"(\d{1,2})[:.](\d{1,2})", first)
        if direct:
            hour = int(direct.group(1))
            minute = int(direct.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, 1
            return None

        for hour_len in (2, 1):
            if hour_len > len(words):
                continue
            hour_value = cls._parse_number_phrase(words[:hour_len])
            if hour_value is None or int(hour_value) != hour_value:
                continue
            hour = int(hour_value)
            if not 0 <= hour <= 23:
                continue

            remaining = words[hour_len:]
            for minute_len in (2, 1):
                if minute_len > len(remaining):
                    continue
                minute_value = cls._parse_number_phrase(remaining[:minute_len])
                if minute_value is None or int(minute_value) != minute_value:
                    continue
                minute = int(minute_value)
                if 0 <= minute <= 59:
                    return hour, minute, hour_len + minute_len

            # "будильник на семь" means 07:00.
            return hour, 0, hour_len

        return None

    @staticmethod
    def _parse_number_phrase(words: list[str]) -> float | None:
        cleaned = [word.strip(" ,.!?:;").lower().replace("ё", "е") for word in words]
        cleaned = [word for word in cleaned if word]
        if not cleaned:
            return None

        if len(cleaned) == 1:
            try:
                return float(cleaned[0].replace(",", "."))
            except ValueError:
                pass

        total = 0
        for word in cleaned:
            value = _NUMBER_WORDS.get(word)
            if value is None:
                return None
            total += value
        return float(total)

    @staticmethod
    def _number(value: object) -> float:
        if isinstance(value, bool) or value is None:
            return 0.0
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0
