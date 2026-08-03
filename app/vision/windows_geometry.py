from __future__ import annotations

import os
from threading import Lock


_dpi_lock = Lock()
_dpi_awareness_attempted = False


def enable_per_monitor_dpi_awareness() -> None:
    """Keep screenshots and Win32 cursor coordinates in the same pixel space."""
    global _dpi_awareness_attempted

    if os.name != "nt" or _dpi_awareness_attempted:
        return

    with _dpi_lock:
        if _dpi_awareness_attempted:
            return
        _dpi_awareness_attempted = True

        import ctypes

        user32 = ctypes.windll.user32
        try:
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        except (AttributeError, OSError):
            pass

        try:
            # PROCESS_PER_MONITOR_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except (AttributeError, OSError):
            pass

        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
