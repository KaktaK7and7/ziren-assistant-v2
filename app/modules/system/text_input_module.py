from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import WindowsInputError, type_unicode_text


TEXT_INPUT_PREFIXES = [
    "введи текст",
    "напечатай",
    "напечатай текст",
    "напиши здесь",
    "введи сюда",
]
MAX_TYPED_TEXT_LENGTH = 2_000


class SystemTextInputModule(AssistantModule):
    feature_id = "system.text_input"
    display_name = "Голосовой ввод текста"
    plan = Plan.FREE
    default_trigger_groups = {
        "text.type": {
            "display_name": "Ввести продиктованный текст",
            "triggers": TEXT_INPUT_PREFIXES,
        }
    }

    def can_handle(self, text: str) -> bool:
        return self._extract_text(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        value = self._extract_text(text)

        if value is None:
            return ModuleResponse(text="Не поняла, какой текст ввести.")

        if not value:
            return ModuleResponse(text="После команды продиктуй текст.")

        if len(value) > MAX_TYPED_TEXT_LENGTH:
            return ModuleResponse(text="Этот текст слишком длинный для голосового ввода за один раз.")

        try:
            type_unicode_text(value)
        except WindowsInputError as error:
            return ModuleResponse(text=f"Не смогла ввести текст: {error}")

        return ModuleResponse(text="Напечатала.")

    def _extract_text(self, text: str) -> str | None:
        source = " ".join(str(text or "").split()).strip()
        lowered = source.lower().replace("ё", "е")

        for prefix in sorted(TEXT_INPUT_PREFIXES, key=len, reverse=True):
            normalized_prefix = prefix.lower().replace("ё", "е")
            match = re.match(
                rf"^{re.escape(normalized_prefix)}(?:\s*[:,-]?\s*)(.*)$",
                lowered,
            )
            if match is None:
                continue

            # Use the original text slice so capitalization/punctuation from STT
            # are preserved as much as possible instead of typing the normalized copy.
            prefix_match = re.match(
                rf"^\s*.{{0,{max(0, len(prefix) + 4)}}}",
                source,
            )
            _ = prefix_match  # keep parsing deliberately based on word count below
            source_words = source.split()
            prefix_words = prefix.split()
            value = " ".join(source_words[len(prefix_words):]).strip(" :-,")
            return value

        return None
