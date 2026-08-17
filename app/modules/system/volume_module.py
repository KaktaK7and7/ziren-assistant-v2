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
            "argument_hint": "Без аргументов. Увеличивает системную громкость на 10 процентов.",
        },
        "volume.down": {
            "display_name": "Уменьшить громкость",
            "triggers": ["тише", "сделай тише"],
            "argument_hint": "Без аргументов. Уменьшает системную громкость на 10 процентов.",
        },
        "volume.mute": {
            "display_name": "Выключить звук",
            "triggers": ["выключи звук", "убери звук"],
            "argument_hint": "Без аргументов. Включает mute системного вывода.",
        },
        "volume.unmute": {
            "display_name": "Включить звук",
            "triggers": ["включи звук", "верни звук"],
            "argument_hint": "Без аргументов. Снимает mute системного вывода.",
        },
        "volume.set": {
            "display_name": "Установить громкость",
            "triggers": ["поставь громкость", "сделай громкость", "громкость на"],
            "argument_hint": "arguments.percent — целое значение системной громкости от 0 до 100.",
        },
    }

    def can_handle(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(
            self._matches_action(normalized, action_id)
            for action_id in self.default_trigger_groups
        )

    def handle(self, text: str) -> ModuleResponse:
        normalized = self._normalize(text)
        action_id = self._find_action(normalized)
        if action_id is None:
            return ModuleResponse(text="Не поняла команду громкости.")

        percent = self._extract_percent(normalized) if action_id == "volume.set" else None
        return self._execute(action_id, percent)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id not in self.default_trigger_groups:
            return None
        percent = None
        if action_id == "volume.set":
            percent = self._coerce_percent((arguments or {}).get("percent"))
        return self._execute(action_id, percent)

    def _execute(self, action_id: str, percent: int | None = None) -> ModuleResponse:
        try:
            volume = self._get_volume()

            if action_id == "volume.mute":
                volume.SetMute(1, None)
                return ModuleResponse(text="Звук выключен.")

            if action_id == "volume.unmute":
                volume.SetMute(0, None)
                return ModuleResponse(text="Звук включён.")

            if action_id == "volume.set":
                if percent is None:
                    return ModuleResponse(text="Укажи громкость от 0 до 100 процентов.")
                self._set_volume_percent(volume, percent)
                return ModuleResponse(
                    text=f"Громкость установлена на {percent} процентов."
                )

            current = self._get_current_percent(volume)
            if action_id == "volume.up":
                new_value = min(100, current + 10)
                self._set_volume_percent(volume, new_value)
                return ModuleResponse(
                    text=f"Сделала громче. Сейчас {new_value} процентов."
                )

            if action_id == "volume.down":
                new_value = max(0, current - 10)
                self._set_volume_percent(volume, new_value)
                return ModuleResponse(
                    text=f"Сделала тише. Сейчас {new_value} процентов."
                )
        except Exception as error:
            return ModuleResponse(
                text=f"Не смогла изменить громкость. Ошибка: {error}"
            )

        return ModuleResponse(text="Не поняла команду громкости.")

    def _find_action(self, text: str) -> str | None:
        matches: list[tuple[int, str]] = []
        for action_id in self.default_trigger_groups:
            for trigger in self.get_action_triggers(action_id):
                needle = self._normalize(trigger)
                if needle and re.search(rf"\b{re.escape(needle)}\b", text):
                    matches.append((len(needle), action_id))
        return max(matches, key=lambda item: item[0])[1] if matches else None

    def _matches_action(self, text: str, action_id: str) -> bool:
        return any(
            (needle := self._normalize(trigger))
            and re.search(rf"\b{re.escape(needle)}\b", text)
            for trigger in self.get_action_triggers(action_id)
        )

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
            f"Не нашла audio endpoint с Activate(). Тип объекта: {type(speakers)}"
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

    def _coerce_percent(self, value: object) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return None
        if not 0 <= number <= 100:
            return None
        return number

    def _clamp_percent(self, value: int) -> int:
        return max(0, min(100, value))

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())
