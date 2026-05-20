import re
from typing import Any

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


class SystemVolumeModule(AssistantModule):
    feature_id = "system.volume"
    display_name = "Управление громкостью"
    plan = Plan.FREE
    default_trigger_groups = {
        "volume.up": {
            "display_name": "Увеличить громкость",
            "triggers": ["громче", "сделай громче"],
        },
        "volume.down": {
            "display_name": "Уменьшить громкость",
            "triggers": ["тише", "сделай тише"],
        },
        "volume.mute": {
            "display_name": "Выключить звук",
            "triggers": ["выключи звук", "убери звук"],
        },
        "volume.unmute": {
            "display_name": "Включить звук",
            "triggers": ["включи звук", "верни звук"],
        },
        "volume.set": {
            "display_name": "Установить громкость",
            "triggers": ["поставь громкость", "сделай громкость", "громкость на"],
        },
    }

    def can_handle(self, text: str) -> bool:
        text = text.strip().lower()

        return any(trigger in text for trigger in self.get_triggers())

    def handle(self, text: str) -> ModuleResponse:
        try:
            return self._handle_volume(text)
        except Exception as error:
            return ModuleResponse(
                text=f"Не смог изменить громкость. Ошибка: {error}"
            )

    def _handle_volume(self, text: str) -> ModuleResponse:
        text = text.strip().lower()
        volume = self._get_volume()

        if self._matches_action(text, "volume.mute"):
            volume.SetMute(1, None)
            return ModuleResponse(text="Звук выключен.")

        if self._matches_action(text, "volume.unmute"):
            volume.SetMute(0, None)
            return ModuleResponse(text="Звук включён.")

        if self._matches_action(text, "volume.set"):
            percent = self._extract_percent(text)

            if percent is None:
                return ModuleResponse(text="Не понял, какую громкость поставить.")

            self._set_volume_percent(volume, percent)
            return ModuleResponse(
                text=f"Громкость установлена на {percent} процентов."
            )

        current = self._get_current_percent(volume)

        if self._matches_action(text, "volume.up"):
            new_value = min(100, current + 10)
            self._set_volume_percent(volume, new_value)
            return ModuleResponse(
                text=f"Сделал громче. Сейчас {new_value} процентов."
            )

        if self._matches_action(text, "volume.down"):
            new_value = max(0, current - 10)
            self._set_volume_percent(volume, new_value)
            return ModuleResponse(
                text=f"Сделал тише. Сейчас {new_value} процентов."
            )

        return ModuleResponse(text="Не понял команду громкости.")

    def _matches_action(self, text: str, action_id: str) -> bool:
        return any(trigger in text for trigger in self.get_action_triggers(action_id))

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

        for index, word in enumerate(words[:-1]):
            next_word = words[index + 1]

            if word in tens and next_word in units:
                return self._clamp_percent(tens[word] + units[next_word])

        for word in words:
            if word in singles:
                return self._clamp_percent(singles[word])

        return None

    def _clamp_percent(self, value: int) -> int:
        return max(0, min(100, value))
