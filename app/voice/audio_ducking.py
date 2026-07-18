from threading import Lock

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from app.core.log_bus import add_log


_lock = Lock()
_original_volume: float | None = None


def duck_volume(target_percent: int = 25) -> None:
    global _original_volume

    try:
        with _lock:
            volume = _get_volume()
            current = float(volume.GetMasterVolumeLevelScalar())

            if _original_volume is None:
                _original_volume = current

            target = max(0.0, min(1.0, target_percent / 100))
            new_value = min(current, target)
            volume.SetMasterVolumeLevelScalar(new_value, None)
            add_log(
                "audio.ducking.enabled",
                meta={
                    "previous_volume": round(current * 100),
                    "target_volume": round(new_value * 100),
                },
            )
    except Exception as error:
        add_log("audio.ducking.error", level="warn", meta={"error": str(error)})


def restore_volume() -> None:
    global _original_volume

    try:
        with _lock:
            if _original_volume is None:
                return

            volume = _get_volume()
            restore_to = _original_volume
            volume.SetMasterVolumeLevelScalar(restore_to, None)
            _original_volume = None
            add_log(
                "audio.ducking.restored",
                meta={"volume": round(restore_to * 100)},
            )
    except Exception as error:
        add_log("audio.ducking.error", level="warn", meta={"error": str(error)})


def is_ducked() -> bool:
    with _lock:
        return _original_volume is not None


def _get_volume():
    speakers = AudioUtilities.GetSpeakers()
    endpoint = _resolve_endpoint(speakers)
    interface = endpoint.Activate(
        IAudioEndpointVolume._iid_,
        CLSCTX_ALL,
        None,
    )
    return interface.QueryInterface(IAudioEndpointVolume)


def _resolve_endpoint(speakers):
    if hasattr(speakers, "Activate"):
        return speakers

    for attr_name in [
        "Endpoint",
        "endpoint",
        "_endpoint",
        "_dev",
        "dev",
        "Device",
        "device",
    ]:
        endpoint = getattr(speakers, attr_name, None)

        if endpoint is not None and hasattr(endpoint, "Activate"):
            return endpoint

    raise RuntimeError(f"Audio endpoint with Activate() not found: {type(speakers)}")
