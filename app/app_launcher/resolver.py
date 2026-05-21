import time

from app.app_launcher.cache import AppLauncherCache
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
    ) -> None:
        self.cache = cache or AppLauncherCache()
        self.steam_indexer = steam_indexer or SteamIndexer()
        self.windows_indexer = windows_indexer or WindowsIndexer()
        self.matcher = matcher or AppMatcher()
        self.launcher = launcher or AppLauncher()
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

        if not normalized_query:
            return LaunchResolution(
                status="not_found",
                query=query,
                message="Не указано приложение для запуска.",
            )

        cached_target = self.cache.get_alias(normalized_query)

        if cached_target is not None:
            return LaunchResolution(
                status="found",
                query=normalized_query,
                target=cached_target,
            )

        targets = self.build_index()
        return self.matcher.match(normalized_query, targets)

    def launch_query(self, query: str) -> LaunchResolution:
        normalized_query = normalize_text(query)

        try:
            resolution = self.resolve(normalized_query)

            if resolution.status != "found" or resolution.target is None:
                return resolution

            self.launcher.launch(resolution.target)
            self.cache.remember_target(resolution.target)
            self.cache.remember_alias(normalized_query, resolution.target)
            return resolution
        except Exception as error:
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
