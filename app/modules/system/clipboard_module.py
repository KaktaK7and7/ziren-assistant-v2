from __future__ import annotations

import re

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


class SystemClipboardModule(AssistantModule):
    feature_id = "system.clipboard"
    display_name = "Буфер обмена"
    plan = Plan.FREE
    default_trigger_groups = {
        "clipboard.read": {
            "display_name": "Прочитать текст из буфера",
            "triggers": READ_TRIGGERS,
        },
        "clipboard.write": {
            "display_name": "Записать текст в буфер",
            "triggers": COPY_TEXT_PREFIXES,
        },
    }

    def can_handle(self, text: str) -> bool:
        normalized = self._normalize(text)
        return (
            any(trigger in normalized for trigger in READ_TRIGGERS)
            or self._extract_copy_text(text) is not None
        )

    def handle(self, text: str) -> ModuleResponse:
        normalized = self._normalize(text)

        if any(trigger in normalized for trigger in READ_TRIGGERS):
            try:
                value = read_text().strip()
            except ClipboardError as error:
                return ModuleResponse(text=str(error))

            if len(value) > MAX_SPOKEN_CLIPBOARD_LENGTH:
                return ModuleResponse(
                    text=(
                        "В буфере длинный текст. Первые символы: "
                        f"{value[:MAX_SPOKEN_CLIPBOARD_LENGTH]}"
                    )
                )
            return ModuleResponse(text=f"В буфере: {value}")

        value = self._extract_copy_text(text)

        if value is None:
            return ModuleResponse(text="Не поняла команду буфера обмена.")

        if not value:
            return ModuleResponse(text="Скажи, какой текст скопировать.")

        try:
            write_text(value)
        except ClipboardError as error:
            return ModuleResponse(text=f"Не смогла скопировать текст: {error}")

        return ModuleResponse(text="Скопировала текст в буфер обмена.")

    def _normalize(self, text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())

    def _extract_copy_text(self, text: str) -> str | None:
        source = " ".join(str(text or "").split()).strip()
        normalized = self._normalize(source)

        for prefix in sorted(COPY_TEXT_PREFIXES, key=len, reverse=True):
            normalized_prefix = self._normalize(prefix)
            if not re.match(rf"^{re.escape(normalized_prefix)}(?:\s|$)", normalized):
                continue

            source_words = source.split()
            prefix_words = prefix.split()
            return " ".join(source_words[len(prefix_words):]).strip(" :-,")

        return None
