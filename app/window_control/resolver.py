import re
from difflib import SequenceMatcher

from app.app_launcher.cache import AppLauncherCache
from app.core.log_bus import add_log
from app.window_control.models import WindowActionResult, WindowTarget
from app.window_control.windows_api import (
    focus_window,
    force_close_process,
    list_windows,
    maximize_window,
    minimize_window,
    restore_window,
    show_desktop,
)


def normalize_text(value: str) -> str:
    value = value.lower().replace("ё", "е").strip()
    value = re.sub(r"[^\w\s]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


class WindowResolver:
    def __init__(self, app_cache: AppLauncherCache | None = None) -> None:
        self.app_cache = app_cache or AppLauncherCache()

    def resolve(self, query: str) -> WindowActionResult:
        normalized_query = normalize_text(query)

        if not normalized_query:
            return WindowActionResult(status="not_found", message="Какое окно нужно?")

        try:
            windows = list_windows()
        except Exception as error:
            return WindowActionResult(status="error", message=str(error))

        add_log("Окна найдены", meta={"count": len(windows)})

        search_terms = self._build_search_terms(normalized_query)
        scored = sorted(
            (
                (self._score_window(window, search_terms), window)
                for window in windows
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        scored = [(score, window) for score, window in scored if score > 0]

        if not scored:
            return WindowActionResult(
                status="not_found",
                message=f"Не нашла открытое окно {query}.",
            )

        best_score, best_window = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0

        if best_score >= 0.78 and best_score - second_score >= 0.08:
            return WindowActionResult(
                status="success",
                message="Окно найдено.",
                target=best_window,
            )

        close_candidates = [
            window for score, window in scored[:3] if best_score - score < 0.12
        ]

        if len(close_candidates) > 1:
            return WindowActionResult(
                status="ambiguous",
                message="Нашла несколько похожих окон.",
                candidates=close_candidates,
            )

        return WindowActionResult(
            status="not_found",
            message=f"Не нашла открытое окно {query}.",
        )

    def perform(self, action: str, query: str | None = None) -> WindowActionResult:
        if action == "desktop":
            try:
                show_desktop()
                return WindowActionResult(
                    status="success",
                    message="Показываю рабочий стол.",
                )
            except Exception as error:
                return WindowActionResult(status="error", message=str(error))

        resolution = self.resolve(query or "")

        if resolution.status != "success" or resolution.target is None:
            return resolution

        target = resolution.target

        try:
            if action == "close":
                force_close_process(target.process_id)
            elif action == "minimize":
                minimize_window(target.hwnd)
            elif action == "maximize":
                maximize_window(target.hwnd)
            elif action == "restore":
                restore_window(target.hwnd)
            elif action == "focus":
                focus_window(target.hwnd)
            else:
                return WindowActionResult(
                    status="error",
                    message=f"Неизвестное действие: {action}",
                    target=target,
                )
        except Exception as error:
            return WindowActionResult(status="error", message=str(error), target=target)

        return WindowActionResult(
            status="success",
            message="Действие выполнено.",
            target=target,
        )

    def _build_search_terms(self, query: str) -> list[str]:
        terms = [query]
        target = self.app_cache.get_alias(query)

        if target is not None:
            terms.extend(
                [
                    target.name,
                    target.spoken_name or "",
                    *target.aliases,
                ]
            )

        data = self.app_cache.load()

        for target_data in data.get("targets", {}).values():
            if not isinstance(target_data, dict):
                continue

            aliases = target_data.get("aliases", [])

            if not isinstance(aliases, list):
                aliases = []

            normalized_aliases = {
                normalize_text(str(alias)) for alias in aliases if isinstance(alias, str)
            }
            name = str(target_data.get("name", ""))
            spoken_name = str(target_data.get("spoken_name", "") or "")

            if query in normalized_aliases or query == normalize_text(name):
                terms.extend([name, spoken_name, *aliases])

        normalized_terms = [normalize_text(term) for term in terms if term]
        return list(dict.fromkeys(term for term in normalized_terms if term))

    def _score_window(self, window: WindowTarget, search_terms: list[str]) -> float:
        title = normalize_text(window.title)
        process_name = normalize_text(window.process_name)
        best = 0.0

        for term in search_terms:
            if not term:
                continue

            if term == title or term == process_name:
                best = max(best, 1.0)
            elif term in title:
                best = max(best, 0.95)
            elif term in process_name:
                best = max(best, 0.9)

            best = max(
                best,
                SequenceMatcher(None, term, title).ratio(),
                SequenceMatcher(None, term, process_name).ratio(),
            )

        return best
