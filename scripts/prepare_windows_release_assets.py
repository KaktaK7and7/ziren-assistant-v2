from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


VOSK_MODEL_NAME = "vosk-model-small-ru-0.22"
VOSK_MODEL_URL = (
    "https://alphacephei.com/vosk/models/"
    "vosk-model-small-ru-0.22.zip"
)
VOSK_MODEL_SHA256 = "961d5ff98a17f4aa6de69864d0aa71fa5bac682301d2b5d17a3f24c5c99a46d4"
VOSK_ARCHIVE_MAX_BYTES = 60 * 1024 * 1024
VOSK_EXTRACTED_MAX_BYTES = 150 * 1024 * 1024
DEFAULT_OUTPUT_ROOT = Path("build") / "release-assets"


class ReleaseAssetError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path) -> None:
    if not path.is_file():
        raise ReleaseAssetError(f"Vosk archive not found: {path}")
    size = path.stat().st_size
    if size <= 0 or size > VOSK_ARCHIVE_MAX_BYTES:
        raise ReleaseAssetError(f"Unexpected Vosk archive size: {size} bytes")
    actual = sha256_file(path)
    if actual != VOSK_MODEL_SHA256:
        raise ReleaseAssetError(
            "Vosk archive SHA-256 mismatch: "
            f"expected {VOSK_MODEL_SHA256}, got {actual}"
        )


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    total_uncompressed = 0

    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename.replace("\\", "/")
            relative = PurePosixPath(name)
            if (
                not name
                or relative.is_absolute()
                or ".." in relative.parts
                or any(part.endswith(":") for part in relative.parts)
                or _is_symlink(info)
            ):
                raise ReleaseAssetError(f"Unsafe ZIP entry: {info.filename}")

            total_uncompressed += max(0, int(info.file_size))
            if total_uncompressed > VOSK_EXTRACTED_MAX_BYTES:
                raise ReleaseAssetError("Vosk archive expands beyond the release limit")

            target = destination.joinpath(*relative.parts)
            resolved_target = target.resolve()
            try:
                resolved_target.relative_to(root)
            except ValueError as error:
                raise ReleaseAssetError(
                    f"ZIP entry escapes destination: {info.filename}"
                ) from error

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def download_archive(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        VOSK_MODEL_URL,
        headers={"User-Agent": "Ziren-Release-Builder/1.0"},
    )
    written = 0
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                announced = int(content_length)
            except ValueError:
                announced = 0
            if announced > VOSK_ARCHIVE_MAX_BYTES:
                raise ReleaseAssetError(
                    f"Vosk download is unexpectedly large: {announced} bytes"
                )

        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > VOSK_ARCHIVE_MAX_BYTES:
                raise ReleaseAssetError("Vosk download exceeded the release size limit")
            output.write(chunk)

    if written <= 0:
        raise ReleaseAssetError("Vosk download returned an empty archive")


def prepare_vosk_model(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    model_zip: Path | None = None,
) -> Path:
    output_root = output_root.resolve()
    final_model = output_root / VOSK_MODEL_NAME

    if final_model.is_dir() and all(
        (final_model / marker).exists() for marker in ("am", "conf", "graph")
    ):
        return final_model

    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ziren-vosk-") as temporary:
        temp_root = Path(temporary)
        archive = temp_root / f"{VOSK_MODEL_NAME}.zip"
        if model_zip is None:
            download_archive(archive)
        else:
            shutil.copy2(model_zip.resolve(), archive)

        verify_archive(archive)
        extract_root = temp_root / "extract"
        safe_extract_zip(archive, extract_root)
        extracted_model = extract_root / VOSK_MODEL_NAME
        if not extracted_model.is_dir():
            raise ReleaseAssetError(
                f"Archive does not contain expected folder: {VOSK_MODEL_NAME}"
            )
        for marker in ("am", "conf", "graph"):
            if not (extracted_model / marker).exists():
                raise ReleaseAssetError(
                    f"Vosk model is incomplete after extraction: missing {marker}"
                )

        staging = output_root / f".{VOSK_MODEL_NAME}.staging"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(extracted_model, staging)
        if final_model.exists():
            shutil.rmtree(final_model)
        os.replace(staging, final_model)

    return final_model


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare verified assets for the Ziren Windows release build."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory that receives the verified model folder.",
    )
    parser.add_argument(
        "--model-zip",
        type=Path,
        help="Use an already downloaded Vosk ZIP instead of the network.",
    )
    args = parser.parse_args()

    model = prepare_vosk_model(args.output_root, model_zip=args.model_zip)
    print(model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
