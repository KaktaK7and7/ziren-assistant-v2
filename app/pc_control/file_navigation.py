from __future__ import annotations

import os
import subprocess
from pathlib import Path


BLOCKED_OPEN_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".cpl",
    ".exe",
    ".hta",
    ".js",
    ".jse",
    ".lnk",
    ".msi",
    ".msp",
    ".ps1",
    ".reg",
    ".scr",
    ".vbe",
    ".vbs",
    ".wsf",
    ".wsh",
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


def open_safe_file(path: Path) -> None:
    _require_windows()

    if not path.exists() or not path.is_file():
        raise FileNavigationError("Файл больше не существует")

    if path.suffix.lower() in BLOCKED_OPEN_EXTENSIONS:
        raise FileNavigationError(
            "Последний файл может запускать программу или системную команду. "
            "Я могу показать его в папке, но не буду запускать голосом."
        )

    os.startfile(str(path))  # type: ignore[attr-defined]
