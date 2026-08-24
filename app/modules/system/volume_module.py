import re
from typing import Any

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


VOLUME_VERIFY_TOLERANCE_PERCENT = 2


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
                self._set_mute(volume, True)
                return ModuleResponse(text="Звук выключен.")

            if action_id == "volume.unmute":
                self._set_mute(volume, False)
                return ModuleResponse(text="Звук включён.")

            if action_id == "volume.set":
                if percent is None:
                    return ModuleResponse(text="Укажи громкость от 0 до 100 процентов.")
                actual = self._set_volume_percent(volume, percent)
                return ModuleResponse(
                    text=f"Громкость установлена на {actual} процентов."
                )

            current = self._get_current_percent(volume)
            if action_id == "volume.up":
                requested = min(100, current + 10)
                actual = self._set_volume_percent(volume, requested)
                return ModuleResponse(
                    text=f"Сделала громче. Сейчас {actual} процентов."
                )

            if action_id == "volume.down":
                requested = max(0, current - 10)
                actual = self._set_volume_percent(volume, requested)
                return ModuleResponse(
                    text=f"Сделала тише. Сейчас {actual} процентов."
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
        if speakers is None:
            raise RuntimeError("Windows не вернула активное устройство вывода звука")
        endpoint = self._resolve_endpoint(speakers)

        interface = endpoint.Activate(
            IAudioEndpointVolume._iid_,
            CLSCTX_ALL,
            None,
        )
        if interface is None:
            raise RuntimeError("Не удалось открыть системный audio endpoint")

        volume = interface.QueryInterface(IAudioEndpointVolume)
        if volume is None:
            raise RuntimeError("Не удалось получить управление системной громкостью")
        return volume

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
        scalar = float(volume.GetMasterVolumeLevelScalar())
        if not 0.0 <= scalar <= 1.0:
            raise RuntimeError("Windows вернула некорректный уровень громкости")
        return round(scalar * 100)

    def _set_mute(self, volume, muted: bool) -> None:
        expected = 1 if muted else 0
        volume.SetMute(expected, None)
        actual = int(volume.GetMute())
        if actual != expected:
            state = "mute" if muted else "unmute"
            raise RuntimeError(f"Windows не подтвердила состояние {state}")

    def _set_volume_percent(self, volume, percent: int) -> int:
        requested = max(0, min(100, percent))
        # Setting a non-zero volume should make sound audible. At zero we keep
        # the endpoint unmuted as well so future volume-up behaves predictably.
        volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(requested / 100, None)
        actual = self._get_current_percent(volume)
        if abs(actual - requested) > VOLUME_VERIFY_TOLERANCE_PERCENT:
            raise RuntimeError(
                f"Windows не подтвердила громкость {requested} процентов; сейчас {actual}"
            )
        if int(volume.GetMute()) != 0:
            raise RuntimeError("Windows оставила системный звук в mute")
        return actual

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
