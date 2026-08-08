from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MAX_CLIPBOARD_TEXT_LENGTH = 20_000


class ClipboardError(RuntimeError):
    pass


def _require_windows() -> None:
    if os.name != "nt":
        raise ClipboardError("Буфер обмена доступен только в Windows")


def _configure_winapi():
    _require_windows()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    return user32, kernel32


def _open_clipboard(retries: int = 8, delay: float = 0.03) -> None:
    user32, _ = _configure_winapi()

    for _ in range(retries):
        if user32.OpenClipboard(None):
            return
        time.sleep(delay)

    raise ClipboardError("Не удалось открыть буфер обмена")


def read_text() -> str:
    user32, kernel32 = _configure_winapi()
    _open_clipboard()

    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            raise ClipboardError("В буфере обмена сейчас нет текста")

        handle = user32.GetClipboardData(CF_UNICODETEXT)

        if not handle:
            raise ClipboardError("Не удалось прочитать буфер обмена")

        pointer = kernel32.GlobalLock(handle)

        if not pointer:
            raise ClipboardError("Не удалось получить текст из буфера обмена")

        try:
            value = ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    text = str(value or "")

    if not text.strip():
        raise ClipboardError("В буфере обмена пустой текст")

    if len(text) > MAX_CLIPBOARD_TEXT_LENGTH:
        raise ClipboardError("Скопированный текст слишком длинный")

    return text


def write_text(text: str) -> None:
    user32, kernel32 = _configure_winapi()
    value = str(text or "")

    if not value:
        raise ClipboardError("Нет текста для копирования")

    if len(value) > MAX_CLIPBOARD_TEXT_LENGTH:
        raise ClipboardError("Текст слишком длинный для буфера обмена")

    encoded = value.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))

    if not handle:
        raise ClipboardError("Не удалось выделить память для буфера обмена")

    pointer = kernel32.GlobalLock(handle)

    if not pointer:
        kernel32.GlobalFree(handle)
        raise ClipboardError("Не удалось подготовить буфер обмена")

    try:
        ctypes.memmove(pointer, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(handle)

    _open_clipboard()

    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("Не удалось очистить буфер обмена")

        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise ClipboardError("Не удалось записать текст в буфер обмена")

        # Ownership of the handle transfers to Windows after SetClipboardData.
        handle = None
    finally:
        user32.CloseClipboard()

        if handle:
            kernel32.GlobalFree(handle)
