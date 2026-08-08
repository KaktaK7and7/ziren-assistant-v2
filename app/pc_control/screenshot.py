from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path

from app.vision.screen_capture import CapturedScreen, capture_primary_screen


JPEG_PREFIX = "data:image/jpeg;base64,"


class ScreenshotError(RuntimeError):
    pass


def default_screenshot_directory() -> Path:
    pictures = Path(os.environ.get("USERPROFILE", Path.home())) / "Pictures"
    return pictures / "Ziren" / "Screenshots"


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

    target_directory = directory or default_screenshot_directory()
    target_directory.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    path = target_directory / f"Ziren_{timestamp}.jpg"
    counter = 2

    while path.exists():
        path = target_directory / f"Ziren_{timestamp}_{counter}.jpg"
        counter += 1

    path.write_bytes(payload)
    return path


def capture_and_save(directory: Path | None = None) -> Path:
    return save_capture(capture_primary_screen(), directory=directory)
