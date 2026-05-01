import json
import os
from pathlib import Path
from typing import Any


APP_DIR = Path(os.getenv("APPDATA", ".")) / "ZirenAssistantV2"
SESSION_FILE = APP_DIR / "session.json"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    ensure_app_dir()

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_session() -> dict:
    return read_json(SESSION_FILE, default={})


def save_session(data: dict) -> None:
    write_json(SESSION_FILE, data)


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()