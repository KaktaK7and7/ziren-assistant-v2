import unittest

from app.core.command_speech import choose_command_speech


class CommandSpeechTests(unittest.TestCase):
    def test_ai_reaction_replaces_standard_confirmation(self) -> None:
        spoken, uses_ai = choose_command_speech(
            "Игра запущена.",
            True,
            "На пару каток или сегодня всерьёз?",
        )

        self.assertEqual(spoken, "На пару каток или сегодня всерьёз?")
        self.assertTrue(uses_ai)

    def test_standard_confirmation_remains_when_ai_has_no_line(self) -> None:
        spoken, uses_ai = choose_command_speech(
            "Музыка поставлена на паузу.",
            True,
            "",
        )

        self.assertEqual(spoken, "Музыка поставлена на паузу.")
        self.assertFalse(uses_ai)

    def test_late_ai_line_is_not_spoken_after_timeout(self) -> None:
        spoken, uses_ai = choose_command_speech(
            "Громкость увеличена.",
            False,
            "Теперь точно услышишь.",
        )

        self.assertEqual(spoken, "Громкость увеличена.")
        self.assertFalse(uses_ai)


if __name__ == "__main__":
    unittest.main()
