from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import (
    WindowsInputError,
    press_key,
    send_hotkey,
)


KEY_COMMANDS = {
    "enter": (["enter"], ["нажми enter", "нажми энтер", "энтер"]),
    "escape": (["escape"], ["нажми escape", "нажми esc", "нажми эскейп"]),
    "tab": (["tab"], ["нажми tab", "нажми таб"]),
    "backspace": (["backspace"], ["нажми backspace", "нажми бэкспейс", "нажми бекспейс"]),
    "delete": (["delete"], ["нажми delete", "нажми делит"]),
    "space": (["space"], ["нажми пробел"]),
    "up": (["up"], ["стрелка вверх", "нажми стрелку вверх"]),
    "down": (["down"], ["стрелка вниз", "нажми стрелку вниз"]),
    "left": (["left"], ["стрелка влево", "нажми стрелку влево"]),
    "right": (["right"], ["стрелка вправо", "нажми стрелку вправо"]),
    "select_all": (["ctrl", "a"], ["выдели все", "выдели всё", "контрол а", "ctrl a"]),
    "copy": (["ctrl", "c"], ["скопируй выделенное", "контрол с", "ctrl c"]),
    "paste": (["ctrl", "v"], ["вставь", "вставь сюда", "контрол в", "ctrl v"]),
    "cut": (["ctrl", "x"], ["вырежи", "контрол икс", "ctrl x"]),
    "undo": (["ctrl", "z"], ["отмени последнее", "отмени действие", "контрол зет", "ctrl z"]),
    "redo": (["ctrl", "y"], ["повтори действие", "верни отмененное", "верни отменённое", "ctrl y"]),
    "save": (["ctrl", "s"], ["сохрани документ", "сохрани файл", "ctrl s"]),
    "find": (["ctrl", "f"], ["открой поиск", "найди на странице", "ctrl f"]),
    "switch_window": (["alt", "tab"], ["следующее окно", "переключи окно", "alt tab", "альт таб"]),
    "previous_window": (["alt", "shift", "tab"], ["предыдущее окно", "переключись на предыдущее окно"]),
    "task_manager": (["ctrl", "shift", "escape"], ["открой диспетчер задач", "диспетчер задач"]),
    "start_menu": (["win"], ["открой пуск", "меню пуск"]),
    "windows_search": (["win", "s"], ["поиск windows", "открой поиск windows"]),
    "task_view": (["win", "tab"], ["покажи все окна", "представление задач", "task view"]),
    "snap_left": (["win", "left"], ["закрепи окно слева", "поставь окно слева", "окно влево"]),
    "snap_right": (["win", "right"], ["закрепи окно справа", "поставь окно справа", "окно вправо"]),
    "desktop_left": (["ctrl", "win", "left"], ["предыдущий рабочий стол", "рабочий стол влево"]),
    "desktop_right": (["ctrl", "win", "right"], ["следующий рабочий стол", "рабочий стол вправо"]),
    "new_desktop": (["ctrl", "win", "d"], ["создай новый рабочий стол", "новый рабочий стол"]),
    "fullscreen": (["f11"], ["полноэкранный режим", "на весь экран", "включи полный экран"]),
}


class SystemKeyboardModule(AssistantModule):
    feature_id = "system.keyboard"
    display_name = "Клавиатура и горячие клавиши"
    plan = Plan.FREE
    default_trigger_groups = {
        f"keyboard.{action_id}": {
            "display_name": action_id.replace("_", " ").title(),
            "triggers": triggers,
        }
        for action_id, (_keys, triggers) in KEY_COMMANDS.items()
    }

    def can_handle(self, text: str) -> bool:
        return self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        action = self._find_action(text)

        if action is None:
            return ModuleResponse(text="Не поняла команду клавиатуры.")

        action_id, keys = action

        try:
            if len(keys) == 1:
                press_key(keys[0])
            else:
                send_hotkey(keys)
        except WindowsInputError as error:
            return ModuleResponse(text=f"Не смогла нажать клавиши: {error}")

        responses = {
            "select_all": "Выделила всё.",
            "copy": "Скопировала выделенное.",
            "paste": "Вставила.",
            "cut": "Вырезала выделенное.",
            "undo": "Отменила последнее действие.",
            "redo": "Вернула отменённое действие.",
            "save": "Сохранила.",
            "find": "Открыла поиск.",
            "switch_window": "Переключаю окно.",
            "previous_window": "Переключаюсь на предыдущее окно.",
            "task_manager": "Открываю диспетчер задач.",
            "start_menu": "Открываю Пуск.",
            "windows_search": "Открываю поиск Windows.",
            "task_view": "Показываю открытые окна.",
            "snap_left": "Закрепляю активное окно слева.",
            "snap_right": "Закрепляю активное окно справа.",
            "desktop_left": "Переключаюсь на предыдущий рабочий стол.",
            "desktop_right": "Переключаюсь на следующий рабочий стол.",
            "new_desktop": "Создаю новый рабочий стол.",
            "fullscreen": "Переключаю полноэкранный режим.",
        }
        return ModuleResponse(text=responses.get(action_id, "Готово."))

    def _find_action(self, text: str) -> tuple[str, list[str]] | None:
        normalized = " ".join(str(text or "").lower().replace("ё", "е").split())
        matches: list[tuple[int, str, list[str]]] = []

        for action_id, (keys, triggers) in KEY_COMMANDS.items():
            for trigger in triggers:
                normalized_trigger = " ".join(trigger.lower().replace("ё", "е").split())
                if re.search(rf"\b{re.escape(normalized_trigger)}\b", normalized):
                    matches.append((len(normalized_trigger), action_id, list(keys)))

        if not matches:
            return None

        _, action_id, keys = max(matches, key=lambda item: item[0])
        return action_id, keys
