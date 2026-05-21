import difflib
import re

from app.app_launcher.models import AppTarget, LaunchResolution

try:
    from Levenshtein import distance as levenshtein_distance
except Exception:
    levenshtein_distance = None


DANGEROUS_EXE_MARKERS = [
    "setup",
    "install",
    "installer",
    "uninstall",
    "unins",
    "unins000",
    "update",
    "updater",
    "patcher",
    "repair",
    "redist",
    "vcredist",
    "directx",
    "dxsetup",
    "crash",
    "crashreporter",
    "reporter",
    "helper",
    "service",
    "bootstrapper",
    "eac_setup",
    "easyanticheat_setup",
    "battleye",
    "cef",
    "webview",
    "launcher_updater",
    "удалить",
    "деинсталлировать",
    "деинсталлятор",
]


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_dangerous_exe_name(value: str) -> bool:
    normalized = value.lower().replace("\\", "/")
    return any(marker in normalized for marker in DANGEROUS_EXE_MARKERS)


class AppMatcher:
    def score(self, query: str, target: AppTarget) -> float:
        normalized_query = normalize_text(query)
        names = [target.name, *target.aliases]
        best_score = 0.0

        for name in names:
            normalized_name = normalize_text(name)

            if not normalized_name:
                continue

            if normalized_query == normalized_name:
                best_score = max(best_score, 1.0)
            elif normalized_query in normalized_name:
                best_score = max(best_score, 0.92)
            elif normalized_name in normalized_query:
                best_score = max(best_score, 0.84)
            else:
                best_score = max(
                    best_score,
                    self._similarity(normalized_query, normalized_name),
                )

        best_score += target.confidence_bonus
        best_score += self._type_bonus(target)

        if target.type == "exe" and is_dangerous_exe_name(target.path or target.name):
            best_score -= 0.45
        elif target.type == "shortcut" and is_dangerous_exe_name(target.path or target.name):
            best_score -= 0.25

        return max(0.0, best_score)

    def match(self, query: str, targets: list[AppTarget]) -> LaunchResolution:
        scored = [
            (self.score(query, target), self._sort_priority(target), target)
            for target in targets
        ]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(key=lambda item: (-item[0], item[1], item[2].name.lower()))

        if not scored:
            return LaunchResolution(
                status="not_found",
                query=query,
                message=f"Не нашла приложение {query}.",
            )

        best_score, _, best_target = scored[0]
        second_score = self._second_distinct_score(best_target, scored[1:])

        if best_score >= 0.86 and best_score - second_score >= 0.08:
            return LaunchResolution(status="found", query=query, target=best_target)

        if best_score >= 0.68:
            return LaunchResolution(
                status="ambiguous",
                query=query,
                candidates=self._unique_candidates([target for _, _, target in scored[:5]]),
                message="Найдено несколько похожих приложений.",
            )

        return LaunchResolution(
            status="not_found",
            query=query,
            message=f"Не нашла приложение {query}.",
        )

    def _similarity(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0

        if levenshtein_distance is not None:
            max_length = max(len(left), len(right))
            return 1.0 - (levenshtein_distance(left, right) / max_length)

        return difflib.SequenceMatcher(None, left, right).ratio()

    def _type_bonus(self, target: AppTarget) -> float:
        if target.type == "steam":
            return 0.04
        if target.type == "shortcut" and target.source == "wargaming_shortcut":
            return 0.035
        if target.type == "shortcut":
            return 0.03
        if target.type == "system":
            return 0.02
        return 0.0

    def _sort_priority(self, target: AppTarget) -> int:
        if target.type == "steam":
            return 0
        if target.type == "shortcut" and target.source == "wargaming_shortcut":
            return 1
        if target.type == "shortcut":
            return 2
        if target.type == "system":
            return 3
        return 4

    def _second_distinct_score(
        self,
        best_target: AppTarget,
        scored_targets: list[tuple[float, int, AppTarget]],
    ) -> float:
        best_name = normalize_text(best_target.name)

        for score, _, target in scored_targets:
            if normalize_text(target.name) != best_name:
                return score

        return 0.0

    def _unique_candidates(self, candidates: list[AppTarget]) -> list[AppTarget]:
        unique: list[AppTarget] = []
        seen: set[str] = set()

        for candidate in candidates:
            key = normalize_text(candidate.name)

            if key in seen:
                continue

            unique.append(candidate)
            seen.add(key)

        return unique
