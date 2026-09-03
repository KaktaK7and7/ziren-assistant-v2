import webbrowser
from ctypes import windll
import platform


VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _ensure_windows() -> None:
    if platform.system().lower() != "windows":
        raise RuntimeError("Media keys are available only on Windows.")


def _press_key(vk_code: int) -> None:
    _ensure_windows()
    # These are global Windows media-key events. Windows accepting the event does
    # not prove that an application had an active media session, so callers must
    # report command delivery rather than claiming playback state changed.
    windll.user32.keybd_event(vk_code, 0, 0, 0)
    windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def press_play_pause() -> None:
    _press_key(VK_MEDIA_PLAY_PAUSE)


def press_next_track() -> None:
    _press_key(VK_MEDIA_NEXT_TRACK)


def press_previous_track() -> None:
    _press_key(VK_MEDIA_PREV_TRACK)


def press_stop() -> None:
    _press_key(VK_MEDIA_STOP)


def open_url(url: str) -> None:
    target = url.strip()
    if not target:
        raise RuntimeError("URL is required.")

    opened = bool(webbrowser.open(target))
    if not opened:
        raise RuntimeError("Windows не подтвердила открытие ссылки в браузере.")
