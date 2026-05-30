import json
import os
import re
from typing import Any


APP_LAUNCHER_DEBUG = os.getenv("APP_LAUNCHER_DEBUG", "1") != "0"
MAX_STRING_LENGTH = 300
MAX_LIST_ITEMS = 20
SECRET_KEY_MARKERS = ["token", "key", "secret", "password"]


def app_debug(message: str, meta: dict | None = None) -> None:
    if not APP_LAUNCHER_DEBUG:
        return

    safe_meta = _sanitize(meta or {})
    line = f"[APP-LAUNCHER] {message}"

    if safe_meta:
        line = f"{line} {json.dumps(safe_meta, ensure_ascii=False)}"

    print(line)

    try:
        from app.core.log_bus import add_log

        add_log(f"APP-LAUNCHER: {message}", meta=safe_meta)
    except Exception:
        pass


def app_debug_step(step: str, meta: dict | None = None) -> None:
    app_debug(step, meta)


def _sanitize(value: Any, key: str = "") -> Any:
    lowered_key = key.lower()

    if any(marker in lowered_key for marker in SECRET_KEY_MARKERS):
        return "***"

    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(item_value, str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_sanitize(item, key) for item in list(value)[:MAX_LIST_ITEMS]]

    if isinstance(value, str):
        if key.lower() == "target_id" and (value.startswith("shortcut:") or value.startswith("exe:")):
            prefix, _, raw_path = value.partition(":")
            return f"{prefix}:{os.path.basename(raw_path)}"

        value = _redact_paths(value)

        if len(value) > MAX_STRING_LENGTH:
            return f"{value[:MAX_STRING_LENGTH]}..."

        return value

    return value


def _redact_paths(value: str) -> str:
    return re.sub(
        r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*([^\\/:*?\"<>|\r\n]+)",
        r"\1",
        value,
    )
