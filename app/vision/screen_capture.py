from __future__ import annotations

import base64
import io
import os
import re
from dataclasses import dataclass


SCREEN_REFERENCE_RE = re.compile(
    r"\b(?:экран\w*|окн\w*|страниц\w*|монитор\w*)\b",
    re.IGNORECASE,
)
SCREEN_REQUEST_RE = re.compile(
    r"\b(?:что|кто|где|как|покажи|посмотри|проверь|объясни|"
    r"помоги|разберись|разобраться|переведи|перевести|выдели|"
    r"нажми|нажать|кликни|открой|сохрани|делать)\b",
    re.IGNORECASE,
)
SCREEN_CLICK_REQUEST_RE = re.compile(
    r"\b(?:нажми|нажать|кликни|кликнуть|щёлкни|щелкни|"
    r"открой|выбери|перейди)\b",
    re.IGNORECASE,
)
SCREEN_CANVAS_REQUEST_RE = re.compile(
    r"\b(?:сохрани|добавь|перенеси|отправь)\b[^.!?\n]{0,48}"
    r"\b(?:холст|рисунк\w*|библиотек\w*)\b",
    re.IGNORECASE,
)
MAX_SCREENSHOT_BYTES = 1_200_000


@dataclass(frozen=True)
class CapturedScreen:
    data_url: str
    width: int
    height: int
    byte_size: int
    foreground_window: int | None = None


def _foreground_window_handle() -> int | None:
    if os.name != "nt":
        return None

    try:
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow()) or None
    except Exception:
        return None


def is_screen_analysis_request(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return bool(
        normalized
        and SCREEN_REFERENCE_RE.search(normalized)
        and SCREEN_REQUEST_RE.search(normalized)
    )


def is_screen_click_request(text: str) -> bool:
    return bool(SCREEN_CLICK_REQUEST_RE.search(str(text or "")))


def is_screen_canvas_request(text: str) -> bool:
    return bool(SCREEN_CANVAS_REQUEST_RE.search(str(text or "")))


def capture_primary_screen(
    max_width: int = 1600,
    max_height: int = 900,
) -> CapturedScreen:
    # Import lazily so a missing Windows capture backend cannot break startup.
    from PIL import Image, ImageGrab

    foreground_before = _foreground_window_handle()
    image = ImageGrab.grab()
    foreground_after = _foreground_window_handle()
    foreground_window = (
        foreground_before
        if foreground_before is not None
        and foreground_before == foreground_after
        else None
    )
    image = image.convert("RGB")
    image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    encoded = b""

    for quality in (78, 68, 58, 48):
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        encoded = buffer.getvalue()

        if len(encoded) <= MAX_SCREENSHOT_BYTES:
            break

    if not encoded or len(encoded) > MAX_SCREENSHOT_BYTES:
        raise RuntimeError("Снимок экрана получился слишком большим")

    payload = base64.b64encode(encoded).decode("ascii")
    return CapturedScreen(
        data_url=f"data:image/jpeg;base64,{payload}",
        width=image.width,
        height=image.height,
        byte_size=len(encoded),
        foreground_window=foreground_window,
    )
