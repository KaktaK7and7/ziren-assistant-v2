from __future__ import annotations

import ctypes
import os
import subprocess
import uuid
from ctypes import wintypes
from pathlib import Path


SAFE_OPEN_EXTENSIONS = {
    ".csv", ".doc", ".docx", ".epub", ".json", ".log", ".md", ".ods",
    ".odt", ".pdf", ".ppt", ".pptx", ".rtf", ".txt", ".xls", ".xlsx",
    ".xml", ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg",
    ".tif", ".tiff", ".webp", ".aac", ".avi", ".flac", ".m4a", ".mkv",
    ".mov", ".mp3", ".mp4", ".ogg", ".opus", ".wav", ".webm", ".7z",
    ".rar", ".tar", ".zip", ".3ds", ".blend", ".dxf", ".fbx", ".obj",
    ".psd", ".stl",
}

PARTIAL_DOWNLOAD_EXTENSIONS = {
    ".crdownload",
    ".download",
    ".part",
    ".partial",
    ".tmp",
}

KNOWN_FOLDER_IDS = {
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_text(cls, value: str) -> "GUID":
        parsed = uuid.UUID(value)
        tail = (ctypes.c_ubyte * 8)(*parsed.bytes[8:])
        return cls(parsed.time_low, parsed.time_mid, parsed.time_hi_version, tail)


class FileNavigationError(RuntimeError):
    pass


def _require_windows() -> None:
    if os.name != "nt":
        raise FileNavigationError("Навигация по файлам доступна только в Windows")


def user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def _fallback_known_folders() -> dict[str, Path]:
    home = user_home()
    return {
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "pictures": home / "Pictures",
        "desktop": home / "Desktop",
        "music": home / "Music",
        "videos": home / "Videos",
    }


def _known_folder_path(folder_guid: str) -> Path:
    _require_windows()
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    guid = GUID.from_text(folder_guid)
    path_pointer = ctypes.c_void_p()

    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(guid),
        0,
        None,
        ctypes.byref(path_pointer),
    )
    if result != 0 or not path_pointer.value:
        raise FileNavigationError("Windows не смогла определить системную папку")

    try:
        value = ctypes.wstring_at(path_pointer.value)
    finally:
        ole32.CoTaskMemFree(path_pointer)

    if not value:
        raise FileNavigationError("Windows вернула пустой путь системной папки")
    return Path(value)


def known_folders() -> dict[str, Path]:
    fallback = _fallback_known_folders()
    if os.name != "nt":
        return fallback

    resolved: dict[str, Path] = {}
    for folder_id, guid in KNOWN_FOLDER_IDS.items():
        try:
            resolved[folder_id] = _known_folder_path(guid)
        except (FileNavigationError, OSError, AttributeError):
            # Older/custom Windows shells can fail one Known Folder lookup.
            # Keep a deterministic user-profile fallback for that folder only.
            resolved[folder_id] = fallback[folder_id]
    return resolved


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
