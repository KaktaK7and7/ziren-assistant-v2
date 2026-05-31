import re

from app.core.log_bus import add_log
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.window_control.resolver import WindowResolver, normalize_text


QUERY_STOP_WORDS = ["приложение", "окно", "игру", "игра"]

ACTION_BY_GROUP = {
    "window.close": "close",
    "window.minimize": "minimize",
    "window.maximize": "maximize",
    "window.restore": "restore",
    "window.desktop": "desktop",
}


class SystemWindowControlModule(AssistantModule):
    feature_id = "system.window_control"
    display_name = "Управление окнами"
    plan = Plan.FREE
    default_trigger_groups = {
        "window.close": {
            "display_name": "Закрыть приложение",
            "triggers": [
                "закрой",
                "закрой приложение",
                "выключи приложение",
                "закрой окно",
                "закрой игру",
                "выруби",
                "выруби приложение",
            ],
        },
        "window.minimize": {
            "display_name": "Свернуть приложение",
            "triggers": [
                "сверни",
                "сверни приложение",
                "сверни окно",
            ],
        },
        "window.maximize": {
            "display_name": "Развернуть приложение",
            "triggers": [
                "разверни",
                "разверни приложение",
                "разверни окно",
            ],
        },
        "window.restore": {
            "display_name": "Показать окно",
            "triggers": [
                "покажи окно",
                "верни окно",
                "восстанови окно",
                "переключись на",
            ],
        },
        "window.desktop": {
            "display_name": "Показать рабочий стол",
            "triggers": [
                "покажи рабочий стол",
                "сверни все окна",
                "рабочий стол",
            ],
        },
    }

    def __init__(self, resolver: WindowResolver | None = None) -> None:
        self.resolver = resolver or WindowResolver()

    def can_handle(self, text: str) -> bool:
        normalized_text = normalize_text(text)
        return self._find_action_match(normalized_text) is not None

    def handle(self, text: str) -> ModuleResponse:
        normalized_text = normalize_text(text)
        action_match = self._find_action_match(normalized_text)

        if action_match is None:
            return ModuleResponse(text="Не поняла команду управления окнами.")

        action_id, action, trigger = action_match
        query = "" if action == "desktop" else self._extract_query(normalized_text, trigger)

        add_log(
            "WindowControl команда получена",
            meta={"action": action, "query": query, "trigger": trigger},
        )

        result = self.resolver.perform(action, query)

        if result.candidates:
            add_log("Окна найдены", meta={"count": len(result.candidates)})

        if result.target is not None:
            add_log(
                "WindowControl target найден",
                meta={
                    "title": result.target.title,
                    "process": result.target.process_name,
                    "pid": result.target.process_id,
                },
            )

        if result.status == "success":
            add_log(
                "WindowControl действие выполнено",
                meta={"action": action, "action_id": action_id},
            )
            return ModuleResponse(text=self._success_text(action, result.target))

        if result.status == "ambiguous":
            candidates = ", ".join(
                f"{index + 1}. {candidate.title}"
                for index, candidate in enumerate(result.candidates[:3])
            )
            return ModuleResponse(
                text=f"Я нашла несколько окон: {candidates}. Скажи точнее."
            )

        if result.status == "not_found":
            add_log("WindowControl окно не найдено", meta={"query": query}, level="warn")
            return ModuleResponse(text=f"Не нашла открытое окно {query}.")

        if "Нельзя закрыть системный процесс" in result.message:
            return ModuleResponse(text="Нельзя закрыть системный процесс.")

        if "Нет прав для закрытия процесса" in result.message:
            return ModuleResponse(text="Не хватает прав для закрытия процесса.")

        return ModuleResponse(text=f"Не смогла выполнить действие: {result.message}")

    def _find_action_match(self, text: str) -> tuple[str, str, str] | None:
        matches: list[tuple[int, str, str, str]] = []

        for action_id, action in ACTION_BY_GROUP.items():
            for trigger in self.get_action_triggers(action_id):
                normalized_trigger = normalize_text(trigger)

                if not normalized_trigger:
                    continue

                if re.search(rf"\b{re.escape(normalized_trigger)}\b", text):
                    matches.append((len(normalized_trigger), action_id, action, normalized_trigger))

        if not matches:
            return None

        _, action_id, action, trigger = max(matches, key=lambda item: item[0])
        return action_id, action, trigger

    def _extract_query(self, text: str, trigger: str) -> str:
        query = re.sub(rf"\b{re.escape(trigger)}\b", " ", text, count=1)

        for stop_word in QUERY_STOP_WORDS:
            query = re.sub(rf"\b{re.escape(stop_word)}\b", " ", query)

        return re.sub(r"\s+", " ", query).strip()

    def _success_text(self, action: str, target) -> str:
        if action == "desktop":
            return "Показываю рабочий стол."

        title = target.title if target is not None else "окно"

        if action == "close":
            return f"Закрываю {title}."

        if action == "minimize":
            return f"Сворачиваю {title}."

        if action == "maximize":
            return f"Разворачиваю {title}."

        return f"Показываю {title}."
