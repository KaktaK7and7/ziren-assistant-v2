from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.voice.tts_silero import SileroTTS


_lock = threading.Lock()
_tts: "SileroTTS | None" = None


def register_tts(tts: "SileroTTS") -> None:
    global _tts
    with _lock:
        _tts = tts


def get_tts() -> "SileroTTS | None":
    with _lock:
        return _tts
