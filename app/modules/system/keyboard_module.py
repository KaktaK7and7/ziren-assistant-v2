from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import (
    WindowsInputError,
    press_key,
    send_hotkey,
)


MAX_VIRTUAL_DESKTOPS = 20


def _function_key_triggers(number: int) -> list[str]:
    return [
        f"нажми f{number}",
        f"нажми f {number}",
        f"нажми эф {number}",
        f"нажми клавишу f{number}",
        f"f{number}",
        f"эф {number}",
    ]


KEY_COMMANDS: dict[str, tuple[list[str], list[str]]] = {
    "enter": (
        ["enter"],
        [
            "нажми enter",
            "нажми энтер",
            "нажми интер",
            "нажми ентер",
            "нажми энтэр",
            "нажми клавишу enter",
            "нажми клавишу энтер",
            "нажми клавишу интер",
            "enter",
            "энтер",
            "интер",
            "ентер",
            "энтэр",
        ],
    ),
    "escape": (
        ["escape"],
        [
            "нажми escape",
            "нажми esc",
            "нажми эскейп",
            "нажми ескейп",
            "нажми эск",
            "нажми клавишу escape",
            "нажми клавишу эскейп",
            "эскейп",
            "ескейп",
            "эск",
        ],
    ),
    "tab": (
        ["tab"],
        [
            "нажми tab",
            "нажми таб",
            "нажми этап",
            "нажми тэб",
            "нажми клавишу tab",
            "нажми клавишу таб",
            "tab",
            "таб",
            "тэб",
        ],
    ),
    "backspace": (
        ["backspace"],
        [
            "нажми backspace",
            "нажми бэкспейс",
            "нажми бекспейс",
            "нажми бэк спейс",
            "нажми бек спейс",
            "нажми клавишу backspace",
            "бэкспейс",
            "бекспейс",
        ],
    ),
    "delete": (
        ["delete"],
        [
            "нажми delete",
            "нажми делит",
            "нажми дэлит",
            "нажми клавишу delete",
            "delete",
            "делит",
            "дэлит",
        ],
    ),
    "space": (
        ["space"],
        ["нажми пробел", "нажми space", "нажми спейс", "пробел", "спейс"],
    ),
    "home": (
        ["home"],
        ["нажми home", "нажми хоум", "клавиша home", "клавиша хоум", "хоум"],
    ),
    "end": (
        ["end"],
        ["нажми end", "нажми энд", "клавиша end", "клавиша энд", "энд"],
    ),
    "pageup": (
        ["pageup"],
        [
            "нажми page up",
            "нажми pageup",
            "нажми пейдж ап",
            "страница вверх",
            "page up",
            "пейдж ап",
        ],
    ),
    "pagedown": (
        ["pagedown"],
        [
            "нажми page down",
            "нажми pagedown",
            "нажми пейдж даун",
            "страница вниз",
            "page down",
            "пейдж даун",
        ],
    ),
    "up": (
        ["up"],
        ["стрелка вверх", "нажми стрелку вверх", "нажми вверх"],
    ),
    "down": (
        ["down"],
        ["стрелка вниз", "нажми стрелку вниз", "нажми вниз"],
    ),
    "left": (
        ["left"],
        ["стрелка влево", "нажми стрелку влево", "нажми влево"],
    ),
    "right": (
        ["right"],
        ["стрелка вправо", "нажми стрелку вправо", "нажми вправо"],
    ),
    "select_all": (
        ["ctrl", "a"],
        ["выдели все", "выдели всё", "контрол а", "контроль а", "ctrl a"],
    ),
    "copy": (
        ["ctrl", "c"],
        ["скопируй выделенное", "контрол с", "контроль с", "ctrl c"],
    ),
    "paste": (
        ["ctrl", "v"],
        ["вставь", "вставь сюда", "контрол в", "контроль в", "ctrl v"],
    ),
    "cut": (
        ["ctrl", "x"],
        ["вырежи", "контрол икс", "контроль икс", "ctrl x"],
    ),
    "undo": (
        ["ctrl", "z"],
        ["отмени последнее", "отмени действие", "контрол зет", "контроль зет", "ctrl z"],
    ),
    "redo": (
        ["ctrl", "y"],
        ["повтори действие", "верни отмененное", "верни отменённое", "ctrl y"],
    ),
    "save": (
        ["ctrl", "s"],
        ["сохрани документ", "сохрани файл", "контрол эс", "ctrl s"],
    ),
    "find": (
        ["ctrl", "f"],
        ["открой поиск", "найди на странице", "контрол эф", "ctrl f"],
    ),
    "switch_window": (
        ["alt", "tab"],
        ["следующее окно", "переключи окно", "alt tab", "альт таб"],
    ),
    "previous_window": (
        ["alt", "shift", "tab"],
        ["предыдущее окно", "переключись на предыдущее окно"],
    ),
    "task_manager": (
        ["ctrl", "shift", "escape"],
        ["открой диспетчер задач", "диспетчер задач"],
    ),
    "start_menu": (["win"], ["открой пуск", "меню пуск"]),
    "windows_search": (
        ["win", "s"],
        ["поиск windows", "открой поиск windows", "открой поиск виндовс"],
    ),
    "task_view": (
        ["win", "tab"],
        ["покажи все окна", "представление задач", "task view"],
    ),
    "snap_left": (
        ["win", "left"],
        ["закрепи окно слева", "поставь окно слева", "окно влево"],
    ),
    "snap_right": (
        ["win", "right"],
        ["закрепи окно справа", "поставь окно справа", "окно вправо"],
    ),
    "desktop_left": (
        ["ctrl", "win", "left"],
        [
            "предыдущий рабочий стол",
            "рабочий стол влево",
            "переключи на предыдущий рабочий стол",
            "верни на предыдущий рабочий стол",
            "верни на старый рабочий стол",
            "вернись на старый рабочий стол",
        ],
    ),
    "desktop_right": (
        ["ctrl", "win", "right"],
        [
            "следующий рабочий стол",
            "рабочий стол вправо",
            "переключи на следующий рабочий стол",
        ],
    ),
    "new_desktop": (
        ["ctrl", "win", "d"],
        [
            "создай новый рабочий стол",
            "создай новый виртуальный рабочий стол",
            "новый рабочий стол",
            "новый виртуальный рабочий стол",
        ],
    ),
    "close_desktop": (
        ["ctrl", "win", "f4"],
        [
            "закрой виртуальный рабочий стол",
            "закрой текущий рабочий стол",
            "закрой этот рабочий стол",
            "закрой рабочий стол",
        ],
    ),
    "fullscreen": (
        ["f11"],
        ["полноэкранный режим", "на весь экран", "включи полный экран"],
    ),
}

