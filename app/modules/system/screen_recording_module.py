from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.screen_recording import (
    ScreenRecordingError,
    open_recording_directory,
)
from app.pc_control.windows_input import WindowsInputError, send_hotkey


RECORDING_TOGGLE_TRIGGERS = [
    "начни запись экрана",
    "запусти запись экрана",
    "останови запись экрана",
    "закончи запись экрана",
    "переключи запись экрана",
]

RECORDING_FOLDER_TRIGGERS = [
    "открой папку записей экрана",
    "открой папку с записями экрана",
    "открой куда сохраняются записи экрана",
    "покажи папку записей экрана",
    "покажи где сохраняются записи экрана",
    "где лежат записи экрана",
    "открой папку captures",
]


class SystemScreenRecordingModule(AssistantModule):
    feature_id = "system.screen_recording"
    display_name = "Запись экрана"
    plan = Plan.FREE
    default_trigger_groups = {
        "screen_recording.toggle": {
            "display_name": "Начать или остановить запись экрана",
            "triggers": RECORDING_TOGGLE_TRIGGERS,
            "argument_hint": "Без аргументов. Использует системное сочетание Windows Game Bar Win+Alt+R.",
        },
        "screen_recording.open_folder": {
            "display_name": "Открыть папку записей экрана",
            "triggers": RECORDING_FOLDER_TRIGGERS,
            "argument_hint": "Без аргументов. Открывает фиксированную локальную папку Videos/Captures.",
        },
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action_id = self._find_action(text)
        if action_id == "screen_recording.open_folder":
            return self._open_folder()
        return self._toggle(text)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id == "screen_recording.toggle":
            return self._toggle("")
        if action_id == "screen_recording.open_folder":
            return self._open_folder()
        return None

    def _toggle(self, text: str) -> ModuleResponse:
        try:
            send_hotkey(["win", "alt", "r"])
        except WindowsInputError as error:
            return ModuleResponse(text=f"Не смогла передать команду записи экрана: {error}")

        normalized = self._normalize(text)
        if "останов" in normalized or "закончи" in normalized:
            return ModuleResponse(text="Передала Windows команду остановить запись экрана.")
        if "начни" in normalized or "запусти" in normalized:
            return ModuleResponse(text="Передала Windows команду начать запись экрана.")
        return ModuleResponse(text="Переключила запись экрана через Windows Game Bar.")

    def _open_folder(self) -> ModuleResponse:
        try:
            open_recording_directory()
        except (ScreenRecordingError, OSError, RuntimeError) as error:
            return ModuleResponse(
                text=f"Не получилось открыть папку записей экрана: {error}"
            )
        return ModuleResponse(text="Открываю папку записей экрана.")

    def _find_action(self, text: str) -> str | None:
        normalized = self._normalize(text)
        matches: list[tuple[int, str]] = []

        for action_id in (
            "screen_recording.open_folder",
            "screen_recording.toggle",
        ):
            for trigger in self.get_action_triggers(action_id):
                needle = self._normalize(trigger)
                if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                    matches.append((len(needle), action_id))

        return max(matches, key=lambda item: item[0])[1] if matches else None

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
