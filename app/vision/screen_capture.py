from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass


SCREEN_REFERENCE_RE = re.compile(
    r"\b(?:экран\w*|окн\w*|страниц\w*|монитор\w*)\b",
    re.IGNORECASE,
)
SCREEN_REQUEST_RE = re.compile(
    r"\b(?:что|кто|где|как|покажи|посмотри|проверь|объясни|"
    r"помоги|разберись|разобраться|нажать|делать)\b",
    re.IGNORECASE,
)
MAX_SCREENSHOT_BYTES = 1_200_000


@dataclass(frozen=True)
class CapturedScreen:
    data_url: str
    width: int
    height: int
    byte_size: int


def is_screen_analysis_request(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return bool(
        normalized
        and SCREEN_REFERENCE_RE.search(normalized)
        and SCREEN_REQUEST_RE.search(normalized)
    )


def capture_primary_screen(
    max_width: int = 1600,
    max_height: int = 900,
) -> CapturedScreen:
    # Import lazily so a missing Windows capture backend cannot break startup.
    from PIL import Image, ImageGrab

    image = ImageGrab.grab()
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
    )
