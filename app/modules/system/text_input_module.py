from __future__ import annotations

import re

from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.windows_input import WindowsInputError, type_unicode_text


TEXT_INPUT_PREFIXES = [
    "введи текст",
    "напечатай",
    "напечатай текст",
    "напечатать",
    "напечатать текст",
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
        prefixes = sorted(
            (
                trigger
                for trigger in self.get_action_triggers("text.type")
                if trigger.strip()
            ),
            key=len,
            reverse=True,
        )

        for prefix in prefixes:
            normalized_prefix = prefix.lower().replace("ё", "е").strip()
            match = re.match(
                rf"^{re.escape(normalized_prefix)}(?:\s*[:,-]?\s*)(.*)$",
                lowered,
            )
            if match is None:
                continue

            source_words = source.split()
            prefix_words = prefix.split()
            value = " ".join(source_words[len(prefix_words):]).strip(" :-,")
            return value

        return None
