from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import uuid4

MAX_EVENTS = 300

_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_lock = Lock()


def emit_event(
    event_type: str,
    payload: dict | None = None,
    level: str = "info",
    write_log: bool = False,
) -> None:
    item = {
        "id": str(uuid4()),
        "ts": datetime.now().isoformat(),
        "type": event_type,
        "level": level,
        "payload": payload or {},
    }

    with _lock:
        _events.append(item)

    if write_log:
        from app.core.log_bus import add_log

        add_log(event_type, level=level, meta=item["payload"])


def get_events() -> list[dict]:
    with _lock:
        return list(_events)


def clear_events() -> None:
    with _lock:
        _events.clear()
