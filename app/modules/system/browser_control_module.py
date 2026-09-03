from __future__ import annotations

import ctypes
import platform
import re
from typing import Any

import psutil

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import WindowsInputError, send_hotkey


BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "opera.exe",
    "opera_gx.exe",
    "brave.exe",
    "vivaldi.exe",
    "browser.exe",
}

BROWSER_ACTIONS = {
    "new_tab": {
        "keys": ["ctrl", "t"],
        "triggers": ["новая вкладка", "открой новую вкладку", "создай новую вкладку"],
        "response": "Передала браузеру команду открыть новую вкладку.",
    },
    "close_tab": {
        "keys": ["ctrl", "w"],
        "triggers": ["закрой вкладку", "закрой текущую вкладку"],
        "response": "Передала браузеру команду закрыть текущую вкладку.",
    },
    "restore_tab": {
        "keys": ["ctrl", "shift", "t"],
        "triggers": ["верни вкладку", "восстанови вкладку", "верни закрытую вкладку"],
        "response": "Передала браузеру команду восстановить закрытую вкладку.",
    },
    "back": {
        "keys": ["alt", "left"],
        "triggers": ["назад в браузере", "вернись назад", "предыдущая страница"],
        "response": "Передала браузеру команду перейти назад.",
    },
    "forward": {
        "keys": ["alt", "right"],
        "triggers": ["вперед в браузере", "вперёд в браузере", "следующая страница"],
        "response": "Передала браузеру команду перейти вперёд.",
    },
    "reload": {
        "keys": ["ctrl", "r"],
        "triggers": ["обнови страницу", "перезагрузи страницу"],
        "response": "Передала браузеру команду обновить страницу.",
    },
    "address": {
        "keys": ["ctrl", "l"],
        "triggers": ["адресная строка", "перейди в адресную строку", "выдели адрес сайта"],
        "response": "Передала браузеру команду перейти в адресную строку.",
    },
    "next_tab": {
        "keys": ["ctrl", "tab"],
        "triggers": ["следующая вкладка", "переключи на следующую вкладку"],
        "response": "Передала браузеру команду переключиться на следующую вкладку.",
    },
    "previous_tab": {
        "keys": ["ctrl", "shift", "tab"],
        "triggers": ["предыдущая вкладка", "переключи на предыдущую вкладку"],
        "response": "Передала браузеру команду переключиться на предыдущую вкладку.",
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
            "argument_hint": (
                "Без аргументов. Core сначала проверяет, что активное окно принадлежит "
                "разрешённому браузеру, затем отправляет whitelisted hotkey. Состояние "
                "вкладки после hotkey пока не проверяется, поэтому Ziren подтверждает "
                "только доставку команды браузеру."
            ),
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
            process_name = _foreground_process_name()
        except RuntimeError as error:
            return ModuleResponse(text=f"Не смогла проверить активный браузер: {error}")

        if process_name not in BROWSER_PROCESSES:
            readable = process_name or "неизвестное приложение"
            return ModuleResponse(
                text=(
                    f"Активное окно сейчас не браузер ({readable}). "
                    "Сначала переключись на браузер."
                )
            )

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


def _foreground_process_name() -> str:
    if platform.system().lower() != "windows":
        raise RuntimeError("проверка активного браузера доступна только на Windows")

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            raise RuntimeError("Windows не вернула активное окно")

        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value <= 0:
            raise RuntimeError("Windows не вернула процесс активного окна")

        return psutil.Process(pid.value).name().strip().lower()
    except (psutil.Error, OSError) as error:
        raise RuntimeError(f"не удалось определить процесс активного окна: {error}") from error
