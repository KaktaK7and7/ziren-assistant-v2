from __future__ import annotations

import base64
import io
import os
import re
from dataclasses import dataclass

from app.vision.windows_geometry import enable_per_monitor_dpi_awareness


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
    r"\b(?:нажми|нажимай|нажать|кликни|кликай|кликнуть|"
    r"щёлкни|щелкни|открой|выбери|перейди)\b",
    re.IGNORECASE,
)
SCREEN_CLICK_TARGET_RE = re.compile(
    r"\b(?:кнопк\w*|пункт\w*|меню|вкладк\w*|ссылк\w*|иконк\w*|"
    r"значк\w*|профил\w*|ник\w*|им(?:я|ени|енем)|пол\w*|"
    r"переключател\w*)\b",
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
    source_width: int | None = None
    source_height: int | None = None


def _foreground_window_handle() -> int | None:
    if os.name != "nt":
        return None

    try:
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow()) or None
    except Exception:
        return None


def is_screen_analysis_request(
    text: str,
    allow_click_followup: bool = False,
) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False

    explicit_screen_request = bool(
        SCREEN_REFERENCE_RE.search(normalized)
        and SCREEN_REQUEST_RE.search(normalized)
    )
    click_request = bool(SCREEN_CLICK_REQUEST_RE.search(normalized))
    direct_visible_target = bool(SCREEN_CLICK_TARGET_RE.search(normalized))
    return bool(
        explicit_screen_request
        or (click_request and direct_visible_target)
        or (allow_click_followup and click_request)
    )


def is_screen_click_request(text: str) -> bool:
    return bool(SCREEN_CLICK_REQUEST_RE.search(str(text or "")))


def is_screen_canvas_request(text: str) -> bool:
    return bool(SCREEN_CANVAS_REQUEST_RE.search(str(text or "")))


def build_grounded_screen_data_url(capture: CapturedScreen) -> str:
    """Add a model-only coordinate grid without changing the stored capture."""
    from PIL import Image, ImageDraw

    prefix = "data:image/jpeg;base64,"
    if not capture.data_url.startswith(prefix):
        raise ValueError("Screen capture must be a JPEG data URL")

    try:
        encoded = base64.b64decode(
            capture.data_url[len(prefix):],
            validate=True,
        )
        image = Image.open(io.BytesIO(encoded)).convert("RGBA")
    except Exception as error:
        raise ValueError("Cannot prepare the screen grounding grid") from error

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    line_width = max(1, round(min(image.size) / 600))
    label_height = max(14, round(image.height * 0.018))
    label_width = max(34, round(image.width * 0.032))

    for index in range(1, 10):
        ratio = index / 10
        x = round((image.width - 1) * ratio)
        y = round((image.height - 1) * ratio)
        draw.line(
            [(x, 0), (x, image.height)],
            fill=(0, 229, 255, 125),
            width=line_width,
        )
        draw.line(
            [(0, y), (image.width, y)],
            fill=(0, 229, 255, 125),
            width=line_width,
        )
        draw.rectangle(
            [(x + 2, 2), (x + label_width, label_height + 2)],
            fill=(1, 12, 18, 205),
        )
        draw.text(
            (x + 5, 3),
            f"x.{index}",
            fill=(118, 255, 247, 255),
        )
        draw.rectangle(
            [(2, y + 2), (label_width, y + label_height + 2)],
            fill=(1, 12, 18, 205),
        )
        draw.text(
            (5, y + 3),
            f"y.{index}",
            fill=(118, 255, 247, 255),
        )

    grounded = Image.alpha_composite(image, overlay).convert("RGB")
    grounded_bytes = b""
    for quality in (78, 68, 58, 48):
        buffer = io.BytesIO()
        grounded.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        grounded_bytes = buffer.getvalue()
        if len(grounded_bytes) <= MAX_SCREENSHOT_BYTES:
            break

    if not grounded_bytes or len(grounded_bytes) > MAX_SCREENSHOT_BYTES:
        raise RuntimeError("Снимок с координатной сеткой получился слишком большим")

    payload = base64.b64encode(grounded_bytes).decode("ascii")
    return f"{prefix}{payload}"


def capture_primary_screen(
    max_width: int = 1600,
    max_height: int = 900,
) -> CapturedScreen:
    # Import lazily so a missing Windows capture backend cannot break startup.
    from PIL import Image, ImageGrab

    enable_per_monitor_dpi_awareness()
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
    source_width, source_height = image.size
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
        source_width=source_width,
        source_height=source_height,
    )
