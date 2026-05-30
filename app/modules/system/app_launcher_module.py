import re
import time

from app.app_launcher.debug import app_debug_step
from app.app_launcher.matcher import normalize_text
from app.app_launcher.models import AppTarget
from app.app_launcher.resolver import AppResolver
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


VOLUME_WORDS = ["громкость", "громче", "тише", "звук"]
ORDINAL_LABELS = ["первый", "второй", "третий"]
SPOKEN_NAME_FALLBACKS = [
    ("PUBG", "Пабг Батлграундс"),
    ("Dead Cells", "Дед Селс"),
    ("Euro Truck Simulator", "Евро Трак Симулятор"),
    ("Counter-Strike", "Ка Эс"),
    ("Need for Speed", "Нид фор Спид"),
    ("Wallpaper Engine", "Волпейпер Энжин"),
    ("Rust", "Раст"),
]
QUERY_STOP_WORDS = [
    "приложение",
    "приложуху",
    "прогу",
    "программа",
    "игру",
    "игра",
]
PENDING_SELECTION_TTL_SECONDS = 30.0
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
        "запусти третий",
    ],
    3: [
        "4",
        "четыре",
        "четвертый",
        "четвёртый",
        "четвертую",
        "четвёртую",
        "вариант четыре",
        "номер четыре",
    ],
    4: [
        "5",
        "пять",
        "пятый",
        "пятую",
        "вариант пять",
        "номер пять",
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
            if self._extract_selection_index(normalized_text) is not None:
                return True

        return self._contains_launch_trigger(normalized_text)

    def handle(self, text: str) -> ModuleResponse:
        if self._has_active_pending_selection():
            app_debug_step(
                "pending selection received",
                {
                    "text": text,
                    "pending_query": self.pending_query,
                    "candidates": [
                        candidate.name for candidate in self.pending_candidates
                    ],
                },
            )
            pending_response = self._handle_pending_selection(text)

            if pending_response is not None:
                return pending_response

            if self._is_launch_command(text):
                self._clear_pending_selection()

        query = self._extract_query(text)
        app_debug_step(
            "command received",
            {
                "raw_text": text,
                "query": query,
            },
        )

        if not query:
            app_debug_step("empty query")
            return ModuleResponse(text="Что открыть?")

        resolution = self.resolver.launch_query(query)

        if resolution.status == "found" and resolution.target is not None:
            return ModuleResponse(
                text=self._format_launch_response(
                    resolution.target,
                    resolution.spoken_name,
                )
            )

        if resolution.status == "ambiguous":
            readable_candidates = [
                candidate
                for candidate in resolution.candidates[:3]
                if self._target_speech_name(candidate)
            ]

            if not readable_candidates:
                return ModuleResponse(
                    text="Не смогла уверенно выбрать приложение. Попробуй назвать его точнее."
                )

            self.pending_candidates = readable_candidates
            self.pending_query = query
            self.pending_created_at = time.time()
            app_debug_step(
                "pending selection created",
                {
                    "query": query,
                    "candidates": [
                        candidate.name for candidate in self.pending_candidates
                    ],
                },
            )

            variants = ", ".join(
                f"{ORDINAL_LABELS[index]} — {self._target_speech_name(candidate)}"
                for index, candidate in enumerate(self.pending_candidates)
            )
            return ModuleResponse(
                text=(
                    f"Я не уверена. Похоже на: {variants}. "
                    f"Скажи {self._selection_hint(len(self.pending_candidates))}."
                )
            )

        if resolution.status == "error":
            return ModuleResponse(
                text=f"Не смогла открыть {query}: {resolution.message}"
            )

        self._emit_not_found(query)

        return ModuleResponse(
            text=resolution.message
            or "Не смогла уверенно понять, какое приложение открыть. Попробуй назвать его точнее."
        )

    def _handle_pending_selection(self, text: str) -> ModuleResponse | None:
        selection_index = self._extract_selection_index(text)

        if selection_index is None:
            return None

        return self._launch_selected_target(selection_index)

    def _launch_selected_target(self, selection_index: int) -> ModuleResponse:
        if selection_index >= len(self.pending_candidates):
            return ModuleResponse(
                text=(
                    "Такого варианта нет. Назови номер от 1 до "
                    f"{len(self.pending_candidates)}."
                )
            )

        target = self.pending_candidates[selection_index]
        pending_query = self.pending_query
        app_debug_step(
            "pending selection selected",
            {
                "index": selection_index + 1,
                "target": target.name,
                "target_id": target.target_id,
            },
        )

        try:
            self.resolver.launcher.launch(target)
            self.resolver.cache.remember_target(target)

            if pending_query:
                self.resolver.cache.remember_alias(pending_query, target)

            self._clear_pending_selection()
            return ModuleResponse(
                text=f"{self._format_launch_response(target)} Запомнила этот выбор."
            )
        except Exception as error:
            return ModuleResponse(
                text=f"Не смогла открыть {self._target_speech_name(target)}: {error}"
            )

    def _extract_query(self, text: str) -> str:
        query = normalize_text(text)
        query = re.sub(r"^(змея|змей|змею)\s+", "", query)

        trigger = self._find_launch_trigger(query)

        if trigger is None:
            return ""

        query = re.sub(
            rf"\b{re.escape(trigger)}\b",
            " ",
            query,
            count=1,
        )

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

        if time.time() - self.pending_created_at > PENDING_SELECTION_TTL_SECONDS:
            self._clear_pending_selection()
            return False

        return True

    def _clear_pending_selection(self) -> None:
        self.pending_candidates = []
        self.pending_query = ""
        self.pending_created_at = 0.0

    def _target_speech_name(
        self,
        target: AppTarget,
        fallback_spoken_name: str | None = None,
    ) -> str:
        if fallback_spoken_name:
            return fallback_spoken_name

        if target.spoken_name:
            return target.spoken_name

        for marker, spoken_name in SPOKEN_NAME_FALLBACKS:
            if marker.lower() in target.name.lower():
                return spoken_name

        return target.name.strip()

    def _format_open_response(
        self,
        target: AppTarget,
        fallback_spoken_name: str | None = None,
    ) -> str:
        speech_name = self._target_speech_name(target, fallback_spoken_name)

        if target.type == "steam":
            return f"Открываю {speech_name} через Стим."

        if target.source == "wargaming_shortcut":
            return f"Открываю {speech_name} через игровой центр."

        return f"Открываю {speech_name}."

    def _format_launch_response(
        self,
        target: AppTarget,
        fallback_spoken_name: str | None = None,
    ) -> str:
        speech_name = self._target_speech_name(target, fallback_spoken_name)

        if self.resolver.launcher.last_launch_was_elevated:
            return (
                f"Открываю {speech_name} с повышенными правами. "
                
            )
        return self._format_open_response(target, fallback_spoken_name)

    def _is_launch_command(self, text: str) -> bool:
        normalized_text = normalize_text(text)
        return self._contains_launch_trigger(normalized_text)

    def _selection_hint(self, count: int) -> str:
        labels = ORDINAL_LABELS[:count]

        if len(labels) == 1:
            return labels[0]

        return " или ".join([", ".join(labels[:-1]), labels[-1]]).strip(" ,")

    def _emit_not_found(self, query: str) -> None:
        try:
            from app.events.event_bus import emit_event

            emit_event("app.launcher.not_found", payload={"query": query}, level="warn")
        except Exception:
            pass

    def _contains_trigger(self, text: str, trigger: str) -> bool:
        normalized_trigger = normalize_text(trigger)

        if not normalized_trigger:
            return False

        return re.search(rf"\b{re.escape(normalized_trigger)}\b", text) is not None

    def _contains_launch_trigger(self, text: str) -> bool:
        return self._find_launch_trigger(text) is not None

    def _find_launch_trigger(self, text: str) -> str | None:
        normalized_text = normalize_text(text)
        triggers = sorted(
            (
                normalize_text(trigger)
                for trigger in self.get_action_triggers("app.launch")
            ),
            key=len,
            reverse=True,
        )

        for trigger in triggers:
            if not trigger:
                continue

            if re.search(rf"\b{re.escape(trigger)}\b", normalized_text):
                return trigger

        return None
