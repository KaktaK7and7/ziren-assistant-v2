from __future__ import annotations

import os


SETTINGS_URIS = {
    "system": "ms-settings:system",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth",
    "network": "ms-settings:network-status",
    "wifi": "ms-settings:network-wifi",
    "apps": "ms-settings:appsfeatures",
    "storage": "ms-settings:storagesense",
    "power": "ms-settings:powersleep",
    "notifications": "ms-settings:notifications",
    "microphone": "ms-settings:privacy-microphone",
    "windows_update": "ms-settings:windowsupdate",
}


def open_settings(section: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Настройки Windows доступны только в Windows")
    uri = SETTINGS_URIS.get(section)
    if not uri:
        raise RuntimeError("Неизвестный раздел настроек Windows")
    os.startfile(uri)  # type: ignore[attr-defined]
