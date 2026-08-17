from __future__ import annotations

import re
from typing import Any

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.clipboard import ClipboardError, read_text, write_text


COPY_TEXT_PREFIXES = [
    "скопируй текст",
    "положи в буфер",
    "запиши в буфер",
]
READ_TRIGGERS = [
    "что скопировано",
    "что в буфере",
    "прочитай буфер обмена",
]
MAX_SPOKEN_CLIPBOARD_LENGTH = 500
MAX_CLIPBOARD_WRITE_LENGTH = 10_000


class SystemClipboardModule(AssistantModule):
    feature_id = "system.clipboard"
    display_name = "Буфер обмена"
    plan = Plan.FREE
    default_trigger_groups = {
        "clipboard.read": {
            "display_name": "Прочитать текст из буфера",
            "triggers": READ_TRIGGERS,
            "argument_hint": "Без аргументов. Читает только текстовое содержимое буфера обмена.",
        },
        "clipboard.write": {
            "display_name": "Записать текст в буфер",
            "triggers": COPY_TEXT_PREFIXES,
            "argument_hint": "arguments.text — текст, который нужно положить в буфер обмена.",
        },
    }

    def can_handle(self, text: str) -> bool:
        normalized = self._normalize(text)
        return self._matches_read(normalized) or self._extract_copy_text(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        normalized = self._normalize(text)

        if self._matches_read(normalized):
            return self._read()

        value = self._extract_copy_text(text)
        if value is None:
            return ModuleResponse(text="Не поняла команду буфера обмена.")
        return self._write(value)

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id == "clipboard.read":
            return self._read()
        if action_id == "clipboard.write":
            return self._write(str((arguments or {}).get("text") or "").strip())
        return None

    def _read(self) -> ModuleResponse:
        try:
            value = read_text().strip()
        except ClipboardError as error:
            return ModuleResponse(text=str(error))

        if not value:
            return ModuleResponse(text="Буфер обмена пуст.")
        if len(value) > MAX_SPOKEN_CLIPBOARD_LENGTH:
            return ModuleResponse(
                text=(
                    "В буфере длинный текст. Первые символы: "
                    f"{value[:MAX_SPOKEN_CLIPBOARD_LENGTH]}"
                )
            )
        return ModuleResponse(text=f"В буфере: {value}")

    def _write(self, value: str) -> ModuleResponse:
        if not value:
            return ModuleResponse(text="Скажи, какой текст скопировать.")
        if len(value) > MAX_CLIPBOARD_WRITE_LENGTH:
            return ModuleResponse(text="Текст слишком длинный для одной голосовой команды.")

        try:
            write_text(value)
        except ClipboardError as error:
            return ModuleResponse(text=f"Не смогла скопировать текст: {error}")

        return ModuleResponse(text="Скопировала текст в буфер обмена.")

    def _matches_read(self, normalized: str) -> bool:
        for trigger in self.get_action_triggers("clipboard.read"):
            needle = self._normalize(trigger)
            if needle and re.search(rf"\b{re.escape(needle)}\b", normalized):
                return True
        return False

    def _normalize(self, text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())

    def _extract_copy_text(self, text: str) -> str | None:
        source = " ".join(str(text or "").split()).strip()
        normalized = self._normalize(source)

        for prefix in sorted(
            self.get_action_triggers("clipboard.write"),
            key=len,
            reverse=True,
        ):
            normalized_prefix = self._normalize(prefix)
            if not normalized_prefix:
                continue
            if not re.match(rf"^{re.escape(normalized_prefix)}(?:\s|$)", normalized):
                continue

            source_words = source.split()
            prefix_words = prefix.split()
            return " ".join(source_words[len(prefix_words):]).strip(" :-,")

        return None