for function_number in range(1, 13):
    KEY_COMMANDS.setdefault(
        f"f{function_number}",
        ([f"f{function_number}"], _function_key_triggers(function_number)),
    )


DESKTOP_ORDINALS = {
    1: ("первый", "первого", "первом", "первому"),
    2: ("второй", "второго", "втором", "второму"),
    3: ("третий", "третьего", "третьем", "третьему"),
    4: ("четвертый", "четвертого", "четвертом", "четвертому"),
    5: ("пятый", "пятого", "пятом", "пятому"),
    6: ("шестой", "шестого", "шестом", "шестому"),
    7: ("седьмой", "седьмого", "седьмом", "седьмому"),
    8: ("восьмой", "восьмого", "восьмом", "восьмому"),
    9: ("девятый", "девятого", "девятом", "девятому"),
    10: ("десятый", "десятого", "десятом", "десятому"),
    11: ("одиннадцатый", "одиннадцатого", "одиннадцатом", "одиннадцатому"),
    12: ("двенадцатый", "двенадцатого", "двенадцатом", "двенадцатому"),
    13: ("тринадцатый", "тринадцатого", "тринадцатом", "тринадцатому"),
    14: ("четырнадцатый", "четырнадцатого", "четырнадцатом", "четырнадцатому"),
    15: ("пятнадцатый", "пятнадцатого", "пятнадцатом", "пятнадцатому"),
    16: ("шестнадцатый", "шестнадцатого", "шестнадцатом", "шестнадцатому"),
    17: ("семнадцатый", "семнадцатого", "семнадцатом", "семнадцатому"),
    18: ("восемнадцатый", "восемнадцатого", "восемнадцатом", "восемнадцатому"),
    19: ("девятнадцатый", "девятнадцатого", "девятнадцатом", "девятнадцатому"),
    20: ("двадцатый", "двадцатого", "двадцатом", "двадцатому"),
}


DISPLAY_NAMES = {
    "enter": "Enter",
    "escape": "Escape",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Delete",
    "space": "Пробел",
    "home": "Home",
    "end": "End",
    "pageup": "Page Up",
    "pagedown": "Page Down",
    "up": "Стрелка вверх",
    "down": "Стрелка вниз",
    "left": "Стрелка влево",
    "right": "Стрелка вправо",
    "close_desktop": "Закрыть текущий виртуальный рабочий стол",
}


