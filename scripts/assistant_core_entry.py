from __future__ import annotations

import os
import sys
from pathlib import Path


VOSK_MODEL_DIRNAME = "vosk-model-small-ru-0.22"
SELF_TEST_ENV = "ZIREN_PACKAGE_SELF_TEST"


def _bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def _embedded_vosk_model() -> Path:
    return _bundle_root() / "models" / "vosk" / VOSK_MODEL_DIRNAME


def _validate_embedded_release_assets() -> Path:
    model = _embedded_vosk_model()
    required = (model / "am", model / "conf", model / "graph")
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Packaged Vosk model is incomplete: " + ", ".join(missing)
        )
    return model


def package_self_test() -> int:
    """Validate the frozen bundle without opening audio devices or the network."""
    model = _validate_embedded_release_assets()
    os.environ["ZIREN_VOSK_MODEL_PATH"] = str(model)

    # Import the runtime entrypoint so PyInstaller hidden-import/package problems
    # fail in CI before the executable is shipped. Do not call main(): that would
    # open the microphone and require a real desktop session.
    from app import main as runtime_main  # noqa: F401

    return 0


def main() -> None:
    model = _validate_embedded_release_assets()
    os.environ.setdefault("ZIREN_VOSK_MODEL_PATH", str(model))

    if os.getenv(SELF_TEST_ENV, "").strip() == "1":
        raise SystemExit(package_self_test())

    from app.main import main as run_assistant

    run_assistant()


if __name__ == "__main__":
    main()
