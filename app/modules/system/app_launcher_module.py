import re
import time

from app.app_launcher.matcher import normalize_text
from app.app_launcher.models import AppTarget
from app.app_launcher.resolver import AppResolver
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


VOLUME_WORDS = ["громкость", "громче", "тише", "звук"]
QUERY_STOP_WORDS = [
    "приложение",
    "приложуху",
    "прогу",
    "программа",
    "игру",
    "игра",
]
SELECTION_TTL_SECONDS = 30.0
SELECTION_ALIASES = {
    0: [
        "1",
        "один",
        "первый",
        "первую",
        "вариант один",
        "номер один",
        "открой первый",
        "запусти первый",
    ],
    1: [
        "2",
        "два",
        "второй",
        "вторую",
        "вариант два",
        "номер два",
        "открой второй",
        "запусти второй",
    ],
    2: [
        "3",
        "три",
        "третий",
        "третью",
        "вариант три",
        "номер три",
        "открой третий",
    ],
    3: [
        "4",
        "четыре",
        "четвертый",
        "четвертую",
        "вариант четыре",
    ],
    4: [
        "5",
        "пять",
        "пятый",
        "пятую",
        "вариант пять",
    ],
}


class SystemAppLauncherModule(AssistantModule):
    feature_id = "system.app_launcher"
    display_name = "Запуск приложений"
    plan = Plan.FREE
    default_trigger_groups = {
        "app.launch": {
            "display_name": "Запустить приложение",
            "triggers": [
                "открой",
                "запусти",
                "включи",
                "открой приложение",
                "запусти приложение",
                "открой игру",
                "запусти игру",
            ],
        }
    }

    def __init__(self, resolver: AppResolver | None = None) -> None:
        self.resolver = resolver or AppResolver()
        self.pending_candidates: list[AppTarget] = []
        self.pending_query = ""
        self.pending_created_at = 0.0

    def can_handle(self, text: str) -> bool:
        normalized_text = normalize_text(text)

        if any(word in normalized_text for word in VOLUME_WORDS):
            return False

        if self._has_active_pending_selection():
            return self._extract_selection_index(normalized_text) is not None or any(
                self._contains_trigger(normalized_text, trigger)
                for trigger in self.get_action_triggers("app.launch")
            )

        return any(
            self._contains_trigger(normalized_text, trigger)
            for trigger in self.get_action_triggers("app.launch")
        )

    def handle(self, text: str) -> ModuleResponse:
        if self._has_active_pending_selection():
            selection_index = self._extract_selection_index(text)

            if selection_index is not None:
                return self._handle_pending_selection(selection_index)

            if self._is_launch_command(text):
                self._clear_pending_selection()

        query = self._extract_query(text)

        if not query:
            return ModuleResponse(text="Что открыть?")

        resolution = self.resolver.launch_query(query)

        if resolution.status == "found" and resolution.target is not None:
            return ModuleResponse(text=self._format_open_response(resolution.target))

        if resolution.status == "ambiguous":
            self.pending_candidates = resolution.candidates[:5]
            self.pending_query = query
            self.pending_created_at = time.time()

            variants = ", ".join(
                f"{index}. {candidate.name}"
                for index, candidate in enumerate(self.pending_candidates, start=1)
            )
            return ModuleResponse(
                text=(
                    f"Я нашла несколько вариантов: {variants}. "
                    "Скажи: первый, второй или уточни название."
                )
            )

        if resolution.status == "error":
            return ModuleResponse(
                text=f"Не смогла открыть {query}: {resolution.message}"
            )

        return ModuleResponse(
            text=(
                f"Не нашла приложение {query}. Позже я смогу открыть окно добавления "
                "приложения, чтобы ты указал файл запуска один раз."
            )
        )

    def _handle_pending_selection(self, selection_index: int) -> ModuleResponse:
        if selection_index >= len(self.pending_candidates):
            return ModuleResponse(
                text=(
                    "Такого варианта нет. Назови номер от 1 до "
                    f"{len(self.pending_candidates)}."
                )
            )

        target = self.pending_candidates[selection_index]
        pending_query = self.pending_query

        try:
            self.resolver.launcher.launch(target)
            self.resolver.cache.remember_target(target)

            if pending_query:
                self.resolver.cache.remember_alias(pending_query, target)

            self._clear_pending_selection()
            return ModuleResponse(
                text=f"{self._format_open_response(target)} Запомнила этот выбор."
            )
        except Exception as error:
            return ModuleResponse(
                text=f"Не смогла открыть {target.name}: {error}"
            )

    def _extract_query(self, text: str) -> str:
        query = normalize_text(text)
        query = re.sub(r"^(змея|змей|змею)\s+", "", query)

        triggers = sorted(
            self.get_action_triggers("app.launch"),
            key=lambda trigger: len(normalize_text(trigger)),
            reverse=True,
        )

        for trigger in triggers:
            normalized_trigger = normalize_text(trigger)

            if not normalized_trigger:
                continue

            query, replacements = re.subn(
                rf"\b{re.escape(normalized_trigger)}\b",
                " ",
                query,
                count=1,
            )

            if replacements:
                break

        for stop_word in QUERY_STOP_WORDS:
            query = re.sub(rf"\b{re.escape(stop_word)}\b", " ", query)

        return re.sub(r"\s+", " ", query).strip()

    def _extract_selection_index(self, text: str) -> int | None:
        normalized_text = normalize_text(text)
        normalized_text = re.sub(r"^(змея|змей|змею)\s+", "", normalized_text)

        for index, aliases in SELECTION_ALIASES.items():
            for alias in aliases:
                normalized_alias = normalize_text(alias)

                if re.search(rf"\b{re.escape(normalized_alias)}\b", normalized_text):
                    return index

        return None

    def _has_active_pending_selection(self) -> bool:
        if not self.pending_candidates:
            return False

        if time.time() - self.pending_created_at > SELECTION_TTL_SECONDS:
            self._clear_pending_selection()
            return False

        return True

    def _clear_pending_selection(self) -> None:
        self.pending_candidates = []
        self.pending_query = ""
        self.pending_created_at = 0.0

    def _format_open_response(self, target: AppTarget) -> str:
        if target.type == "steam":
            return f"Открываю {target.name} через Steam."

        if target.source == "wargaming_shortcut":
            return f"Открываю {target.name} через игровой центр."

        return f"Открываю {target.name}."

    def _is_launch_command(self, text: str) -> bool:
        normalized_text = normalize_text(text)
        return any(
            self._contains_trigger(normalized_text, trigger)
            for trigger in self.get_action_triggers("app.launch")
        )

    def _contains_trigger(self, text: str, trigger: str) -> bool:
        normalized_trigger = normalize_text(trigger)

        if not normalized_trigger:
            return False

        return re.search(rf"\b{re.escape(normalized_trigger)}\b", text) is not None
