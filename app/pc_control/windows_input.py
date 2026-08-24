from __future__ import annotations

import os
import time
from collections.abc import Iterable


KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
HOTKEY_SETTLE_SECONDS = 0.04

VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
    "win": 0x5B,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

for digit in "0123456789":
    VK[digit] = ord(digit)
for letter in "abcdefghijklmnopqrstuvwxyz":
    VK[letter] = ord(letter.upper())


class WindowsInputError(RuntimeError):
    pass


def _build_input_types(ctypes, wintypes):
    """Build the real Win32 INPUT layout.

    INPUT contains a union of MOUSEINPUT, KEYBDINPUT and HARDWAREINPUT.  It is
    tempting to declare only KEYBDINPUT when we inject keyboard events, but
    that changes sizeof(INPUT) (notably from 40 to 32 bytes on 64-bit Windows).
    SendInput requires cbSize to be exactly sizeof the native INPUT structure
    and returns zero for the truncated layout.
    """

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", INPUT_UNION),
        ]

    return KEYBDINPUT, INPUT


def _require_windows():
    if os.name != "nt":
        raise WindowsInputError("Управление клавиатурой доступно только в Windows")

    import ctypes
    from ctypes import wintypes

    KEYBDINPUT, INPUT = _build_input_types(ctypes, wintypes)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [
        wintypes.UINT,
        ctypes.POINTER(INPUT),
        ctypes.c_int,
    ]
    user32.SendInput.restype = wintypes.UINT

    return ctypes, user32, KEYBDINPUT, INPUT


def _send_keyboard_packet(*, vk_code: int, scan_code: int, flags: int, error_label: str) -> None:
    ctypes, user32, KEYBDINPUT, INPUT = _require_windows()
    packet = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=vk_code,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )

    ctypes.set_last_error(0)
    sent = user32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
    if sent == 1:
        return

    error_code = ctypes.get_last_error()
    suffix = f" (WinError {error_code})" if error_code else ""
    raise WindowsInputError(f"{error_label}{suffix}")


def _send_vk(vk_code: int, key_up: bool = False) -> None:
    _send_keyboard_packet(
        vk_code=vk_code,
        scan_code=0,
        flags=KEYEVENTF_KEYUP if key_up else 0,
        error_label="Windows не приняла ввод с клавиатуры",
    )


def _send_unicode_unit(unit: int, key_up: bool = False) -> None:
    _send_keyboard_packet(
        vk_code=0,
        scan_code=unit,
        flags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0),
        error_label="Windows не приняла текстовый ввод",
    )


def normalize_key_name(value: str) -> str:
    key = str(value or "").strip().lower().replace("ё", "е")
    aliases = {
        "контрол": "ctrl",
        "контроль": "ctrl",
        "control": "ctrl",
        "эскейп": "escape",
        "esc": "escape",
        "пробел": "space",
        "делит": "delete",
        "удалить": "delete",
        "бэкспейс": "backspace",
        "бекспейс": "backspace",
        "стрелка вверх": "up",
        "стрелка вниз": "down",
        "стрелка влево": "left",
        "стрелка вправо": "right",
        "вин": "win",
        "windows": "win",
    }
    return aliases.get(key, key)


def key_code(value: str) -> int:
    normalized = normalize_key_name(value)
    code = VK.get(normalized)

    if code is None:
        raise WindowsInputError(f"Клавиша «{value}» не разрешена")

    return code


def press_key(key: str) -> None:
    code = key_code(key)
    _send_vk(code)
    _send_vk(code, key_up=True)


def send_hotkey(keys: Iterable[str]) -> None:
    normalized = [normalize_key_name(key) for key in keys]

    if not normalized:
        raise WindowsInputError("Пустое сочетание клавиш")

    codes = [key_code(key) for key in normalized]

    try:
        for code in codes:
            _send_vk(code)
            time.sleep(0.01)
    finally:
        for code in reversed(codes):
            try:
                _send_vk(code, key_up=True)
            except Exception:
                pass

    # Windows Shell actions such as virtual-desktop switching are asynchronous.
    # SendInput returning success only proves that the keyboard packets entered
    # the input stream, not that Explorer/VirtualDesktopManager already handled
    # the chord. A tiny settle interval prevents repeated shell hotkeys from
    # collapsing into an unreliable burst while remaining imperceptible for
    # normal user commands.
    time.sleep(HOTKEY_SETTLE_SECONDS)


def type_unicode_text(text: str) -> None:
    value = str(text or "")

    if not value:
        raise WindowsInputError("Нет текста для ввода")

    encoded = value.encode("utf-16-le")

    for index in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[index:index + 2], "little")
        _send_unicode_unit(unit)
        _send_unicode_unit(unit, key_up=True)
