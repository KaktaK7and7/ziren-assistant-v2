from __future__ import annotations

import os
from pathlib import Path


VOSK_MODEL_ENV = "ZIREN_VOSK_MODEL_PATH"
VOSK_MODEL_DIRNAME = "vosk-model-small-ru-0.22"


def get_vosk_model_path() -> Path:
    """Resolve the Vosk model used by both source and packaged builds.

    Release packaging supplies an absolute path through ZIREN_VOSK_MODEL_PATH.
    Source/dev checkouts keep the historical repository-local fallback.
    """
    configured = os.getenv(VOSK_MODEL_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    repository_root = Path(__file__).resolve().parents[2]
    return repository_root / "models" / "vosk" / VOSK_MODEL_DIRNAME


def validate_vosk_model_path(path: Path | None = None) -> Path:
    resolved = (path or get_vosk_model_path()).resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(
            "Vosk model is missing. Reinstall Ziren or restore the bundled voice model: "
            f"{resolved}"
        )

    required_markers = (
        resolved / "am",
        resolved / "conf",
        resolved / "graph",
    )
    missing = [marker.name for marker in required_markers if not marker.exists()]
    if missing:
        raise FileNotFoundError(
            "Vosk model is incomplete; missing: " + ", ".join(missing)
        )

    return resolved
