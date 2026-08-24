from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path

from app.vision.screen_capture import CapturedScreen, capture_primary_screen


JPEG_PREFIX = "data:image/jpeg;base64,"
MIN_JPEG_BYTES = 64


class ScreenshotError(RuntimeError):
    pass


def default_screenshot_directory() -> Path:
    pictures = Path(os.environ.get("USERPROFILE", Path.home())) / "Pictures"
    return pictures / "Ziren" / "Screenshots"


def open_screenshot_directory() -> Path:
    target = default_screenshot_directory()
    target.mkdir(parents=True, exist_ok=True)

    if os.name != "nt" or not hasattr(os, "startfile"):
        raise ScreenshotError("Открытие папки скриншотов доступно только в Windows")

    try:
        os.startfile(str(target))
    except OSError as error:
        raise ScreenshotError(f"Не удалось открыть папку скриншотов: {error}") from error

    return target


def _validate_jpeg(payload: bytes) -> None:
    if (
        len(payload) < MIN_JPEG_BYTES
        or not payload.startswith(b"\xff\xd8\xff")
        or not payload.endswith(b"\xff\xd9")
    ):
        raise ScreenshotError("Получен повреждённый JPEG-снимок")


def save_capture(
    capture: CapturedScreen,
    directory: Path | None = None,
    now: datetime | None = None,
) -> Path:
    if not capture.data_url.startswith(JPEG_PREFIX):
        raise ScreenshotError("Неизвестный формат снимка")

    try:
        payload = base64.b64decode(
            capture.data_url[len(JPEG_PREFIX):],
            validate=True,
        )
    except Exception as error:
        raise ScreenshotError("Не удалось декодировать снимок") from error

    _validate_jpeg(payload)

    target_directory = directory or default_screenshot_directory()
    target_directory.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    path = target_directory / f"Ziren_{timestamp}.jpg"
    counter = 2

    while path.exists():
        path = target_directory / f"Ziren_{timestamp}_{counter}.jpg"
        counter += 1

    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("wb") as handle:
            written = handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if written != len(payload) or temporary.stat().st_size != len(payload):
            raise ScreenshotError("Файл скриншота записался не полностью")
        os.replace(temporary, path)
    except ScreenshotError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ScreenshotError(f"Не удалось сохранить скриншот: {error}") from error

    if not path.is_file() or path.stat().st_size != len(payload):
        raise ScreenshotError("Не удалось подтвердить сохранение скриншота")

    return path


def capture_and_save(directory: Path | None = None) -> Path:
    return save_capture(capture_primary_screen(), directory=directory)
