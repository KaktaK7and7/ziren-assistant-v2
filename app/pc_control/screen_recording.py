from __future__ import annotations

import os
from pathlib import Path


class ScreenRecordingError(RuntimeError):
    pass


def default_recording_directory() -> Path:
    """Return the standard Windows Game Bar capture directory.

    Ziren uses the system recorder (Win+Alt+R), so the canonical destination is
    the user's Videos/Captures folder. The directory is created on demand only
    when the user explicitly asks to open it.
    """
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "Videos" / "Captures"


def open_recording_directory() -> Path:
    target = default_recording_directory()

    if os.name != "nt" or not hasattr(os, "startfile"):
        raise ScreenRecordingError(
            "Открытие папки записей экрана доступно только в Windows"
        )

    try:
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))  # type: ignore[attr-defined]
    except OSError as error:
        raise ScreenRecordingError(
            f"Не удалось открыть папку записей экрана: {error}"
        ) from error

    return target
