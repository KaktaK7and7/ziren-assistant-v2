from __future__ import annotations

import os
import subprocess
from pathlib import Path


SAFE_OPEN_EXTENSIONS = {
    # Documents and plain data.
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".json",
    ".log",
    ".md",
    ".ods",
    ".odt",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
    # Images.
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
    # Audio and video.
    ".aac",
    ".avi",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    # Archives are opened by the user's configured archive application.
    ".7z",
    ".rar",
    ".tar",
    ".zip",
    # Common creative / CAD / 3D project files.
    ".3ds",
    ".blend",
    ".dxf",
    ".fbx",
    ".obj",
    ".psd",
    ".stl",
}

PARTIAL_DOWNLOAD_EXTENSIONS = {
    ".crdownload",
    ".download",
    ".part",
    ".partial",
    ".tmp",
}


class FileNavigationError(RuntimeError):
    pass


def _require_windows() -> None:
    if os.name != "nt":
        raise FileNavigationError("Навигация по файлам доступна только в Windows")


def user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def known_folders() -> dict[str, Path]:
    home = user_home()
    return {
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "pictures": home / "Pictures",
        "desktop": home / "Desktop",
        "music": home / "Music",
        "videos": home / "Videos",
    }


def resolve_known_folder(folder_id: str) -> Path:
    path = known_folders().get(str(folder_id or "").strip().lower())

    if path is None:
        raise FileNavigationError("Неизвестная системная папка")

    if not path.exists() or not path.is_dir():
        raise FileNavigationError(f"Папка {path.name} не найдена")

    return path


def open_folder(folder_id: str) -> Path:
    _require_windows()
    path = resolve_known_folder(folder_id)
    os.startfile(str(path))  # type: ignore[attr-defined]
    return path


def open_explorer() -> None:
    _require_windows()
    subprocess.Popen(
        ["explorer.exe"],
        close_fds=True,
    )


def latest_download() -> Path:
    downloads = resolve_known_folder("downloads")
    candidates: list[Path] = []

    try:
        for item in downloads.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() in PARTIAL_DOWNLOAD_EXTENSIONS:
                continue
            candidates.append(item)
    except OSError as error:
        raise FileNavigationError("Не удалось прочитать папку загрузок") from error

    if not candidates:
        raise FileNavigationError("В загрузках пока нет файлов")

    try:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    except OSError as error:
        raise FileNavigationError("Не удалось определить последний скачанный файл") from error


def reveal_file(path: Path) -> None:
    _require_windows()

    if not path.exists() or not path.is_file():
        raise FileNavigationError("Файл больше не существует")

    subprocess.Popen(
        ["explorer.exe", f"/select,{path}"],
        close_fds=True,
    )


def is_safe_to_open(path: Path) -> bool:
    return path.suffix.lower() in SAFE_OPEN_EXTENSIONS


def open_safe_file(path: Path) -> None:
    _require_windows()

    if not path.exists() or not path.is_file():
        raise FileNavigationError("Файл больше не существует")

    if not is_safe_to_open(path):
        raise FileNavigationError(
            "Я не запускаю этот тип скачанного файла голосом. "
            "Могу показать его в Проводнике, чтобы решение осталось за тобой."
        )

    os.startfile(str(path))  # type: ignore[attr-defined]
