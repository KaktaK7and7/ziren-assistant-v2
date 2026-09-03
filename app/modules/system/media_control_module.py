import re
from typing import Any

from app.core.log_bus import add_log
from app.features.plans import Plan
from app.media_control.resolver import MediaResolver
from app.media_control.store import normalize_alias
from app.modules.base import AssistantModule, ModuleResponse


ACTION_BY_GROUP = {
    "media.pause": "pause",
    "media.resume": "resume",
    "media.next": "next",
    "media.previous": "previous",
    "media.stop": "stop",
    "media.play_preset": "play_preset",
}


class SystemMediaControlModule(AssistantModule):
    feature_id = "system.media_control"
    display_name = "Управление музыкой"
    plan = Plan.FREE
    default_trigger_groups = {
        "media.pause": {
            "display_name": "Пауза",
            "triggers": [
                "пауза",
                "поставь на паузу",
            ],
            "argument_hint": (
                "Без аргументов. Передаёт глобальную Windows media play/pause команду. "
                "Core пока не подтверждает состояние медиасеанса после события."
            ),
        },
        "media.resume": {
            "display_name": "Продолжить",
            "triggers": [
                "продолжи",
                "продолжи музыку",
            ],
            "argument_hint": (
                "Без аргументов. Передаёт глобальную Windows media play/pause команду. "
                "Core пока не подтверждает состояние медиасеанса после события."
            ),
        },
        "media.next": {
            "display_name": "Следующий трек",
            "triggers": [
                "следующий трек",
                "следующая песня",
            ],
            "argument_hint": "Без аргументов. Передаёт глобальную Windows media-next команду.",
        },
        "media.previous": {
            "display_name": "Предыдущий трек",
            "triggers": [
                "предыдущий трек",
                "предыдущая песня",
            ],
            "argument_hint": "Без аргументов. Передаёт глобальную Windows media-previous команду.",
        },
        "media.stop": {
            "display_name": "Остановить музыку",
            "triggers": [
                "останови музыку",
            ],
            "argument_hint": "Без аргументов. Передаёт глобальную Windows media-stop команду.",
        },
        "media.play_preset": {
            "display_name": "Открыть музыкальный сценарий",
            "triggers": [
                "включи",
                "включи музыку",
                "поставь",
                "запусти музыку",
            ],
            "argument_hint": "arguments.target — название или пользовательский алиас сохранённого музыкального сценария.",
        },
    }

    def __init__(self, resolver: MediaResolver | None = None) -> None:
        self.resolver = resolver or MediaResolver()
        self.store = self.resolver.store

    def can_handle(self, text: str) -> bool:
        normalized_text = normalize_alias(text)
        action_match = self._find_action_match(normalized_text)

        if action_match is None:
            return False

        _, action, trigger = action_match

        if action != "play_preset":
            return True

        return self._find_preset_query(normalized_text, trigger) is not None

    def handle(self, text: str) -> ModuleResponse:
        normalized_text = normalize_alias(text)
        action_match = self._find_action_match(normalized_text)

        if action_match is None:
            return ModuleResponse(text="Не поняла команду управления музыкой.")

        action_id, action, trigger = action_match
        query = self._extract_query(normalized_text, trigger)
        if action == "play_preset":
            query = self._find_preset_query(normalized_text, trigger) or query
        return self._execute(action_id, query)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id not in ACTION_BY_GROUP:
            return None
        query = str((arguments or {}).get("target") or "").strip()
        return self._execute(action_id, query)

    def _execute(self, action_id: str, query: str = "") -> ModuleResponse:
        action = ACTION_BY_GROUP[action_id]

        add_log(
            "MediaControl команда получена",
            meta={"action": action, "query": query, "action_id": action_id},
        )

        if action == "play_preset":
            if not query:
                return ModuleResponse(text="Скажи, какой музыкальный сценарий включить.")
            result = self.resolver.play_preset(query)
        else:
            result = self.resolver.perform_basic(action)

        if result.status == "success":
            add_log(
                "MediaControl действие выполнено",
                meta={"action": action, "action_id": action_id},
            )
            return ModuleResponse(text=self._success_text(action, result))

        if result.status == "not_found":
            add_log(
                "MediaControl сценарий не найден",
                meta={"query": query},
                level="warn",
            )
            return ModuleResponse(text="Не нашла такой музыкальный сценарий.")

        return ModuleResponse(text=f"Не смогла выполнить действие: {result.message}")

    def _find_action_match(self, text: str) -> tuple[str, str, str] | None:
        matches: list[tuple[int, str, str, str]] = []

        for action_id, action in ACTION_BY_GROUP.items():
            for trigger in self.get_action_triggers(action_id):
                normalized_trigger = normalize_alias(trigger)

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
        query = re.sub(r"^(змея|змей|змею)\s+", "", query)
        return re.sub(r"\s+", " ", query).strip()

    def _find_preset_query(self, text: str, trigger: str) -> str | None:
        query = self._extract_query(text, trigger)

        if self.store.find_by_query(query) is not None:
            return query

        if self.store.find_by_query(text) is not None:
            return text

        return None

    def _success_text(self, action: str, result) -> str:
        if action == "pause":
            return "Передала Windows медиакоманду play/pause. Если есть активный медиасеанс, он должен переключиться."

        if action == "resume":
            return "Передала Windows медиакоманду play/pause. Если есть активный медиасеанс, он должен переключиться."

        if action == "next":
            return "Передала Windows команду следующего трека."

        if action == "previous":
            return "Передала Windows команду предыдущего трека."

        if action == "stop":
            return "Передала Windows команду остановить медиавоспроизведение."

        return result.message
