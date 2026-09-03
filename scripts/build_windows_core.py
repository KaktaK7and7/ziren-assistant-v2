from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from prepare_windows_release_assets import prepare_vosk_model


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST_DIR = PROJECT_ROOT / "build" / "windows-core"
DEFAULT_WORK_DIR = PROJECT_ROOT / "build" / "pyinstaller-work"
DEFAULT_SPEC_DIR = PROJECT_ROOT / "build" / "pyinstaller-spec"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def build_core(*, clean: bool = False, skip_assets: bool = False) -> Path:
    dist_dir = DEFAULT_DIST_DIR.resolve()
    work_dir = DEFAULT_WORK_DIR.resolve()
    spec_dir = DEFAULT_SPEC_DIR.resolve()

    if clean:
        for path in (dist_dir, work_dir, spec_dir):
            if path.exists():
                shutil.rmtree(path)

    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    if not skip_assets:
        model_dir = prepare_vosk_model(PROJECT_ROOT / "build" / "release-assets")
        print(f"Verified Vosk model: {model_dir}")

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "assistant-core",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        # Packages with dynamic imports, data files or native extensions that
        # PyInstaller cannot reliably infer from the top-level application graph.
        "--collect-all",
        "silero",
        "--collect-all",
        "vosk",
        "--collect-all",
        "pycaw",
        "--collect-all",
        "comtypes",
        "--collect-all",
        "Levenshtein",
        "--collect-all",
        "rapidfuzz",
        "--hidden-import",
        "sounddevice",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        str(PROJECT_ROOT / "app" / "release_entry.py"),
    ]
    _run(command, env=env)

    binary = dist_dir / "assistant-core.exe"
    if not binary.is_file() or binary.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"Packaged Core binary is missing or unexpectedly small: {binary}")

    print(binary)
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the standalone Windows Ziren Core executable.")
    parser.add_argument("--clean", action="store_true", help="Remove previous PyInstaller outputs first.")
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Skip Vosk download/verification (useful for isolated binary-only debugging).",
    )
    args = parser.parse_args()
    build_core(clean=args.clean, skip_assets=args.skip_assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
