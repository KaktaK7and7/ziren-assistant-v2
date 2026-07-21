import unittest

from app.core.command_text import is_exit_command, is_tts_test_command


class CommandTextTests(unittest.TestCase):
    def test_exit_commands_are_normalized(self) -> None:
        self.assertTrue(is_exit_command("  ЗАКРОЙ   ассистента "))
        self.assertTrue(is_exit_command("выход"))

    def test_exit_word_inside_ai_question_is_not_a_command(self) -> None:
        self.assertFalse(is_exit_command("расскажи про выход из приложения"))

    def test_tts_test_commands_are_explicit(self) -> None:
        self.assertTrue(is_tts_test_command("Проверка голоса"))
        self.assertFalse(is_tts_test_command("расскажи про тест Тьюринга"))


if __name__ == "__main__":
    unittest.main()
