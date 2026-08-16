import sys
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any

MAX_LOGS = 300

_logs: deque[dict[str, Any]] = deque(maxlen=MAX_LOGS)
_lock = Lock()


def add_log(event: str, level: str = "info", meta: dict[str, Any] | None = None) -> None:
    item = {
        "ts": datetime.now().isoformat(),
        "level": level,
        "event": event,
        "meta": meta or {},
    }

    with _lock:
        _logs.append(item)

    _safe_console_print(f"[{item['ts']}] [{level.upper()}] {event}")


def _safe_console_print(value: str) -> None:
    """Console diagnostics must never be able to crash the assistant."""
    try:
        print(value)
        return
    except UnicodeEncodeError:
        pass
    except (OSError, ValueError):
        return

    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        safe_value = value.encode(encoding, errors="replace").decode(
            encoding,
            errors="replace",
        )
        print(safe_value)
    except Exception:
        # The structured in-memory log above is still available to the GUI.
        return


def get_logs() -> list[dict[str, Any]]:
    with _lock:
        return list(_logs)
