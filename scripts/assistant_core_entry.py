from __future__ import annotations

import os
import sys
from pathlib import Path


VOSK_MODEL_DIRNAME = "vosk-model-small-ru-0.22"
SILERO_MODEL_FILENAME = "v5_5_ru.pt"
SELF_TEST_ENV = "ZIREN_PACKAGE_SELF_TEST"


def _bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def _embedded_vosk_model() -> Path:
    return _bundle_root() / "models" / "vosk" / VOSK_MODEL_DIRNAME


def _embedded_silero_model() -> Path:
    return _bundle_root() / "models" / "silero" / SILERO_MODEL_FILENAME


def _configure_embedded_release_assets() -> tuple[Path, Path]:
    vosk_model = _embedded_vosk_model()
    required = (vosk_model / "am", vosk_model / "conf", vosk_model / "graph")
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Packaged Vosk model is incomplete: " + ", ".join(missing)
        )

    silero_model = _embedded_silero_model()
    if not silero_model.is_file() or silero_model.stat().st_size < 1_000_000:
        raise RuntimeError(f"Packaged Silero model is missing or invalid: {silero_model}")

    os.environ["ZIREN_VOSK_MODEL_PATH"] = str(vosk_model)
    os.environ["ZIREN_SILERO_MODEL_PATH"] = str(silero_model)
    return vosk_model, silero_model


def package_self_test() -> int:
    """Validate the frozen bundle without opening audio devices or the network."""
    vosk_model, _ = _configure_embedded_release_assets()

    # Import the complete runtime so hidden-import/package problems fail in CI.
    from app import main as runtime_main

    runtime_vosk = Path(runtime_main.VOSK_MODEL_PATH).resolve()
    if runtime_vosk != vosk_model.resolve():
        raise RuntimeError(
            "Runtime Vosk path does not point at the embedded model: "
            f"runtime={runtime_vosk}, embedded={vosk_model.resolve()}"
        )

    # Actually load the recognizer model so a corrupt/incompatible packaged
    # model fails before the installer is published. No microphone is opened.
    import vosk

    vosk_model_instance = vosk.Model(str(runtime_vosk))
    if vosk_model_instance is None:
        raise RuntimeError("Packaged Vosk model did not load")

    # Load and warm the bundled TTS model. This deliberately does not call
    # speak(), so CI never needs a physical audio output device.
    from app.voice.audio_state import AudioState
    from app.voice.tts_silero import SileroTTS

    tts = SileroTTS(AudioState())
    tts.load()
    if tts.model is None:
        raise RuntimeError("Packaged Silero model did not load")

    return 0


def main() -> None:
    _configure_embedded_release_assets()

    if os.getenv(SELF_TEST_ENV, "").strip() == "1":
        raise SystemExit(package_self_test())

    from app.main import main as run_assistant

    run_assistant()


if __name__ == "__main__":
    main()
