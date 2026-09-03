from __future__ import annotations

import json
import sys
from pathlib import Path


def _self_test() -> int:
    checks: dict[str, object] = {}
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401
        import torch  # noqa: F401
        import vosk  # noqa: F401
        import silero  # noqa: F401
        import httpx  # noqa: F401
        import PIL  # noqa: F401
        import pycaw  # noqa: F401
        import comtypes  # noqa: F401
        import uiautomation  # noqa: F401
        import psutil  # noqa: F401
        checks["runtime_imports"] = True
    except Exception as error:
        checks["runtime_imports"] = False
        checks["import_error"] = f"{type(error).__name__}: {error}"

    try:
        from app.config.release_paths import validate_vosk_model_path

        model = validate_vosk_model_path()
        checks["vosk_model"] = True
        checks["vosk_model_path"] = str(Path(model))
    except Exception as error:
        checks["vosk_model"] = False
        checks["vosk_error"] = f"{type(error).__name__}: {error}"

    ok = bool(checks.get("runtime_imports")) and bool(checks.get("vosk_model"))
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False))
    return 0 if ok else 2


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _self_test()

    from app.main import main as run_assistant

    run_assistant()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
