from __future__ import annotations

import json
import sys

from app.config.release_paths import validate_vosk_model_path


SELF_TEST_FLAG = "--release-self-test"


def run_release_self_test() -> int:
    """Validate packaged prerequisites without opening audio or executing actions."""
    model_path = validate_vosk_model_path()

    # Import the actual application graph so a packaged build fails here if a
    # required runtime module or hidden import was missed by the bundler.
    from app import main as assistant_main

    if not callable(getattr(assistant_main, "main", None)):
        raise RuntimeError("Ziren Core entry point is unavailable")

    print(
        json.dumps(
            {
                "ok": True,
                "component": "ziren-assistant-core",
                "self_test": "release",
                "vosk_model": model_path.name,
            },
            ensure_ascii=False,
        )
    )
    return 0


def run() -> int:
    if SELF_TEST_FLAG in sys.argv[1:]:
        return run_release_self_test()

    model_path = validate_vosk_model_path()
    from app import main as assistant_main

    # Existing Core logic keeps its source-checkout default. The release
    # wrapper replaces only the model location with the verified bundled path.
    assistant_main.VOSK_MODEL_PATH = model_path
    assistant_main.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