DEFAULT_TRIGGER_GROUPS = {
    f"keyboard.{action_id}": {
        "display_name": DISPLAY_NAMES.get(action_id, action_id.replace("_", " ").title()),
        "triggers": triggers,
        "argument_hint": "Без аргументов. Нажимается только заранее разрешённая клавиша или сочетание.",
    }
    for action_id, (_keys, triggers) in KEY_COMMANDS.items()
}
DEFAULT_TRIGGER_GROUPS["keyboard.desktop_number"] = {
    "display_name": "Переключиться на рабочий стол по номеру",
    "triggers": [
        "переключи на первый рабочий стол",
        "переключи на второй рабочий стол",
        "переключи на третий рабочий стол",
        "рабочий стол 1",
        "рабочий стол 2",
        "рабочий стол 3",
    ],
    "argument_hint": "arguments.target — номер виртуального рабочего стола от 1 до 20.",
}


class SystemKeyboardModule(AssistantModule):
    feature_id = "system.keyboard"
    display_name = "Клавиатура и горячие клавиши"
    plan = Plan.FREE
    default_trigger_groups = DEFAULT_TRIGGER_GROUPS

    def can_handle(self, text: str) -> bool:
        return self._find_desktop_number(text) is not None or self._find_action(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        desktop_number = self._find_desktop_number(text)
        if desktop_number is not None:
            return self._switch_to_desktop(desktop_number)

        action = self._find_action(text)
        if action is None:
            return ModuleResponse(text="Не поняла команду клавиатуры.")

        action_id, keys = action
        return self._execute_keys(action_id, keys)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id == "keyboard.desktop_number":
            target = self._parse_desktop_target((arguments or {}).get("target"))
            if target is None:
                return ModuleResponse(text="Не поняла номер рабочего стола. Назови номер от первого до двадцатого.")
            return self._switch_to_desktop(target)

        if not action_id.startswith("keyboard."):
            return None
        local_id = action_id.removeprefix("keyboard.")
        action = KEY_COMMANDS.get(local_id)
        if action is None:
            return None
        return self._execute_keys(local_id, list(action[0]))

    def _execute_keys(self, action_id: str, keys: list[str]) -> ModuleResponse:
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
            "close_desktop": "Закрываю текущий виртуальный рабочий стол.",
            "fullscreen": "Переключаю полноэкранный режим.",
        }
        if action_id.startswith("f") and action_id[1:].isdigit():
            return ModuleResponse(text=f"Нажала {action_id.upper()}.")
        return ModuleResponse(text=responses.get(action_id, "Готово."))

    def _switch_to_desktop(self, target: int) -> ModuleResponse:
        if target < 1 or target > MAX_VIRTUAL_DESKTOPS:
            return ModuleResponse(text=f"Поддерживаются рабочие столы с первого по {MAX_VIRTUAL_DESKTOPS}-й.")

        try:
            # Windows не даёт простого стабильного публичного API для адресного
            # переключения виртуального рабочего стола. Надёжный безопасный путь:
            # дойти до крайнего левого стола и затем сделать target-1 шагов вправо.
            for _ in range(MAX_VIRTUAL_DESKTOPS):
                send_hotkey(["ctrl", "win", "left"])
            for _ in range(target - 1):
                send_hotkey(["ctrl", "win", "right"])
        except WindowsInputError as error:
            return ModuleResponse(text=f"Не смогла переключить рабочий стол: {error}")

        return ModuleResponse(text=f"Переключаюсь на рабочий стол {target}.")

    def _find_action(self, text: str) -> tuple[str, list[str]] | None:
        normalized = self._normalize(text)
        matches: list[tuple[int, str, list[str]]] = []

        for action_id, (keys, _default_triggers) in KEY_COMMANDS.items():
            group_id = f"keyboard.{action_id}"
            for trigger in self.get_action_triggers(group_id):
                normalized_trigger = self._normalize(trigger)
                if not normalized_trigger:
                    continue
                if re.search(rf"\b{re.escape(normalized_trigger)}\b", normalized):
                    matches.append((len(normalized_trigger), action_id, list(keys)))

        if not matches:
            return None

        _, action_id, keys = max(matches, key=lambda item: item[0])
        return action_id, keys

    def _find_desktop_number(self, text: str) -> int | None:
        normalized = self._normalize(text)
        if "рабоч" not in normalized or "стол" not in normalized:
            return None

        numeric = re.search(r"\b(20|1[0-9]|[1-9])\b", normalized)
        if numeric:
            return int(numeric.group(1))

        for number, variants in DESKTOP_ORDINALS.items():
            if any(re.search(rf"\b{re.escape(variant)}\b", normalized) for variant in variants):
                return number
        return None

    def _parse_desktop_target(self, value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and float(value).is_integer():
            number = int(value)
            return number if 1 <= number <= MAX_VIRTUAL_DESKTOPS else None

        text = self._normalize(str(value or ""))
        if not text:
            return None
        return self._find_desktop_number(f"рабочий стол {text}")

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value or "").lower().replace("ё", "е").split())
