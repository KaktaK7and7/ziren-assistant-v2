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

    print(f"[{item['ts']}] [{level.upper()}] {event}")


def get_logs() -> list[dict[str, Any]]:
    with _lock:
        return list(_logs)