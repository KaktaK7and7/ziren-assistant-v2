from app.core.log_bus import add_log
from app.media_control.models import MediaActionResult
from app.media_control.store import MusicPresetStore
from app.media_control.windows_media import (
    open_url,
    press_next_track,
    press_play_pause,
    press_previous_track,
    press_stop,
)


class MediaResolver:
    def __init__(self, store: MusicPresetStore | None = None) -> None:
        self.store = store or MusicPresetStore()

    def perform_basic(self, action: str) -> MediaActionResult:
        try:
            if action == "pause":
                press_play_pause()
                return MediaActionResult("success", "Ставлю на паузу.")

            if action == "resume":
                press_play_pause()
                return MediaActionResult("success", "Продолжаю воспроизведение.")

            if action == "play_pause":
                press_play_pause()
                return MediaActionResult("success", "Переключаю воспроизведение.")

            if action == "next":
                press_next_track()
                return MediaActionResult("success", "Включаю следующий трек.")

            if action == "previous":
                press_previous_track()
                return MediaActionResult("success", "Включаю предыдущий трек.")

            if action == "stop":
                press_stop()
                return MediaActionResult("success", "Останавливаю музыку.")

            return MediaActionResult("error", f"Unknown media action: {action}")
        except Exception as error:
            return MediaActionResult("error", str(error))

    def play_preset(self, query: str) -> MediaActionResult:
        preset = self.store.find_by_query(query)

        if preset is None:
            return MediaActionResult("not_found", "Не нашла такой музыкальный сценарий.")

        try:
            add_log(
                "MediaControl сценарий найден",
                meta={
                    "preset_name": preset.name,
                    "url": preset.url,
                    "enabled": preset.enabled,
                },
            )
            open_url(preset.url)
            return MediaActionResult(
                "success",
                (
                    f"Открываю {preset.name}. Нажми Play на странице, а потом я смогу "
                    "ставить музыку на паузу, продолжать и переключать треки."
                ),
                preset=preset,
            )
        except Exception as error:
            return MediaActionResult("error", str(error), preset=preset)

    def test_preset(self, url: str) -> MediaActionResult:
        try:
            if not url.strip():
                return MediaActionResult("error", "Ссылка обязательна.")

            open_url(url.strip())
            return MediaActionResult("success", "Открываю ссылку.")
        except Exception as error:
            return MediaActionResult("error", str(error))
