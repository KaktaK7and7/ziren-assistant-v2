import time
from os.path import basename

from app.app_launcher.ai_disambiguator import AppAIDisambiguator
from app.app_launcher.cache import AppLauncherCache
from app.app_launcher.debug import app_debug_step
from app.app_launcher.launcher import AppLauncher
from app.app_launcher.matcher import AppMatcher, normalize_text
from app.app_launcher.models import AppTarget, LaunchResolution
from app.app_launcher.steam_indexer import SteamIndexer
from app.app_launcher.windows_indexer import WindowsIndexer


class AppResolver:
    INDEX_TTL_SECONDS = 300

    def __init__(
        self,
        cache: AppLauncherCache | None = None,
        steam_indexer: SteamIndexer | None = None,
        windows_indexer: WindowsIndexer | None = None,
        matcher: AppMatcher | None = None,
        launcher: AppLauncher | None = None,
        ai_disambiguator: AppAIDisambiguator | None = None,
        enable_ai_disambiguation: bool = True,
    ) -> None:
        self.cache = cache or AppLauncherCache()
        self.steam_indexer = steam_indexer or SteamIndexer()
        self.windows_indexer = windows_indexer or WindowsIndexer()
        self.matcher = matcher or AppMatcher()
        self.launcher = launcher or AppLauncher()
        self.ai_disambiguator = ai_disambiguator or AppAIDisambiguator()
        self.enable_ai_disambiguation = enable_ai_disambiguation
        self._targets: list[AppTarget] = []
        self._last_index_at = 0.0

    def build_index(self, force: bool = False) -> list[AppTarget]:
        now = time.time()

        if (
            not force
            and self._targets
            and now - self._last_index_at < self.INDEX_TTL_SECONDS
        ):
            return list(self._targets)

        targets: list[AppTarget] = []
        targets.extend(self.steam_indexer.index())
        targets.extend(self.windows_indexer.index())
        self._targets = self._deduplicate(targets)
        self._last_index_at = now
        return list(self._targets)

    def resolve(self, query: str) -> LaunchResolution:
        normalized_query = normalize_text(query)
        app_debug_step("resolve started", {"query": normalized_query})

        if not normalized_query:
            return LaunchResolution(
                status="not_found",
                query=query,
                message="Не указано приложение для запуска.",
            )

        cached_target = self.cache.get_alias(normalized_query)

        if cached_target is not None:
            app_debug_step(
                "cache hit",
                {
                    "query": normalized_query,
                    "target": cached_target.name,
                    "target_id": cached_target.target_id,
                    "type": cached_target.type,
                    "source": cached_target.source,
                },
            )
            return LaunchResolution(
                status="found",
                query=normalized_query,
                target=cached_target,
            )

        app_debug_step("cache miss", {"query": normalized_query})
        targets = self.build_index()
        app_debug_step(
            "index built",
            {
                "targets_count": len(targets),
                "first_targets": [target.name for target in targets[:20]],
            },
        )
        local_resolution = self.matcher.match(normalized_query, targets)
        app_debug_step(
            "local match result",
            {
                "status": local_resolution.status,
                "target": local_resolution.target.name if local_resolution.target else None,
                "candidates": [
                    candidate.name for candidate in local_resolution.candidates[:10]
                ],
            },
        )

        if local_resolution.status == "found":
            return local_resolution

        if not self.enable_ai_disambiguation:
            return local_resolution

        if local_resolution.status == "ambiguous":
            ai_resolution = self._resolve_with_ai(
                normalized_query,
                local_resolution,
                local_resolution.candidates[:40],
            )

            if ai_resolution.status == "found":
                return ai_resolution

            readable_candidates = self._readable_candidates(local_resolution.candidates, limit=3)

            if not readable_candidates:
                return LaunchResolution(
                    status="not_found",
                    query=normalized_query,
                    message="Не смогла уверенно выбрать приложение",
                )

            return LaunchResolution(
                status="ambiguous",
                query=normalized_query,
                candidates=readable_candidates,
                message=ai_resolution.message or local_resolution.message,
            )

        if local_resolution.status == "not_found":
            candidates = self.matcher.rank_candidates_for_ai(
                normalized_query,
                targets,
                limit=40,
            )

            if not candidates:
                return local_resolution

            ai_resolution = self._resolve_with_ai(
                normalized_query,
                LaunchResolution(
                    status="ambiguous",
                    query=normalized_query,
                    candidates=candidates,
                    message="Я нашла несколько возможных вариантов.",
                ),
                candidates,
            )

            if ai_resolution.status == "found":
                return ai_resolution

            return LaunchResolution(
                status="not_found",
                query=normalized_query,
                message="Не смогла уверенно понять, какое приложение открыть. Попробуй назвать его точнее.",
            )

        return local_resolution

    def launch_query(self, query: str) -> LaunchResolution:
        normalized_query = normalize_text(query)

        try:
            resolution = self.resolve(normalized_query)
            target = resolution.target
            app_debug_step(
                "launch requested",
                {
                    "query": normalized_query,
                    "status": resolution.status,
                    "target": target.name if target else None,
                    "type": target.type if target else None,
                    "source": target.source if target else None,
                    "spoken_name": resolution.spoken_name,
                },
            )

            if resolution.status != "found" or resolution.target is None:
                app_debug_step(
                    "launch skipped",
                    {
                        "status": resolution.status,
                        "message": resolution.message,
                    },
                )
                return resolution

            if resolution.spoken_name:
                resolution.target.spoken_name = resolution.spoken_name

            self.launcher.launch(resolution.target)
            app_debug_step(
                "launch success",
                {
                    "target": resolution.target.name,
                    "target_id": resolution.target.target_id,
                },
            )
            self.cache.remember_target(resolution.target)
            self.cache.remember_alias(normalized_query, resolution.target)
            app_debug_step(
                "cache saved",
                {
                    "alias": normalized_query,
                    "target": resolution.target.name,
                    "target_id": resolution.target.target_id,
                },
            )
            return resolution
        except Exception as error:
            app_debug_step(
                "launch error",
                {
                    "query": normalized_query,
                    "error": str(error),
                },
            )
            return LaunchResolution(
                status="error",
                query=normalized_query,
                message=str(error),
            )

    def _deduplicate(self, targets: list[AppTarget]) -> list[AppTarget]:
        deduped: list[AppTarget] = []
        seen: set[str] = set()

        for target in targets:
            if target.target_id in seen:
                continue

            deduped.append(target)
            seen.add(target.target_id)

        return deduped

    def _resolve_with_ai(
        self,
        query: str,
        resolution: LaunchResolution,
        candidates: list[AppTarget],
    ) -> LaunchResolution:
        app_debug_step(
            "ai candidate list prepared",
            {
                "query": query,
                "count": len(candidates),
                "candidates": [
                    {
                        "index": index + 1,
                        "name": candidate.name,
                        "type": candidate.type,
                        "source": candidate.source,
                        "appid": candidate.appid,
                        "path_basename": basename(candidate.path) if candidate.path else "",
                    }
                    for index, candidate in enumerate(candidates[:20])
                ],
            },
        )
        ai_result = self.ai_disambiguator.choose(query, candidates)

        if (
            ai_result.selected_index is None
            or ai_result.confidence < 0.82
            or ai_result.selected_index < 0
            or ai_result.selected_index >= len(candidates)
        ):
            app_debug_step(
                "ai did not select",
                {
                    "query": query,
                    "confidence": ai_result.confidence,
                    "reason": ai_result.reason,
                },
            )
            return LaunchResolution(
                status=resolution.status,
                query=resolution.query,
                target=resolution.target,
                candidates=resolution.candidates,
                message=self._ai_fallback_message(ai_result.reason) or resolution.message,
                spoken_name=resolution.spoken_name,
            )

        selected_target = candidates[ai_result.selected_index]
        selected_target.spoken_name = ai_result.spoken_name or selected_target.spoken_name

        app_debug_step(
            "ai selected",
            {
                "query": query,
                "selected_index": ai_result.selected_index,
                "target": selected_target.name,
                "confidence": ai_result.confidence,
                "spoken_name": ai_result.spoken_name,
                "reason": ai_result.reason,
            },
        )

        return LaunchResolution(
            status="found",
            query=query,
            target=selected_target,
            candidates=resolution.candidates,
            message="AI selected candidate",
            spoken_name=ai_result.spoken_name,
        )

    def _readable_candidates(
        self,
        candidates: list[AppTarget],
        limit: int,
    ) -> list[AppTarget]:
        readable: list[AppTarget] = []

        for candidate in candidates:
            name = (candidate.spoken_name or candidate.name or "").strip()

            if not name:
                continue

            readable.append(candidate)

            if len(readable) >= limit:
                break

        return readable

    def _ai_fallback_message(self, reason: str) -> str:
        reason_lower = reason.lower()

        if any(
            marker in reason_lower
            for marker in ["timed out", "timeout", "http", "connect", "network"]
        ):
            return "AI service unavailable"

        return ""
