import re
from typing import Any

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


class SystemVolumeModule(AssistantModule):
    feature_id = "system.volume"
    plan = Plan.FREE

    def can_handle(self, text: str) -> bool:
        text = text.strip().lower()

        return any(
            phrase in text
            for phrase in [
                "громче",
                "тише",
                "выключи звук",
                "включи звук",
                "убери звук",
                "верни звук",
                "поставь громкость",
                "сделай громкость",
                "громкость на",
            ]
        )

    def handle(self, text: str) -> ModuleResponse:
        try:
            return self._handle_volume(text)
        except Exception as error:
            return ModuleResponse(text=f"Не смог изменить громкость. Ошибка: {error}")

    def _handle_volume(self, text: str) -> ModuleResponse:
        text = text.strip().lower()
        volume = self._get_volume()

        if "выключи звук" in text or "убери звук" in text:
            volume.SetMute(1, None)
            return ModuleResponse(text="Звук выключен.")

        if "включи звук" in text or "верни звук" in text:
            volume.SetMute(0, None)
            return ModuleResponse(text="Звук включён.")

        percent = self._extract_percent(text)

        if percent is not None:
            self._set_volume_percent(volume, percent)
            return ModuleResponse(text=f"Громкость установлена на {percent} процентов.")

        current = self._get_current_percent(volume)

        if "громче" in text:
            new_value = min(100, current + 10)
            self._set_volume_percent(volume, new_value)
            return ModuleResponse(text=f"Сделал громче. Сейчас {new_value} процентов.")

        if "тише" in text:
            new_value = max(0, current - 10)
            self._set_volume_percent(volume, new_value)
            return ModuleResponse(text=f"Сделал тише. Сейчас {new_value} процентов.")

        return ModuleResponse(text="Не понял команду громкости.")

    def _get_volume(self):
        speakers = AudioUtilities.GetSpeakers()
        endpoint = self._resolve_endpoint(speakers)

        interface = endpoint.Activate(
            IAudioEndpointVolume._iid_,
            CLSCTX_ALL,
            None,
        )

        return interface.QueryInterface(IAudioEndpointVolume)

    def _resolve_endpoint(self, speakers: Any) -> Any:
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

        raise RuntimeError(
            f"Не нашёл audio endpoint с Activate(). Тип объекта: {type(speakers)}"
        )

    def _get_current_percent(self, volume) -> int:
        scalar = volume.GetMasterVolumeLevelScalar()
        return round(float(scalar) * 100)

    def _set_volume_percent(self, volume, percent: int) -> None:
        percent = max(0, min(100, percent))
        volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(percent / 100, None)

    def _extract_percent(self, text: str) -> int | None:
        digit_match = re.search(r"\b(\d{1,3})\b", text)

        if digit_match:
            return self._clamp_percent(int(digit_match.group(1)))

        words = text.lower().replace("ё", "е").split()

        tens = {
            "двадцать": 20,
            "тридцать": 30,
            "сорок": 40,
            "пятьдесят": 50,
            "шестьдесят": 60,
            "семьдесят": 70,
            "восемьдесят": 80,
            "девяносто": 90,
        }

        units = {
            "один": 1,
            "одна": 1,
            "два": 2,
            "две": 2,
            "три": 3,
            "четыре": 4,
            "пять": 5,
            "шесть": 6,
            "семь": 7,
            "восемь": 8,
            "девять": 9,
        }

        singles = {
            "ноль": 0,
            "десять": 10,
            "одиннадцать": 11,
            "двенадцать": 12,
            "тринадцать": 13,
            "четырнадцать": 14,
            "пятнадцать": 15,
            "шестнадцать": 16,
            "семнадцать": 17,
            "восемнадцать": 18,
            "девятнадцать": 19,
            "сто": 100,
            **tens,
            **units,
        }

        # Сначала составные: "двадцать пять", "семьдесят два"
        for index, word in enumerate(words[:-1]):
            next_word = words[index + 1]

            if word in tens and next_word in units:
                return self._clamp_percent(tens[word] + units[next_word])

        # Потом одиночные: "пятьдесят", "десять", "сто"
        for word in words:
            if word in singles:
                return self._clamp_percent(singles[word])

        return None

    def _clamp_percent(self, value: int) -> int:
        return max(0, min(100, value))