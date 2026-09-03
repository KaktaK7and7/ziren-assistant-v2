from __future__ import annotations

import json
import sys
from pathlib import Path


def _self_test() -> int:
    checks: dict[str, object] = {}

    try:
        # Native/runtime imports that have historically been easy to miss in a
        # frozen build. Import them explicitly so packaging regressions fail
        # before an installer reaches a user machine.
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
        import rapidfuzz  # noqa: F401
        from Levenshtein import distance as levenshtein_distance

        if levenshtein_distance("ziren", "ziren") != 0:
            raise RuntimeError("Levenshtein native extension returned an invalid result")
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

    try:
        # Import the actual application graph. This is deliberately stricter
        # than checking individual dependencies: a green release artifact must
        # prove that the same graph used on startup is importable when frozen.
        import app.main as assistant_main

        if not callable(getattr(assistant_main, "main", None)):
            raise RuntimeError("Ziren Core entry point is unavailable")
        checks["application_graph"] = True
    except Exception as error:
        checks["application_graph"] = False
        checks["application_error"] = f"{type(error).__name__}: {error}"

    ok = all(
        bool(checks.get(key))
        for key in ("runtime_imports", "vosk_model", "application_graph")
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False))
    return 0 if ok else 2


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _self_test()

    from app.config.release_paths import validate_vosk_model_path

    # Validate the bundled model before audio initialization so a damaged
    # install fails with a precise reinstall message rather than inside Vosk.
    validate_vosk_model_path()

    from app.main import main as run_assistant

    run_assistant()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
